"""Part 4 student implementation."""

from app.backends import ansible, netconf, netmiko_textfsm, restconf

def dispatch_request(data):
    method = data["method"]
    action = data["action"]
    router = data["router"]
    interface = data["desired"]["interface"]

    routes = {
        ("restconf", "status"): (restconf, "get_interface_state"),
        ("restconf", "plan"): (restconf, "plan_interface"),
        ("restconf", "apply"): (restconf, "apply_interface"),
        ("netconf", "status"): (netconf, "get_interface_state"),
        ("netconf", "plan"): (netconf, "plan_interface"),
        ("netconf", "apply"): (netconf, "apply_interface"),
        ("ansible", "apply"): (ansible, "apply_interface"),
        ("netmiko-textfsm", "status"): (netmiko_textfsm, "get_interface_state"),
        ("netmiko-textfsm", "delete"): (netmiko_textfsm, "delete_interface"),
    }

    route = routes.get((method, action))
    if route is None:
        return {"status": "error", "result": "invalid_action"}

    module, function_name = route
    function = getattr(module, function_name)

    if action in ("status", "delete"):
        return function(router, interface["name"])
    return function(router, interface)