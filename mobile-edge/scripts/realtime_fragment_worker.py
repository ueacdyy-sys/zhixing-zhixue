"""Single-reader RTSP ingress that seals PTS-aligned A/V fragments.

One process owns the authorized RTSP connection.  It copies packets into
immutable Matroska fragments and emits PC-side arrival/seal telemetry.  OCR,
ASR and VLM must consume the sealed files; they must never open a second RTSP
connection to the phone.
"""

from __future__ import annotations

import argparse
import heapq
import hashlib
import json
import math
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import av


NS = 1_000_000_000
# RTSP interleaving can deliver an Opus packet whose media PTS is shortly
# before the video keyframe that opens the next independently decodable
# fragment.  The origin deliberately precedes that keyframe: it preserves the
# same-source A/V relationship instead of throwing away those packets.
AUDIO_PREROLL_NS = 250_000_000
AUDIO_COVERAGE_TOLERANCE_NS = 120_000_000
PACKET_REORDER_HORIZON_NS = 250_000_000


class SegmentProtocolError(ValueError):
    """Raised when a packet or ingress configuration violates the contract."""


@dataclass(frozen=True)
class LiveIngressConfig:
    source: str
    session_id: str
    output_dir: Path
    fragment_seconds: float = 2.0
    duration_seconds: float = 0.0

    def __post_init__(self) -> None:
        if not self.source.startswith("rtsp://") or not self.session_id:
            raise SegmentProtocolError("authorized_rtsp_source_and_session_id_required")
        if not math.isfinite(self.fragment_seconds) or self.fragment_seconds <= 0:
            raise SegmentProtocolError("fragment_seconds_must_be_positive")
        if not math.isfinite(self.duration_seconds) or self.duration_seconds < 0:
            raise SegmentProtocolError("duration_seconds_must_be_nonnegative")


def reader_options(config: LiveIngressConfig) -> dict[str, str]:
    del config
    return {"rtsp_transport": "tcp", "stimeout": "5000000"}


@dataclass(frozen=True)
class IncomingPacket:
    track: str
    pts: int
    time_base_numerator: int
    arrival_monotonic_ns: int
    is_keyframe: bool
    time_base_denominator: int = 1

    @property
    def pts_ns(self) -> int:
        if self.track not in {"video", "audio"} or self.time_base_numerator <= 0 or self.time_base_denominator <= 0:
            raise SegmentProtocolError("packet_time_base_invalid")
        return (self.pts * self.time_base_numerator * NS) // self.time_base_denominator


@dataclass(frozen=True)
class SealedFragment:
    fragment_index: int
    start_pts_ns: int
    end_pts_ns: int
    pc_arrival_first_monotonic_ns: int
    pc_sealed_monotonic_ns: int
    has_same_source_audio: bool


class PtsFragmenter:
    """Cuts only before a video keyframe once the target PTS duration is met."""

    def __init__(self, session_id: str, *, fragment_seconds: float) -> None:
        if not session_id or fragment_seconds <= 0:
            raise SegmentProtocolError("fragmenter_configuration_invalid")
        self.session_id = session_id
        self.target_ns = int(fragment_seconds * NS)
        self._index = 0
        self._start_pts_ns: int | None = None
        self._arrival_first_ns: int | None = None
        self._has_audio = False

    @property
    def active(self) -> bool:
        return self._start_pts_ns is not None

    @property
    def current_start_pts_ns(self) -> int | None:
        return self._start_pts_ns

    def accept(self, packet: IncomingPacket) -> list[SealedFragment]:
        pts_ns = packet.pts_ns
        if not self.active:
            if packet.track != "video" or not packet.is_keyframe:
                return []
            self._index += 1
            self._start_pts_ns = pts_ns
            self._arrival_first_ns = packet.arrival_monotonic_ns
            self._has_audio = False
            return []

        assert self._start_pts_ns is not None
        assert self._arrival_first_ns is not None
        if packet.track == "audio":
            self._has_audio = True
            return []
        if packet.track != "video" or not packet.is_keyframe or pts_ns - self._start_pts_ns < self.target_ns:
            return []
        closed = SealedFragment(
            fragment_index=self._index,
            start_pts_ns=self._start_pts_ns,
            end_pts_ns=pts_ns,
            pc_arrival_first_monotonic_ns=self._arrival_first_ns,
            pc_sealed_monotonic_ns=packet.arrival_monotonic_ns,
            has_same_source_audio=self._has_audio,
        )
        self._index += 1
        self._start_pts_ns = pts_ns
        self._arrival_first_ns = packet.arrival_monotonic_ns
        self._has_audio = False
        return [closed]

    def close(self, *, end_pts_ns: int, sealed_monotonic_ns: int) -> SealedFragment | None:
        if not self.active:
            return None
        assert self._start_pts_ns is not None
        assert self._arrival_first_ns is not None
        if end_pts_ns <= self._start_pts_ns:
            return None
        closed = SealedFragment(
            fragment_index=self._index,
            start_pts_ns=self._start_pts_ns,
            end_pts_ns=end_pts_ns,
            pc_arrival_first_monotonic_ns=self._arrival_first_ns,
            pc_sealed_monotonic_ns=sealed_monotonic_ns,
            has_same_source_audio=self._has_audio,
        )
        self._start_pts_ns = None
        self._arrival_first_ns = None
        self._has_audio = False
        return closed


def _packet_pts_ns(packet: av.Packet) -> int | None:
    if packet.pts is None or packet.time_base is None:
        return None
    return int(packet.pts * packet.time_base * NS)


def _packet_dts_ns(packet: av.Packet) -> int | None:
    if packet.dts is None or packet.time_base is None:
        return None
    return int(packet.dts * packet.time_base * NS)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _append_jsonl(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(item, ensure_ascii=False, allow_nan=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _verify_sealed_audio(
    path: Path,
    *,
    packet_audio_seen: bool,
    had_mux_skips: bool,
    audio_coverage_start_ns: int | None,
    audio_coverage_end_ns: int | None,
    window_start_pts_ns: int,
    window_end_pts_ns: int,
) -> str:
    """Return a sealed-media fact, never a prediction from the live packet loop."""

    with av.open(str(path)) as container:
        tracks = {stream.type for stream in container.streams}
    if "audio" not in tracks:
        return "NO_AUDIO_TRACK_VERIFIED"
    coverage_is_continuous = (
        audio_coverage_start_ns is not None
        and audio_coverage_end_ns is not None
        and audio_coverage_start_ns <= window_start_pts_ns + AUDIO_COVERAGE_TOLERANCE_NS
        and audio_coverage_end_ns >= window_end_pts_ns - AUDIO_COVERAGE_TOLERANCE_NS
    )
    if packet_audio_seen and not had_mux_skips and coverage_is_continuous:
        return "SAME_SOURCE_AUDIO_VERIFIED"
    return "AUDIO_INTEGRITY_UNRESOLVED"


class _FragmentSink:
    def __init__(self, path: Path, input_streams: list[av.stream.Stream], *, start_pts_ns: int) -> None:
        self.final_path = path
        self.partial_path = path.with_suffix(path.suffix + ".partial")
        self.start_pts_ns = start_pts_ns
        self.timeline_origin_ns = max(0, start_pts_ns - AUDIO_PREROLL_NS)
        self.container = av.open(str(self.partial_path), mode="w", format="matroska")
        self.streams = {stream.index: self.container.add_stream_from_template(stream) for stream in input_streams}
        self.last_dts_by_source_stream: dict[int, int] = {}
        self.max_dts_ns_by_source_stream: dict[int, int] = {}
        self.pending_by_source_stream: dict[int, list[tuple[int, int, av.Packet, int]]] = {}
        self._packet_sequence = 0
        self.skipped_nonmonotonic_packets = 0
        self.skipped_pre_roll_packets = 0
        self.skipped_mux_packets = 0
        self.audio_coverage_start_ns: int | None = None
        self.audio_coverage_end_ns: int | None = None

    def mux(self, packet: av.Packet, *, packet_pts_ns: int, packet_dts_ns: int) -> bool:
        """Queue packets per track and release only beyond a bounded DTS watermark."""

        mapped_stream = self.streams.get(packet.stream.index)
        if mapped_stream is None:
            return False
        # Do not cut audio at a video keyframe.  The audio track starts from a
        # bounded pre-roll origin, preserving packets that are interleaved
        # after the keyframe yet carry an earlier PTS.
        if packet_pts_ns < self.timeline_origin_ns:
            self.skipped_pre_roll_packets += 1
            return False
        stream_index = packet.stream.index
        self._packet_sequence += 1
        heap = self.pending_by_source_stream.setdefault(stream_index, [])
        heapq.heappush(heap, (packet_dts_ns, self._packet_sequence, packet, packet_pts_ns))
        prior_max = self.max_dts_ns_by_source_stream.get(stream_index, packet_dts_ns)
        self.max_dts_ns_by_source_stream[stream_index] = max(prior_max, packet_dts_ns)
        self._drain_stream(stream_index, force=False)
        return True

    def _drain_stream(self, source_stream_index: int, *, force: bool) -> None:
        heap = self.pending_by_source_stream[source_stream_index]
        cutoff = self.max_dts_ns_by_source_stream[source_stream_index] - PACKET_REORDER_HORIZON_NS
        while heap and (force or heap[0][0] <= cutoff):
            _source_dts_ns, _sequence, packet, packet_pts_ns = heapq.heappop(heap)
            self._mux_reordered(packet, packet_pts_ns=packet_pts_ns)

    def _mux_reordered(self, packet: av.Packet, *, packet_pts_ns: int) -> None:
        mapped_stream = self.streams.get(packet.stream.index)
        if mapped_stream is None:
            return
        if packet.time_base is None:
            raise SegmentProtocolError("packet_time_base_missing")
        offset = int((self.timeline_origin_ns / NS) / float(packet.time_base))
        if packet.pts is not None:
            packet.pts = max(0, packet.pts - offset)
        if packet.dts is not None:
            packet.dts = max(0, packet.dts - offset)
            previous_dts = self.last_dts_by_source_stream.get(packet.stream.index)
            if previous_dts is not None and packet.dts <= previous_dts:
                self.skipped_nonmonotonic_packets += 1
                return False
            self.last_dts_by_source_stream[packet.stream.index] = packet.dts
        if packet.pts is not None and packet.dts is not None and packet.pts < packet.dts:
            packet.pts = packet.dts
        packet.stream = mapped_stream
        try:
            self.container.mux(packet)
        except av.error.FFmpegError:
            self.skipped_mux_packets += 1
            return False
        if mapped_stream.type == "audio":
            self.audio_coverage_start_ns = (
                packet_pts_ns
                if self.audio_coverage_start_ns is None
                else min(self.audio_coverage_start_ns, packet_pts_ns)
            )
            self.audio_coverage_end_ns = (
                packet_pts_ns
                if self.audio_coverage_end_ns is None
                else max(self.audio_coverage_end_ns, packet_pts_ns)
            )
        return True

    def seal(self) -> Path:
        for source_stream_index in tuple(self.pending_by_source_stream):
            self._drain_stream(source_stream_index, force=True)
        self.container.close()
        if not self.partial_path.is_file() or self.partial_path.stat().st_size <= 0:
            raise SegmentProtocolError("fragment_media_missing_after_close")
        os.replace(self.partial_path, self.final_path)
        return self.final_path


def _open_sink(fragments_dir: Path, index: int, streams: list[av.stream.Stream], *, start_pts_ns: int) -> _FragmentSink:
    fragments_dir.mkdir(parents=True, exist_ok=True)
    return _FragmentSink(fragments_dir / f"fragment_{index:05d}.mkv", streams, start_pts_ns=start_pts_ns)


def run(
    config: LiveIngressConfig,
    *,
    on_fragment_committed: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run one bounded or continuous authorized ingress session.

    Packet arrival times are PC-local monotonic facts.  The caller must combine
    them with a phone clock anchor before claiming capture-to-PC latency.
    """

    started_ns = time.monotonic_ns()
    root = config.output_dir.resolve()
    fragments_dir = root / "fragments"
    telemetry_path = root / "realtime_telemetry.jsonl"
    root.mkdir(parents=True, exist_ok=True)
    fragmenter = PtsFragmenter(config.session_id, fragment_seconds=config.fragment_seconds)
    input_container = av.open(config.source, options=reader_options(config))
    source_streams = [stream for stream in input_container.streams if stream.type in {"video", "audio"}]
    video_stream = next((stream for stream in source_streams if stream.type == "video"), None)
    if video_stream is None:
        input_container.close()
        raise SegmentProtocolError("video_stream_required")
    sink: _FragmentSink | None = None
    last_pts_ns: int | None = None
    # FFmpeg may normalise an RTSP stream's packet PTS.  Preserve the exact
    # demuxer origin alongside the immutable fragments so phone-clock
    # alignment never calibrates itself from a later sealed timestamp.
    demux_start_time_us = int(input_container.start_time) if input_container.start_time is not None else None
    first_video_pts_ns: int | None = None
    first_video_arrival_ns: int | None = None
    observed_video_keyframes: list[dict[str, int]] = []
    published: list[dict[str, Any]] = []

    def publish(closed: SealedFragment) -> None:
        nonlocal sink
        if sink is None:
            raise SegmentProtocolError("fragment_sink_missing")
        sealed_sink = sink
        final_path = sealed_sink.seal()
        sink = None
        audio_status = _verify_sealed_audio(
            final_path,
            packet_audio_seen=closed.has_same_source_audio,
            had_mux_skips=bool(
                sealed_sink.skipped_nonmonotonic_packets
                or sealed_sink.skipped_pre_roll_packets
                or sealed_sink.skipped_mux_packets
            ),
            audio_coverage_start_ns=sealed_sink.audio_coverage_start_ns,
            audio_coverage_end_ns=sealed_sink.audio_coverage_end_ns,
            window_start_pts_ns=closed.start_pts_ns,
            window_end_pts_ns=closed.end_pts_ns,
        )
        payload = {
            "event_type": "FragmentCommitted",
            "session_id": config.session_id,
            **asdict(closed),
            "immutable_media_file": str(final_path),
            "sha256": _sha256(final_path),
            "audio_status": audio_status,
            "has_same_source_audio": audio_status == "SAME_SOURCE_AUDIO_VERIFIED",
            # The RTSP reader never runs FFmpeg remux work.  Materialization is
            # a downstream leased stage, so slow storage cannot back-pressure
            # the only authorized media reader.
            "model_media_file": None,
            "model_media_remux_s": None,
            "model_media_error": None,
            "skipped_nonmonotonic_packets": sealed_sink.skipped_nonmonotonic_packets,
            "skipped_pre_roll_packets": sealed_sink.skipped_pre_roll_packets,
            "skipped_mux_packets": sealed_sink.skipped_mux_packets,
            "audio_coverage_start_pts_ns": sealed_sink.audio_coverage_start_ns,
            "audio_coverage_end_pts_ns": sealed_sink.audio_coverage_end_ns,
            "timeline_origin_pts_ns": sealed_sink.timeline_origin_ns,
            "committed_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "arrival_clock_quality": "PC_MONOTONIC_ONLY",
        }
        _append_jsonl(telemetry_path, payload)
        if on_fragment_committed is not None:
            on_fragment_committed(payload)
        published.append(payload)

    transport_closed = False
    try:
        for packet in input_container.demux(source_streams):
            if packet.dts is None or packet.pts is None or packet.time_base is None:
                continue
            track = packet.stream.type
            if track not in {"video", "audio"}:
                continue
            arrived_ns = time.monotonic_ns()
            pts_ns = _packet_pts_ns(packet)
            dts_ns = _packet_dts_ns(packet)
            if pts_ns is None or dts_ns is None:
                continue
            if track == "video" and first_video_pts_ns is None:
                first_video_pts_ns = pts_ns
                first_video_arrival_ns = arrived_ns
            if track == "video" and bool(packet.is_keyframe):
                observed_video_keyframes.append({"pts_ns": pts_ns, "pc_arrival_monotonic_ns": arrived_ns})
            last_pts_ns = pts_ns if last_pts_ns is None else max(last_pts_ns, pts_ns)
            time_base = packet.time_base
            incoming = IncomingPacket(
                track=track,
                pts=int(packet.pts),
                time_base_numerator=int(time_base.numerator),
                time_base_denominator=int(time_base.denominator),
                arrival_monotonic_ns=arrived_ns,
                is_keyframe=bool(packet.is_keyframe),
            )
            closed = fragmenter.accept(incoming)
            if closed:
                publish(closed[0])
            if fragmenter.active and sink is None:
                start_pts_ns = fragmenter.current_start_pts_ns
                if start_pts_ns is None:
                    raise SegmentProtocolError("active_fragment_start_missing")
                sink = _open_sink(
                    fragments_dir,
                    closed[0].fragment_index + 1 if closed else 1,
                    source_streams,
                    start_pts_ns=start_pts_ns,
                )
            if sink is not None:
                sink.mux(packet, packet_pts_ns=pts_ns, packet_dts_ns=dts_ns)
            if config.duration_seconds and (arrived_ns - started_ns) >= int(config.duration_seconds * NS):
                break
    except av.error.ConnectionResetError:
        # Android ends its RTSP TCP stream by closing the socket.  Seal and
        # drain evidence already received instead of aborting all three lanes.
        transport_closed = True
    finally:
        sealed_ns = time.monotonic_ns()
        final = fragmenter.close(end_pts_ns=last_pts_ns or 0, sealed_monotonic_ns=sealed_ns)
        if final is not None and sink is not None:
            publish(final)
        elif sink is not None:
            sink.container.close()
            sink.partial_path.unlink(missing_ok=True)
        input_container.close()

    report = {
        "schema_version": "realtime_fragment_worker.v1",
        "session_id": config.session_id,
        "transport_closed": transport_closed,
        "fragment_seconds_target": config.fragment_seconds,
        "started_monotonic_ns": started_ns,
        "finished_monotonic_ns": time.monotonic_ns(),
        "single_rtsp_reader": True,
        "demux_start_time_us": demux_start_time_us,
        "first_video_pts_ns": first_video_pts_ns,
        "first_video_arrival_monotonic_ns": first_video_arrival_ns,
        "observed_video_keyframes": observed_video_keyframes,
        "arrival_clock_quality": "PC_MONOTONIC_ONLY",
        "fragment_count": len(published),
        "fragments": published,
        "telemetry_file": str(telemetry_path),
        "limitation": "phone PTS-to-monotonic anchor is required before computing capture-to-PC latency.",
    }
    report_path = root / "realtime_session_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--fragment-seconds", type=float, default=2.0)
    parser.add_argument("--duration-seconds", type=float, default=0.0, help="0 runs until interrupted.")
    args = parser.parse_args()
    try:
        report = run(
            LiveIngressConfig(
                source=args.source,
                session_id=args.session_id,
                output_dir=Path(args.output_dir),
                fragment_seconds=args.fragment_seconds,
                duration_seconds=args.duration_seconds,
            )
        )
    except (OSError, av.error.FFmpegError, SegmentProtocolError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}, ensure_ascii=False), flush=True)
        return 1
    print(json.dumps({"status": "ok", "fragment_count": report["fragment_count"], "report": str(Path(args.output_dir) / "realtime_session_report.json")}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
