"""Start the paired-PC gateway only over TLS.

The Android client intentionally rejects cleartext endpoints.  Supply a
certificate trusted by the phone (for example a locally installed development
CA certificate) instead of weakening Android network policy for the demo.
"""

from __future__ import annotations

import argparse
import base64
from dataclasses import replace
import hashlib
import socket
from pathlib import Path
import subprocess

import uvicorn

from lan_gateway_discovery import LanDiscoveryAdvertisement, LanGatewayDiscoveryResponder
from local_agent_gateway import GatewaySettings, build_app


def certificate_spki_sha256(certfile: Path) -> str:
    """Return the base64 SHA-256 pin of the certificate SubjectPublicKeyInfo."""
    public_key = subprocess.run(
        ["openssl", "x509", "-in", str(certfile), "-pubkey", "-noout"],
        check=True,
        capture_output=True,
    ).stdout
    der = subprocess.run(
        ["openssl", "pkey", "-pubin", "-outform", "DER"],
        input=public_key,
        check=True,
        capture_output=True,
    ).stdout
    return base64.b64encode(hashlib.sha256(der).digest()).decode("ascii")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8443)
    parser.add_argument("--certfile", type=Path, required=True)
    parser.add_argument("--keyfile", type=Path, required=True)
    parser.add_argument(
        "--ca-bundle",
        type=Path,
        help="CA bundle trusted by the PC outbox publisher when it posts back to this TLS gateway",
    )
    parser.add_argument("--pair-host", help="certificate SAN host/IP used by Android and LAN auto-discovery")
    parser.add_argument("--discovery-port", type=int, default=39271)
    args = parser.parse_args()
    if not args.certfile.is_file() or not args.keyfile.is_file():
        raise SystemExit("gateway_tls_certificate_or_key_missing")
    if args.pair_host and (args.ca_bundle is None or not args.ca_bundle.is_file()):
        raise SystemExit("pair_host_requires_gateway_ca_bundle")
    pin = certificate_spki_sha256(args.certfile)
    settings = GatewaySettings.from_environment()
    if args.pair_host:
        settings = replace(
            settings,
            gateway_public_url=f"https://{args.pair_host}:{args.port}",
            gateway_spki_sha256=pin,
            gateway_ca_bundle=args.ca_bundle,
        )
        print(f"LAN auto-pairing enabled for 120 seconds: https://{args.pair_host}:{args.port}#spki=sha256/{pin}", flush=True)
    else:
        print("LAN auto-pairing disabled: start with --pair-host matching the certificate SAN; manual pairing remains available.", flush=True)
    app = build_app(settings)
    responder: LanGatewayDiscoveryResponder | None = None
    if settings.gateway_public_url and settings.gateway_spki_sha256:
        device_name = socket.gethostname()
        def advertisement() -> LanDiscoveryAdvertisement | None:
            record = app.state.nearby_pairing.advertisement(settings.gateway_public_url, settings.gateway_spki_sha256, device_name)
            return LanDiscoveryAdvertisement(**record) if record is not None else None
        responder = LanGatewayDiscoveryResponder(advertisement, args.discovery_port)
        responder.start()
    try:
        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            ssl_certfile=str(args.certfile),
            ssl_keyfile=str(args.keyfile),
            log_level="info",
        )
    finally:
        if responder is not None:
            responder.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
