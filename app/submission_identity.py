"""Configured network identity of the erganiOS node submitting WRKCardSE."""
from __future__ import annotations
import ipaddress
import socket
from config import Config

def server_instance_id() -> str:
    return (Config.SERVER_INSTANCE_ID or socket.gethostname() or "unknown")[:200]

def _valid_ip(value: object) -> str | None:
    try: return str(ipaddress.ip_address(str(value or "").strip()))
    except ValueError: return None

def server_submission_identity() -> tuple[str | None, str]:
    return _valid_ip(Config.ERGANI_EGRESS_IP), server_instance_id()
