import json
import shutil
import subprocess
import sys
from pathlib import Path

from app.backends.common import classify_exception, error, netmask_for

ANSIBLE_DIR = Path(__file__).resolve().parents[2] / "ansible"
PLAYBOOK_TIMEOUT = 120

AUTH_MARKERS = (
    "authentication failed",
    "invalid/incorrect password",
    "permission denied",
    "authentication error",
)

def _ansible_playbook_binary():
    found = shutil.which("ansible-playbook")
    if found:
        return found
    return str(Path(sys.executable).parent / "ansible-playbook")


def _real_run_playbook(variables):
    """รัน ansible/apply_interface.yml และโยน exception ตามชนิดความล้มเหลว"""
    command = [
        _ansible_playbook_binary(),
        "-i", str(ANSIBLE_DIR / "inventory.ini"),
        str(ANSIBLE_DIR / "apply_interface.yml"),
        "-e", json.dumps({**variables, "ansible_host": variables["router"]}),
    ]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=PLAYBOOK_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError("ansible-playbook timed out") from exc

    if completed.returncode == 0:
        return

    output = (completed.stdout + completed.stderr).lower()
    if any(marker in output for marker in AUTH_MARKERS):
        raise PermissionError("router rejected credentials")
    if completed.returncode == 4 or "unreachable" in output:
        raise ConnectionError("router unreachable")
    raise RuntimeError(f"ansible-playbook failed ({completed.returncode})")


def apply_interface(
    router,
    desired_interface,
    run_playbook=None,
):
    """Apply complete desired interface state using Ansible."""
    run_playbook = run_playbook or _real_run_playbook

    try:
        address, mask = netmask_for(desired_interface["ipv4"])
        variables = {
            "router": router,
            "interface_name": desired_interface["name"],
            "description": desired_interface["description"],
            "ipv4_address": address,
            "netmask": mask,
            "shutdown": desired_interface["admin_state"] == "down",
        }
    except (ValueError, KeyError):
        return error("backend_failed")

    try:
        run_playbook(variables)
    except Exception as exc:
        return classify_exception(exc)

    return {"status": "ok", "result": "applied"}