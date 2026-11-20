# E2B buffered file contract

This opt-in development check uses the synchronous Python SDK `e2b==2.62.1`. A loopback create fixture returns connection metadata for one disposable sandbox. The SDK sends file operations to the selected data endpoint. Each run checks UTF-8 text with a trailing newline, a shorter overwrite, bytes 0–255, and a missing file after a successful write/read at the same endpoint.

## Run directly against envd

In a disposable Linux guest, put the pinned envd binary and these scripts on disk. Install `e2b==2.62.1` in a Python 3.11+ virtual environment, install `iproute2` and `socat`, and choose an existing unprivileged guest user. The direct runner starts envd only inside a loopback-only network namespace, initializes it with a fresh token, and gives the default user a temporary directory for its files.

```sh
sudo unshare --net --pid --fork --kill-child \
  /absolute/path/to/venv/bin/python run_private_envd.py /absolute/path/to/envd guest-user
```

## Run the same assertions through a router

Provision a disposable, initialized sandbox and map its ID to it in the router being tested. Set `E2B_SANDBOX_URL` to the router entrypoint, `FILE_TEST_SANDBOX_ID` to the routed ID, `FILE_TEST_ENVD_TOKEN` to its issued envd token, and `FILE_TEST_DIR` to an existing absolute directory owned by the guest default user. Run `python check_files.py` with the pinned SDK. A missing setting fails setup; the test never selects a direct fallback. Remove the disposable directory or sandbox after the run.

## Measured development results

On an arm64 Ubuntu 26.10 Lima VM with CPython 3.14.8 and HTTP/1.1:

| Endpoint | Result |
| --- | --- |
| Official envd v0.8.0 Linux/amd64 binary, QEMU user emulation, reported commit `3691039`, SHA-256 `752cfbc7ba66649ec1bffdc9b59529dd3527e7d3899c69351e05bd21dfc0dbf0` | 4/4 passed in a guest-user-owned directory. In an earlier run directly under sticky `/tmp`, the second write returned HTTP 500 with “permission denied”; the other three cases passed. |
| Linux/arm64 envd built from the OSEP mirror commit `f32ee8a2a50052f32e3632ceb451111a98dd5104` | 4/4 passed in a guest-user-owned directory. |
| Unmodified Go router at OpenSandbox `14658d4aa56a8d4b9941db3720a682d0d1b4e216` | Health returned 200. All four cases stopped at their first upload with HTTP 404. This scaffold has no file forwarding route. |

The binary’s embedded build identifier and the public source checkout are recorded separately. A forwarding router and Linux/amd64 Fast Sandbox acceptance are still pending.

[Upstream artifact location](https://github.com/e2b-dev/runtime/blob/f32ee8a2a50052f32e3632ceb451111a98dd5104/docs/RELEASING.md) · [OSEP-0027](../../../../oseps/0027-optional-e2b-compatibility.md)
