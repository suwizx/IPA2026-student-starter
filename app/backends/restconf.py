from app.backends.common import (
    classify_exception,
    error,
    router_credentials,
    to_cidr,
)
from app.backends import planning
from app.backends.common import (
    classify_exception,
    error,
    loopback_number,
    netmask_for,
    router_credentials,
    to_cidr,
)

TIMEOUT = 10
YANG_JSON = "application/yang-data+json"


def _real_http_get(url):
    import requests
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    return requests.get(
        url,
        auth=router_credentials(),
        headers={"Accept": YANG_JSON},
        verify=False,
        timeout=TIMEOUT,
    )

def _real_http_put(url, json):
    import requests
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    return requests.put(
        url,
        json=json,
        auth=router_credentials(),
        headers={"Accept": YANG_JSON, "Content-Type": YANG_JSON},
        verify=False,
        timeout=TIMEOUT,
    )

def _normalize(raw):
    iface = raw["ietf-interfaces:interface"]

    ipv4 = None
    addresses = (iface.get("ietf-ip:ipv4") or {}).get("address") or []
    if addresses:
        first = addresses[0]
        mask = first.get("netmask") or first.get("prefix-length")
        ipv4 = to_cidr(first["ip"], mask)

    return {
        "name": iface["name"],
        "ipv4": ipv4,
        "description": iface.get("description") or None,
        "admin_state": "down" if iface.get("enabled") is False else "up",
    }


def get_interface_state(
    router,
    interface_name,
    http_get=None,
):
    """Return normalized interface status using RESTCONF."""
    http_get = http_get or _real_http_get
    url = (
        f"https://{router}/restconf/data/"
        f"ietf-interfaces:interfaces/interface={interface_name}"
    )

    try:
        response = http_get(url)
        code = response.status_code

        if code == 404:
            return {"status": "ok", "result": "not_found", "interface": None}
        if code in (401, 403):
            return error("authentication_failed")
        if code != 200:
            return error("backend_failed")

        return {
            "status": "ok",
            "result": "found",
            "interface": _normalize(response.json()),
        }
    except Exception as exc:
        return classify_exception(exc)


def plan_interface(
    router,
    desired_interface,
    http_get=None,
):
    """Return create/update/no_change plan using RESTCONF status."""
    return planning.plan_interface(
        router,
        desired_interface,
        lambda r, name: get_interface_state(r, name, http_get),
    )


def apply_interface(
    router,
    desired_interface,
    http_put=None,
):
    """Apply complete desired interface state using RESTCONF."""
    http_put = http_put or _real_http_put
    
    try:
        number = loopback_number(desired_interface["name"])
        address, mask = netmask_for(desired_interface["ipv4"])
    except (ValueError, KeyError):
        return error("backend_failed")

    payload = {
        "name": number,
        "description": desired_interface["description"],
        "ip": {
            "address": {
                "primary": {"address": address, "mask": mask},
            },
        },
    }
    if desired_interface["admin_state"] == "down":
        payload["shutdown"] = [None]

    url = (
        f"https://{router}/restconf/data/"
        f"Cisco-IOS-XE-native:native/interface/Loopback={number}"
    )

    try:
        response = http_put(url, json={"Cisco-IOS-XE-native:Loopback": payload})
        code = response.status_code

        if code in (200, 201, 204):
            return {"status": "ok", "result": "applied"}
        if code in (401, 403):
            return error("authentication_failed")
        return error("backend_failed")
    except Exception as exc:
        return classify_exception(exc)
