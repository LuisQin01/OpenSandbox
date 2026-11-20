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

"""Exercise a privately initialized envd or a preconfigured router with e2b==2.62.1."""
import json
import os
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
from pathlib import PurePosixPath
from threading import Thread
from uuid import uuid4

from e2b import FileNotFoundException, Sandbox


class CreateFixture(BaseHTTPRequestHandler):
    """Only supplies connection metadata. Every file request goes to the chosen endpoint."""

    def do_POST(self):
        if self.path != "/compat/e2b/v2/sandboxes":
            self.send_error(404)
            return
        self.rfile.read(int(self.headers["Content-Length"]))
        body = json.dumps({
            "templateID": "base", "sandboxID": self.server.sandbox_id,
            "clientID": "local", "envdVersion": "0.8.0", "domain": "example.invalid",
            "envdAccessToken": self.server.envd_token,
        }).encode()
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


class FileContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if version("e2b") != "2.62.1":
            raise RuntimeError("Install e2b==2.62.1 to run this contract")
        endpoint = os.environ["E2B_SANDBOX_URL"]
        token = os.environ["FILE_TEST_ENVD_TOKEN"]
        sandbox_id = os.environ["FILE_TEST_SANDBOX_ID"]
        server = ThreadingHTTPServer(("127.0.0.1", 0), CreateFixture)
        cls.addClassCleanup(server.server_close)
        server.envd_token = token
        server.sandbox_id = sandbox_id
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        cls.addClassCleanup(thread.join)
        cls.addClassCleanup(server.shutdown)
        cls.sandbox = Sandbox.create(
            api_url=f"http://127.0.0.1:{server.server_port}/compat/e2b",
            api_key="local-create-fixture", template="base", http_version="1.1",
            retries=0, request_timeout=12,
        )
        if cls.sandbox.envd_api_url != endpoint:
            raise RuntimeError("SDK selected an unexpected file endpoint")

    def setUp(self):
        directory = PurePosixPath(os.environ["FILE_TEST_DIR"])
        if not directory.is_absolute():
            raise ValueError("FILE_TEST_DIR must be an absolute guest path")
        self.path = str(directory / f"e2b-files-{uuid4().hex}")

    def test_utf8(self):
        info = self.sandbox.files.write(self.path, "hello, 世界\n")
        self.assertEqual(info.path, self.path)
        self.assertEqual(self.sandbox.files.read(self.path), "hello, 世界\n")

    def test_overwrite_truncates(self):
        self.sandbox.files.write(self.path, "original contents\n")
        self.assertEqual(self.sandbox.files.read(self.path), "original contents\n")
        self.sandbox.files.write(self.path, "x")
        self.assertEqual(self.sandbox.files.read(self.path), "x")

    def test_binary(self):
        data = bytes(range(256))
        self.sandbox.files.write(self.path, data)
        self.assertEqual(self.sandbox.files.read(self.path, format="bytes"), data)

    def test_missing(self):
        # A router returning 404 for every URL must not satisfy the missing-file case.
        self.sandbox.files.write(self.path, "present")
        self.assertEqual(self.sandbox.files.read(self.path), "present")
        with self.assertRaises(FileNotFoundException):
            self.sandbox.files.read(self.path + ".missing")


if __name__ == "__main__":
    unittest.main(verbosity=2)
