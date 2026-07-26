"""Trainable temporal routing and evidence-aware visual-cache primitives.

This package is deliberately separate from ``realtime_runtime``.  The latter
owns RTSP ingress and immutable evidence; this package only consumes sealed,
hash-addressed windows exported from that ledger.
"""
