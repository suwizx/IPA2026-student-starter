"""Helpers shared by the Part 3 backends."""

import logging
import os
import re
import socket
from ipaddress import IPv4Interface

try:
    import requests
except ImportError:
    requests = None

try:
    from ncclient.transport.errors import (
        AuthenticationError as NcAuthenticationError,
        SSHError as NcSSHError,
        TransportError as NcTransportError,
    )
except ImportError:
    NcAuthenticationError = NcSSHError = NcTransportError = None

try:
    from netmiko.exceptions import (
        NetmikoAuthenticationException,
        NetmikoTimeoutException,
    )
except ImportError:
    NetmikoAuthenticationException = NetmikoTimeoutException = None

try:
    import paramiko
except ImportError:
    paramiko = None


def error(code):
    return {"status": "error", "result": code}


def _types(*candidates):
    return tuple(c for c in candidates if c is not None)


AUTH_ERRORS = _types(
    PermissionError,
    NcAuthenticationError,
    NetmikoAuthenticationException,
    getattr(paramiko, "AuthenticationException", None),
)

CONNECTION_ERRORS = _types(
    ConnectionError,
    TimeoutError,
    socket.timeout,
    socket.gaierror,
    getattr(requests, "Timeout", None),
    getattr(requests, "ConnectionError", None),
    NcSSHError,
    NcTransportError,
    NetmikoTimeoutException,
    getattr(paramiko, "SSHException", None),
)


log = logging.getLogger(__name__)


def classify_exception(exc):
    """แปลง exception เป็น error response"""
    log.warning("backend operation failed", exc_info=exc)
    if isinstance(exc, AUTH_ERRORS):
        return error("authentication_failed")
    if isinstance(exc, CONNECTION_ERRORS):
        return error("connection_failed")
    return error("backend_failed")


def exception_for_error(response):
    """แปลง error response กลับเป็น exception"""
    code = response.get("result")
    if code == "authentication_failed":
        return PermissionError("authentication failed")
    if code == "connection_failed":
        return ConnectionError("connection failed")
    return RuntimeError(code or "backend failed")


def router_credentials():
    return os.environ.get("ROUTER_USER", ""), os.environ.get("ROUTER_PASS", "")


def to_cidr(ip, mask):
    """172.23.123.1 + 255.255.255.255 -> 172.23.123.1/32"""
    return str(IPv4Interface(f"{ip}/{mask}"))


def loopback_number(interface_name):
    """Loopback123 -> 123"""
    match = re.fullmatch(r"Loopback(\d+)", interface_name or "")
    if not match:
        raise ValueError(f"not a Loopback interface: {interface_name!r}")
    return int(match.group(1))


def netmask_for(ipv4_cidr):
    """172.23.123.1/32 -> ("172.23.123.1", "255.255.255.255")"""
    interface = IPv4Interface(ipv4_cidr)
    return str(interface.ip), str(interface.network.netmask)