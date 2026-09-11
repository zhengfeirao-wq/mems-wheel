"""Deploy/test in an isolated G1 venv; reuse a user-supplied local SSH config.

The config is a local Python module exposing HOST, PORT, USER, PASSWORD. It is
loaded only for authorized lab operation; credentials are never copied/uploaded.
Paramiko is needed on the development PC, not in the tactile wheel.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import shlex
import sys
import time

import paramiko


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--root", default="/home/agi/tactile500_v2_lab_20260910")
    p.add_argument("--version", default="0.3.0")
    p.add_argument("mode", choices=("deploy", "run", "fetch"))
    p.add_argument("arguments", nargs=argparse.REMAINDER)
    a = p.parse_args()
    spec = importlib.util.spec_from_file_location("lab_connection", a.config)
    config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config)
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    # Match the user's existing authorized laboratory SSH helper policy.
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(config.HOST, port=config.PORT, username=config.USER,
                   password=config.PASSWORD, timeout=10)
    sftp = client.open_sftp()
    root = a.root.rstrip("/")

    def run(command):
        _, out, err = client.exec_command(command)
        while not out.channel.exit_status_ready() or out.channel.recv_ready() or out.channel.recv_stderr_ready():
            if out.channel.recv_ready():
                print(out.channel.recv(65536).decode("utf-8", "replace"), end="", flush=True)
            if out.channel.recv_stderr_ready():
                print(out.channel.recv_stderr(65536).decode("utf-8", "replace"), end="", flush=True)
            time.sleep(0.02)
        code = out.channel.recv_exit_status()
        if code:
            raise RuntimeError(f"remote command exited {code}")

    def upload_tree(local, remote):
        try:
            sftp.mkdir(remote)
        except OSError:
            sftp.stat(remote)
        for entry in local.iterdir():
            if entry.name == "__pycache__":
                continue
            if entry.is_dir():
                upload_tree(entry, remote + "/" + entry.name)
            else:
                sftp.put(str(entry), remote + "/" + entry.name)

    def fetch_tree(remote, local):
        import stat
        local.mkdir(parents=True, exist_ok=True)
        for entry in sftp.listdir_attr(remote):
            if entry.filename in (".", "..") or "/" in entry.filename or "\\" in entry.filename:
                continue
            destination = local / entry.filename
            source = remote + "/" + entry.filename
            if stat.S_ISDIR(entry.st_mode):
                fetch_tree(source, destination)
            elif stat.S_ISREG(entry.st_mode):
                sftp.get(source, str(destination))

    try:
        here = Path(__file__).resolve().parent.parent
        if a.mode == "deploy":
            try:
                sftp.mkdir(root)
            except OSError:
                sftp.stat(root)
            upload_tree(here / "wheelhouse", root + "/wheelhouse")
            upload_tree(here / "tests", root + "/tests")
            upload_tree(here / "tools", root + "/tools")
            run("python3 -m venv " + shlex.quote(root + "/.venv"))
            run(shlex.join([root + "/.venv/bin/python", "-m", "pip", "install", "--no-index",
                            "--find-links", root + "/wheelhouse", "--force-reinstall", "tactile500==" + a.version]))
            run(shlex.join([root + "/.venv/bin/python", "-c",
                "import tactile500,usb,platform,shutil; print(tactile500.__version__, usb.__version__, platform.machine()); print(tactile500.__file__); print('free_bytes',shutil.disk_usage('.').free)"]))
        elif a.mode == "run":
            run(shlex.join([root + "/.venv/bin/python", *a.arguments]))
        else:
            if len(a.arguments) != 2:
                p.error("fetch needs remote directory and local destination")
            fetch_tree(a.arguments[0], Path(a.arguments[1]))
            print(json.dumps({"fetched": a.arguments[0], "to": a.arguments[1]}))
    finally:
        sftp.close()
        client.close()


if __name__ == "__main__":
    main()
