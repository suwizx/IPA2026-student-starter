import re

from app.backends.common import (
    classify_exception,
    error,
    exception_for_error,
    router_credentials,
)


def _connect(router):
    from netmiko import ConnectHandler

    user, password = router_credentials()
    return ConnectHandler(
        device_type="cisco_ios",
        host=router,
        username=user,
        password=password,
        timeout=15,
        conn_timeout=15,
    )


def _parse_cli(command, raw_output):
    """
    - ข้อความ error ของ IOS (บรรทัดที่ขึ้นต้นด้วย %) แปลว่าไม่มี interface นี้ -> []
      ต้องเช็กก่อนส่งให้ TextFSM เพราะ template จะ raise error กับบรรทัดที่ไม่รู้จัก
    """
    text = (raw_output or "").strip()
    if not text or any(
        line.lstrip().startswith("%") for line in text.splitlines()
    ):
        return []

    from ntc_templates.parse import parse_output

    try:
        return parse_output(platform="cisco_ios", command=command, data=text)
    except Exception as exc:
        raise RuntimeError(
            f"TextFSM could not parse {command!r}: {text[:300]!r}"
        ) from exc


def _real_netmiko_get(router, interface_name):
    ip_command = f"show ip interface {interface_name}"
    description_command = "show interfaces description"

    with _connect(router) as conn:
        ip_info = _parse_cli(ip_command, conn.send_command(ip_command))
        descriptions = _parse_cli(
            description_command, conn.send_command(description_command)
        )
    return ip_info, descriptions


def _canonical_name(name):
    """Lo123 / loopback123 -> Loopback123"""
    match = re.fullmatch(r"(?i)(?:lo|loopback)\s*(\d+)", (name or "").strip())
    if match:
        return f"Loopback{match.group(1)}"
    return (name or "").strip()


def _first(value):
    """รับ list หรือค่าเดี่ยว คืนตัวแรก"""
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value or None


def _normalize(interface_name, ip_info, descriptions):
    ip_record = next(
        (r for r in ip_info if _canonical_name(r.get("interface")) == interface_name),
        None,
    )
    description_record = next(
        (
            r
            for r in descriptions
            if _canonical_name(r.get("port") or r.get("interface")) == interface_name
        ),
        None,
    )

    if ip_record is None and description_record is None:
        return None

    ipv4 = None
    admin_down = False
    if ip_record is not None:
        ip = _first(ip_record.get("ip_address"))
        prefix = _first(ip_record.get("prefix_length"))
        if ip and prefix:
            ipv4 = f"{ip}/{prefix}"
        admin_down = (
            "administratively down" in str(ip_record.get("link_status", "")).lower()
        )
    elif description_record is not None:
        admin_down = "admin" in str(description_record.get("status", "")).lower()

    description = None
    if description_record is not None:
        description = (description_record.get("description") or "").strip() or None

    return {
        "name": interface_name,
        "ipv4": ipv4,
        "description": description,
        "admin_state": "down" if admin_down else "up",
    }


def get_interface_state(
    router,
    interface_name,
    netmiko_get=None,
):
    """Return normalized interface status using Netmiko + TextFSM."""
    netmiko_get = netmiko_get or _real_netmiko_get

    try:
        ip_info, descriptions = netmiko_get(router, interface_name)
        interface = _normalize(interface_name, ip_info, descriptions)
    except Exception as exc:
        return classify_exception(exc)

    if interface is None:
        return {"status": "ok", "result": "not_found", "interface": None}
    return {"status": "ok", "result": "found", "interface": interface}

def _real_netmiko_delete(router, interface_name):
    current = get_interface_state(router, interface_name)
    if current["status"] != "ok":
        raise exception_for_error(current)
    if current["result"] == "not_found":
        return "not_found"

    with _connect(router) as conn:
        conn.send_config_set([f"no interface {interface_name}"])

    after = get_interface_state(router, interface_name)
    if after["status"] != "ok":
        raise exception_for_error(after)
    if after["result"] == "found":
        raise RuntimeError("interface still present after delete")
    return "deleted"

def delete_interface(
    router,
    interface_name,
    netmiko_delete=None,
):
    """Delete an interface using Netmiko."""
    netmiko_delete = netmiko_delete or _real_netmiko_delete
   
    try:
        outcome = netmiko_delete(router, interface_name)
    except Exception as exc:
        return classify_exception(exc)

    if outcome == "deleted":
        return {"status": "ok", "result": "deleted"}
    if outcome == "not_found":
        return {"status": "ok", "result": "not_found", "interface": None}
    return error("backend_failed")
