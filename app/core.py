import yaml

ALLOWED_ROUTERS = {
    "10.0.29.101", "10.0.29.102", "10.0.29.103",
    "10.0.29.104", "10.0.29.105",
}

METHOD_ACTIONS = {
    "restconf": {"status", "plan", "apply"},
    "netconf": {"status", "plan", "apply"},
    "ansible": {"apply"},
    "netmiko-textfsm": {"status", "delete"},
}

ADMIN_STATES = {"up", "down"}

def _error(code):
    return {"status": "error", "result": code}


def _missing(mapping, key):
    return key not in mapping or mapping[key] is None

def validate_request(data):
    """
    Validate one IPA2026 desired-state request.

    Return a response dictionary according to
    specs/response-spec-v1.md.
    """
    if not isinstance(data, dict):
           return _error("invalid_yaml")

    version = data.get("version")
    if type(version) is not int or version != 1:
        return _error("invalid_version")

    if _missing(data, "router"):
        return _error("missing_router")
    router = data["router"]
    if not isinstance(router, str) or router not in ALLOWED_ROUTERS:
        return _error("invalid_router")

    if _missing(data, "method"):
        return _error("missing_method")
    method = data["method"]
    if not isinstance(method, str) or method not in METHOD_ACTIONS:
        return _error("invalid_method")

    if _missing(data, "action"):
        return _error("missing_action")
    action = data["action"]
    if not isinstance(action, str) or action not in METHOD_ACTIONS[method]:
        return _error("invalid_action")

    desired = data.get("desired")
    if not isinstance(desired, dict):
        return _error("missing_desired")
    interface = desired.get("interface")
    if not isinstance(interface, dict):
        return _error("missing_interface")
    name = interface.get("name")
    if not isinstance(name, str) or not name:
        return _error("missing_interface_name")

    if action in ("plan", "apply"):
        if _missing(interface, "ipv4"):
            return _error("missing_ipv4")
        if _missing(interface, "description"):
            return _error("missing_description")
        if _missing(interface, "admin_state"):
            return _error("missing_admin_state")
        admin_state = interface["admin_state"]
        if not isinstance(admin_state, str) or admin_state not in ADMIN_STATES:
            return _error("invalid_admin_state")

    return {"status": "ok", "result": "accepted"}


def process_request_file(path):
    """
    Read a YAML request file, validate it,
    and return a response dictionary.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (yaml.YAMLError, UnicodeDecodeError, OSError):
        return _error("invalid_yaml")

    return validate_request(data)
