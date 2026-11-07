import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from app.backends import planning
from app.backends.common import (
    classify_exception,
    error,
    loopback_number,
    netmask_for,
    router_credentials,
    to_cidr,
)

IF_NS = "urn:ietf:params:xml:ns:yang:ietf-interfaces"
IP_NS = "urn:ietf:params:xml:ns:yang:ietf-ip"


def _connect(router):
    from ncclient import manager

    user, password = router_credentials()
    connection = manager.connect(
        host=router,
        port=830,
        username=user,
        password=password,
        hostkey_verify=False,
        look_for_keys=False,
        allow_agent=False,
        timeout=10,
    )
    if connection is None:
        raise ConnectionError("could not open a NETCONF session")
    return connection


def _real_get_config(router, filter_xml):
    with _connect(router) as m:
        return m.get_config(source="running", filter=("subtree", filter_xml)).data_xml


def _status_filter(interface_name):
    return (
        f'<interfaces xmlns="{IF_NS}">'
        f"<interface><name>{escape(interface_name)}</name></interface>"
        "</interfaces>"
    )


def _normalize(interface_name, xml_text):
    root = ET.fromstring(xml_text)

    for iface in root.iter(f"{{{IF_NS}}}interface"):
        name = iface.findtext(f"{{{IF_NS}}}name")
        if (name or "").strip() != interface_name:
            continue

        description = iface.findtext(f"{{{IF_NS}}}description")
        enabled = (iface.findtext(f"{{{IF_NS}}}enabled") or "true").strip()

        ipv4 = None
        address = iface.find(f"{{{IP_NS}}}ipv4/{{{IP_NS}}}address")
        if address is not None:
            ip = address.findtext(f"{{{IP_NS}}}ip")
            mask = address.findtext(f"{{{IP_NS}}}netmask") or address.findtext(
                f"{{{IP_NS}}}prefix-length"
            )
            if ip and mask:
                ipv4 = to_cidr(ip.strip(), mask.strip())
        

        return {
            "name": interface_name,
            "ipv4": ipv4,
            "description": (description.strip() or None) if description else None,
            "admin_state": "down" if enabled.lower() == "false" else "up",
        }

    return None


def _real_edit_config(router, config_xml):
    with _connect(router) as m:
        m.edit_config(target="running", config=config_xml)


def _build_config(desired_interface):
    number = loopback_number(desired_interface["name"])
    address, mask = netmask_for(desired_interface["ipv4"])
    shutdown = "<shutdown/>" if desired_interface["admin_state"] == "down" else ""

    return (
        '<config xmlns="urn:ietf:params:xml:ns:netconf:base:1.0" '
        'xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">'
        '<native xmlns="http://cisco.com/ns/yang/Cisco-IOS-XE-native">'
        "<interface>"
        '<Loopback nc:operation="replace">'
        f"<name>{number}</name>"
        f"<description>{escape(desired_interface['description'])}</description>"
        "<ip><address><primary>"
        f"<address>{address}</address>"
        f"<mask>{mask}</mask>"
        "</primary></address></ip>"
        f"{shutdown}"
        "</Loopback>"
        "</interface>"
        "</native>"
        "</config>"
    )


def get_interface_state(
    router,
    interface_name,
    netconf_get_config=None,
):
    """Return normalized interface status using NETCONF."""
    netconf_get_config = netconf_get_config or _real_get_config

    try:
        xml_text = netconf_get_config(router, _status_filter(interface_name))
        interface = _normalize(interface_name, xml_text)
    except Exception as exc:
        return classify_exception(exc)

    if interface is None:
        return {"status": "ok", "result": "not_found", "interface": None}
    return {"status": "ok", "result": "found", "interface": interface}


def plan_interface(
    router,
    desired_interface,
    netconf_get_config=None,
):
    """Return create/update/no_change plan using NETCONF status."""
    return planning.plan_interface(
        router,
        desired_interface,
        lambda r, name: get_interface_state(r, name, netconf_get_config),
    )


def apply_interface(
    router,
    desired_interface,
    netconf_edit_config=None,
):
    """Apply complete desired interface state using NETCONF."""
    netconf_edit_config = netconf_edit_config or _real_edit_config

    try:
        config_xml = _build_config(desired_interface)
    except (ValueError, KeyError):
        return error("backend_failed")

    try:
        netconf_edit_config(router, config_xml)
    except Exception as exc:
        return classify_exception(exc)

    return {"status": "ok", "result": "applied"}
