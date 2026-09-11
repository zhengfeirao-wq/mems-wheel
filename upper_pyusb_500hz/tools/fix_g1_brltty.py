"""Scope the installed G1 BRLTTY udev rule away from tactile CH340 devices.

Run with sudo only after diagnosing the conflict. Does not uninstall BRLTTY,
disable its service permanently, change the kernel or install serial drivers.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

OLD = 'ENV{PRODUCT}=="1a86/7523/*", ENV{BRLTTY_BRAILLE_DRIVER}="bm", GOTO="brltty_usb_run"'
NEW = ('# Tactile500: these CH340 bridges are tactile boards, not braille displays.\n'
       'ENV{PRODUCT}=="1a86/7523/*", ENV{BRLTTY_BRAILLE_DRIVER}="", '
       'ENV{BRLTTY_BRAILLE_DEVICE}="", ENV{BRLTTY_PID_FILE}="", '
       'ENV{SYSTEMD_WANTS}="", GOTO="brltty_device_end"')


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--backup", type=Path, required=True)
    p.add_argument("--apply", action="store_true")
    a = p.parse_args()
    vendor = Path("/lib/udev/rules.d/85-brltty.rules")
    override = Path("/etc/udev/rules.d/85-brltty.rules")
    source = override if override.exists() else vendor
    original = source.read_text()
    if original.count(OLD) != 1:
        raise SystemExit("Expected exactly one original CH340 rule; inspect this OS version manually")
    print(json.dumps({"source": str(source), "change": "replace only PRODUCT=1a86/7523 BRLTTY match",
                      "override": str(override), "backup": str(a.backup)}))
    if not a.apply:
        return
    if os.geteuid() != 0:
        raise SystemExit("Root is required to install the local udev override")
    # Stopping the current udev instance is permitted only if its USB handles
    # are exclusively the target CH340 family; never stop a real other display.
    pid_text = subprocess.check_output(
        ["systemctl", "show", "-p", "MainPID", "--value", "brltty-udev.service"], text=True).strip()
    usb_handles = []
    if pid_text.isdigit() and int(pid_text):
        for fd in Path(f"/proc/{pid_text}/fd").iterdir():
            try:
                target = str(fd.resolve())
            except OSError:
                continue
            if not target.startswith("/dev/bus/usb/"):
                continue
            props = subprocess.check_output(["udevadm", "info", "--query=property", "--name", target], text=True)
            if "PRODUCT=1a86/7523/" not in props:
                raise SystemExit("BRLTTY owns another USB device; do not stop its service automatically")
            usb_handles.append(target)
    a.backup.mkdir(parents=True, exist_ok=False)
    shutil.copy2(vendor, a.backup / "vendor-85-brltty.rules")
    if override.exists():
        shutil.copy2(override, a.backup / "previous-override-85-brltty.rules")
    manifest = {"override_existed": override.exists(), "source_sha256": hashlib.sha256(original.encode()).hexdigest(),
                "brltty_pid": pid_text, "target_usb_handles": usb_handles}
    updated = original.replace(OLD, NEW)
    temporary = override.with_suffix(".rules.tactile500-tmp")
    temporary.write_text(updated)
    temporary.chmod(0o644)
    temporary.replace(override)
    subprocess.run(["udevadm", "control", "--reload-rules"], check=True)
    if usb_handles:
        subprocess.run(["systemctl", "stop", "brltty-udev.service"], check=True)
    subprocess.run(["udevadm", "trigger", "--action=change", "--subsystem-match=usb",
                    "--attr-match=idVendor=1a86", "--attr-match=idProduct=7523"], check=True)
    subprocess.run(["udevadm", "settle", "--timeout=5"], check=True)
    manifest["override_sha256"] = hashlib.sha256(override.read_bytes()).hexdigest()
    (a.backup / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps({"applied": True, **manifest}))


if __name__ == "__main__":
    main()
