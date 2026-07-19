from __future__ import annotations

import socket
import threading
import unittest

from rtsp_clock_sampler import read_clock


class RtspClockSamplerTests(unittest.TestCase):
    def test_get_parameter_uses_valid_rtsp_crlf_and_reads_all_clock_facts(self) -> None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        observed: list[bytes] = []

        def serve_once() -> None:
            connection, _ = listener.accept()
            with connection:
                observed.append(connection.recv(4096))
                connection.sendall(
                    b"RTSP/1.0 200 OK\r\n"
                    b"X-Zhixing-Clock-Session-Epoch: 3\r\n"
                    b"X-Zhixing-Clock-Anchor-Elapsed-Ns: 100\r\n"
                    b"X-Zhixing-Clock-Latest-Video-Pts-Us: 200\r\n"
                    b"X-Zhixing-Clock-Latest-Audio-Pts-Us: 201\r\n"
                    b"X-Zhixing-Clock-Last-Media-Emit-Elapsed-Ns: 300\r\n"
                    b"X-Zhixing-Clock-Observed-Elapsed-Ns: 301\r\n"
                    b"X-Zhixing-Clock-Last-Requested-Keyframe-Pts-Us: 202\r\n"
                    b"X-Zhixing-Clock-Last-Requested-Keyframe-Emit-Elapsed-Ns: 302\r\n\r\n"
                )

        server = threading.Thread(target=serve_once)
        server.start()
        try:
            sample = read_clock("127.0.0.1", port, "screen", timeout_seconds=2)
        finally:
            server.join(timeout=2)
            listener.close()

        self.assertEqual(sample["session_epoch_id"], 3)
        self.assertEqual(sample["latest_video_pts_us"], 200)
        self.assertEqual(sample["phone_observed_elapsed_realtime_ns"], 301)
        self.assertEqual(sample["last_requested_keyframe_pts_us"], 202)
        self.assertIn(b"GET_PARAMETER rtsp://127.0.0.1", observed[0])
        self.assertTrue(observed[0].endswith(b"\r\n\r\n"))
