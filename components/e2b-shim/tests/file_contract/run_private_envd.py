# Copyright 2026 The OpenSandbox Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Run the direct file contract inside a disposable Linux VM's loopback-only namespace."""
import argparse
import hashlib
import http.client
import json
import os
import pwd
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def initialize(user, token, daemon):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if daemon.poll() is not None:
            raise RuntimeError(f"envd exited with status {daemon.returncode}")
        conn = http.client.HTTPConnection("127.0.0.1", 49983, timeout=2)
        try:
            conn.request("GET", "/health")
            if conn.getresponse().status == 204:
                break
        except OSError:
            pass
        finally:
            conn.close()
        time.sleep(0.1)
    else:
        raise RuntimeError("envd did not become healthy")

    conn = http.client.HTTPConnection("127.0.0.1", 49983, timeout=10)
    try:
        conn.request("POST", "/init", json.dumps({"accessToken": token, "defaultUser": user}),
                     {"Content-Type": "application/json"})
        status = conn.getresponse().status
        if status != 204:
            raise RuntimeError(f"private envd initialization returned HTTP {status}")
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("envd", type=Path)
    parser.add_argument("guest_user", help="existing unprivileged guest user for file operations")
    args = parser.parse_args()
    binary = args.envd.resolve(strict=True)
    guest = pwd.getpwnam(args.guest_user)
    if guest.pw_uid == 0 or os.geteuid() != 0:
        parser.error("run as root and specify an unprivileged guest user")
    if [name for _, name in socket.if_nameindex()] != ["lo"]:
        parser.error("run inside a private network namespace with only lo")
    subprocess.run(["ip", "link", "set", "lo", "up"], check=True)
    version = subprocess.check_output([binary, "-version"], text=True).strip()
    if version != "0.8.0":
        parser.error(f"expected envd 0.8.0, got {version}")
    commit = subprocess.check_output([binary, "-commit"], text=True).strip()
    with binary.open("rb") as f:
        digest = hashlib.file_digest(f, "sha256").hexdigest()
    print(f"envd={version} reported_commit={commit} sha256={digest}", flush=True)

    with tempfile.TemporaryDirectory(prefix="e2b-files-") as directory:
        os.chown(directory, guest.pw_uid, guest.pw_gid)
        daemon = subprocess.Popen([binary, "-isnotfc", "-no-cgroups"])
        try:
            token = secrets.token_urlsafe(32)
            initialize(args.guest_user, token, daemon)
            env = dict(os.environ, E2B_SANDBOX_URL="http://127.0.0.1:49983",
                       FILE_TEST_ENVD_TOKEN=token, FILE_TEST_SANDBOX_ID="sbx-2839-local",
                       FILE_TEST_DIR=directory, NO_PROXY="*", no_proxy="*")
            subprocess.run([sys.executable, Path(__file__).with_name("check_files.py")],
                           env=env, check=True)
        finally:
            daemon.terminate()
            try:
                daemon.wait(timeout=3)
            except subprocess.TimeoutExpired:
                daemon.kill()
                daemon.wait()


if __name__ == "__main__":
    main()
