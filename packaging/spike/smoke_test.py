"""Smoke test for the built closet-spike executable. Standard library only.

    python smoke_test.py path/to/closet-spike[.exe]

1. Runs `<exe> --selfcheck` and requires exit code 0 with every check ok.
2. Starts the executable on a free port, polls /health until ok (one-file
   programs unpack slowly), fetches /selfcheck and / (the bundled static
   page), POSTs /shutdown and requires the process to exit with code 0.

Exits 0 on success, 1 on failure (with the server log and the reason).
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

STATIC_MARKER = "closet-spike-static-ok"
EXPECTED_CHECKS = ("onnxruntime", "pillow_webp", "pillow_heif", "ffmpeg_frame", "static_file")

# Never route the loopback requests through a proxy from the environment.
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class SmokeFailure(Exception):
    pass


def log(message: str) -> None:
    print(f"[smoke] {message}", flush=True)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def http(method: str, url: str, timeout: float) -> tuple[int, bytes]:
    request = urllib.request.Request(url, method=method, data=b"" if method == "POST" else None)
    with _opener.open(request, timeout=timeout) as response:
        return response.status, response.read()


def http_json(method: str, url: str, timeout: float) -> dict:
    try:
        status, body = http(method, url, timeout)
    except urllib.error.HTTPError as exc:
        raise SmokeFailure(f"{method} {url} -> HTTP {exc.code}: {exc.read()[:500]!r}") from exc
    except OSError as exc:
        raise SmokeFailure(f"{method} {url} failed: {exc!r}") from exc
    if status != 200:
        raise SmokeFailure(f"{method} {url} -> HTTP {status}")
    try:
        return json.loads(body)
    except ValueError as exc:
        raise SmokeFailure(f"{method} {url} returned non-JSON: {body[:500]!r}") from exc


def describe_checks(report: dict, source: str) -> None:
    """Print one line per check and fail if any is missing or not ok."""
    checks = report.get("checks") or {}
    failed = []
    for name in EXPECTED_CHECKS:
        entry = checks.get(name)
        if entry is None:
            failed.append(f"{name}: missing from report")
            log(f"  {name:<13} MISSING")
            continue
        detail = entry.get("detail") or {}
        note = ""
        if name == "pillow_heif" and entry.get("ok"):
            note = f"path={detail.get('path')}"
        elif name == "ffmpeg_frame" and entry.get("ok"):
            note = f"ffmpeg {detail.get('ffmpeg')} in_bundle={detail.get('exe_in_bundle')}"
        elif name == "onnxruntime" and entry.get("ok"):
            note = f"onnxruntime {detail.get('onnxruntime')}"
        if entry.get("ok"):
            log(f"  {name:<13} ok      {entry.get('seconds', '?')}s  {note}")
        else:
            log(f"  {name:<13} FAILED  {entry.get('error')}")
            if entry.get("traceback"):
                print(entry["traceback"], flush=True)
            failed.append(f"{name}: {entry.get('error')}")
    if failed or not report.get("ok"):
        raise SmokeFailure(f"{source}: checks failed: " + ("; ".join(failed) or "report ok=false"))
    if report.get("frozen") is not True:
        raise SmokeFailure(f"{source}: report says frozen={report.get('frozen')!r}, expected a built executable")


def kill_tree(proc: subprocess.Popen) -> None:
    """Kill the process and its children.

    A one-file PyInstaller program is two processes (bootloader + the real
    app); killing only the parent on Windows would leave the child running.
    """
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        proc.kill()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


def step_cli_selfcheck(exe: Path, timeout: float) -> None:
    log(f"step 1: {exe.name} --selfcheck")
    started = time.monotonic()
    try:
        done = subprocess.run(
            [str(exe), "--selfcheck"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise SmokeFailure(f"--selfcheck did not finish within {timeout:.0f}s") from exc
    except OSError as exc:
        raise SmokeFailure(f"could not start {exe}: {exc!r}") from exc
    stdout = done.stdout.decode("utf-8", "replace")
    stderr = done.stderr.decode("utf-8", "replace")
    log(f"  exit code {done.returncode} after {time.monotonic() - started:.1f}s")
    try:
        report = json.loads(stdout)
    except ValueError:
        report = None
    if report is None:
        print("----- stdout -----\n" + stdout[-4000:], flush=True)
        print("----- stderr -----\n" + stderr[-4000:], flush=True)
        raise SmokeFailure(f"--selfcheck exited {done.returncode} and did not print JSON")
    log(f"  python {report.get('python')} on {report.get('platform')} ({report.get('machine')})")
    try:
        describe_checks(report, "--selfcheck")
    except SmokeFailure:
        if stderr.strip():
            print("----- stderr -----\n" + stderr[-4000:], flush=True)
        raise
    if done.returncode != 0:
        print("----- stderr -----\n" + stderr[-4000:], flush=True)
        raise SmokeFailure(f"--selfcheck reported ok but exited {done.returncode}")


def step_server(exe: Path, startup_timeout: float, shutdown_timeout: float) -> None:
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    log(f"step 2: {exe.name} --port {port}")
    with tempfile.TemporaryDirectory(prefix="closet-smoke-", ignore_cleanup_errors=True) as tmp:
        log_path = Path(tmp) / "server.log"
        with open(log_path, "wb") as log_file:
            proc = subprocess.Popen(
                [str(exe), "--port", str(port)],
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )
            try:
                _drive_server(proc, base, startup_timeout, shutdown_timeout)
            except SmokeFailure:
                kill_tree(proc)
                log_file.flush()
                text = log_path.read_text(encoding="utf-8", errors="replace")
                print("----- server output (tail) -----\n" + text[-6000:], flush=True)
                raise
            finally:
                kill_tree(proc)


def _drive_server(
    proc: subprocess.Popen, base: str, startup_timeout: float, shutdown_timeout: float
) -> None:
    started = time.monotonic()
    deadline = started + startup_timeout
    health = None
    last_error = "no attempt made"
    while time.monotonic() < deadline:
        code = proc.poll()
        if code is not None:
            raise SmokeFailure(f"process exited with code {code} before /health answered")
        try:
            status, body = http("GET", base + "/health", timeout=2)
            candidate = json.loads(body)
            if status == 200 and candidate.get("status") == "ok":
                health = candidate
                break
            last_error = f"HTTP {status}: {body[:200]!r}"
        except (OSError, ValueError) as exc:
            last_error = repr(exc)
        time.sleep(0.5)
    if health is None:
        raise SmokeFailure(
            f"/health not ok within {startup_timeout:.0f}s (last error: {last_error})"
        )
    log(f"  /health ok after {time.monotonic() - started:.1f}s: {json.dumps(health)}")
    for key in ("version", "model_state"):
        if not isinstance(health.get(key), str) or not health[key]:
            raise SmokeFailure(f"/health is missing {key!r}: {health}")

    report = http_json("GET", base + "/selfcheck", timeout=180)
    log("  /selfcheck:")
    describe_checks(report, "GET /selfcheck")

    try:
        status, body = http("GET", base + "/", timeout=30)
    except OSError as exc:
        raise SmokeFailure(f"GET / failed: {exc!r}") from exc
    page = body.decode("utf-8", "replace")
    if status != 200 or STATIC_MARKER not in page:
        raise SmokeFailure(f"GET / -> HTTP {status}, marker {STATIC_MARKER!r} not found: {page[:300]!r}")
    log(f"  GET / ok ({len(body)} bytes, static marker present)")

    reply = http_json("POST", base + "/shutdown", timeout=30)
    log(f"  POST /shutdown -> {json.dumps(reply)}")
    stop_started = time.monotonic()
    try:
        code = proc.wait(timeout=shutdown_timeout)
    except subprocess.TimeoutExpired as exc:
        raise SmokeFailure(
            f"process still running {shutdown_timeout:.0f}s after POST /shutdown"
        ) from exc
    log(f"  process exited with code {code} after {time.monotonic() - stop_started:.1f}s")
    if code != 0:
        raise SmokeFailure(f"process exited with code {code} after /shutdown, expected 0")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("exe", type=Path, help="path to the built closet-spike executable")
    parser.add_argument("--startup-timeout", type=float, default=90.0)
    parser.add_argument("--shutdown-timeout", type=float, default=20.0)
    parser.add_argument("--selfcheck-timeout", type=float, default=300.0)
    args = parser.parse_args()

    exe = args.exe.resolve()
    if not exe.is_file():
        print(f"SMOKE TEST FAILED: executable not found: {exe}", flush=True)
        return 1
    log(f"executable: {exe} ({exe.stat().st_size / 1_048_576:.1f} MiB)")
    try:
        step_cli_selfcheck(exe, args.selfcheck_timeout)
        step_server(exe, args.startup_timeout, args.shutdown_timeout)
    except SmokeFailure as failure:
        print(f"SMOKE TEST FAILED: {failure}", flush=True)
        return 1
    print("SMOKE TEST PASSED", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
