"""Smoke test for the built Closet program. Standard library only (Python 3.10+).

    python packaging/smoke_test.py PROGRAM [--expect-version X.Y.Z]
    python packaging/smoke_test.py PROGRAM --cutout --model isnet-general-use.onnx

PROGRAM is dist/Closet.exe (Windows), dist/closet (Linux) or, on macOS, the
executable inside the bundle: dist/Closet.app/Contents/MacOS/Closet.

Every run uses a fresh, empty data folder (CLOSET_DATA_DIR) and
CLOSET_NO_AUTO_DOWNLOAD=1, so nothing on the machine is touched or downloaded.
ANTHROPIC_API_KEY is removed from the program's environment, so it can never
call Claude with a key.

Default mode:
  1. `PROGRAM selfcheck --out FILE`: exit code 0, every check ok (the
     drawing check draws a garment, the updater check imports the module
     that installs new releases), model_state == "missing".
  2. `PROGRAM --no-browser --no-tray --port N`: /api/health answers within
     the startup timeout with app == "closet", model_state == "missing",
     setup_required == true; GET / is the built page (id="root") and the
     scripts and styles it links to are served with the right types;
     POST /api/setup -> 204 + session cookie; GET /api/items -> 200;
     GET /api/tagging -> 200 with the plan route then the API route;
     POST /api/profile demo -> GET /api/items has 43 items, and a demo
     item's drawing is served;
     POST /api/quit -> the process exits with code 0 within 30 s; the data
     folder then has closet.db and no closet.lock.
  3. Migrations: the selfcheck counts as many bundled migrations as the
     repository has (backend/closet/migrations, or --migrations DIR), and
     the new main closet and the demo closet are both at the latest one
     (PRAGMA user_version).

--cutout mode:
  Copies the model into <data folder>/models/ and runs
  `PROGRAM selfcheck --cutout --out FILE`: every check ok, model_state ==
  "ready" and the cutout check ok.

Exits 0 on success, 1 on failure (with the reason and the program's output
and log). Never leaves a process running: the whole process tree is killed
on failure or interruption (a one-file program is two processes).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

DEMO_ITEMS = 43
PASSPHRASE = "smoke-test-passphrase"
MIGRATIONS = Path(__file__).resolve().parent.parent / "backend" / "closet" / "migrations"
BASE_CHECKS = ("webp", "heic", "onnxruntime", "database", "web_page", "drawing", "model_state", "tagger", "updater")

# Never route loopback requests through a proxy from the environment.
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class SmokeFailure(Exception):
    pass


def log(message: str) -> None:
    print(f"[smoke] {message}", flush=True)


def section(title: str, text: str, limit: int = 6000) -> None:
    text = text.strip()
    if text:
        print(f"----- {title} (last {limit} chars) -----\n{text[-limit:]}\n----- end {title} -----", flush=True)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def program_env(data_dir: Path) -> dict:
    env = dict(os.environ)
    for key in ("CLOSET_HOST", "CLOSET_PORT", "ANTHROPIC_API_KEY"):
        env.pop(key, None)
    env["CLOSET_DATA_DIR"] = str(data_dir)
    env["CLOSET_NO_AUTO_DOWNLOAD"] = "1"
    return env


# ---------------------------------------------------------------- processes
def start(cmd: list[str], env: dict, output: Path) -> subprocess.Popen:
    kwargs: dict = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True  # own process group, so killpg reaches the unpacked child
    with open(output, "wb") as out:
        try:
            return subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, env=env, **kwargs)
        except OSError as exc:
            raise SmokeFailure(f"could not start {cmd[0]}: {exc!r}") from exc


def kill_tree(proc: subprocess.Popen) -> None:
    """Kill the process and everything it started (bootloader + app)."""
    if os.name == "nt":
        if proc.poll() is None:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    else:
        try:  # the group can outlive its leader, so always try
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        log(f"WARNING: process {proc.pid} did not die after being killed")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def dump_diagnostics(output: Path, data_dir: Path) -> None:
    section("program output", read_text(output))
    section("closet.log", read_text(data_dir / "logs" / "closet.log"))
    if os.name == "nt":
        log("note: the Windows build is windowed; a crash may show an error dialog that blocks until the timeout")


# ---------------------------------------------------------------- selfcheck
def run_selfcheck(program: Path, data_dir: Path, work: Path, cutout: bool, timeout: float,
                  expect_version: str | None) -> dict:
    out_file = work / ("selfcheck-cutout.json" if cutout else "selfcheck.json")
    output = work / ("selfcheck-cutout.log" if cutout else "selfcheck.log")
    # the cutout mode also checks HTTPS to the model's download server, the connection the
    # program makes on first run (it failed on macOS when the program shipped without certificates)
    cmd = [str(program), "selfcheck"] + (["--cutout", "--https"] if cutout else []) + ["--out", str(out_file)]
    log(f"$ {program.name} {' '.join(cmd[1:])}")
    started = time.monotonic()
    proc = start(cmd, program_env(data_dir), output)
    try:
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise SmokeFailure(f"selfcheck did not finish within {timeout:.0f}s") from exc
        log(f"  exit code {code} after {time.monotonic() - started:.1f}s")
        try:
            report = json.loads(out_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SmokeFailure(f"selfcheck exited {code} and did not write a JSON report to {out_file}: {exc}") from exc
        expected = BASE_CHECKS + (("cutout", "https") if cutout else ())
        checks = report.get("checks") or {}
        log(f"  Closet version {report.get('version')!r}")
        problems = []
        for name in expected + tuple(sorted(set(checks) - set(expected))):
            entry = checks.get(name)
            if entry is None:
                log(f"  {name:<12} MISSING")
                problems.append(f"{name}: missing from report")
            elif entry.get("ok"):
                log(f"  {name:<12} ok      {entry.get('detail')}")
            else:
                log(f"  {name:<12} FAILED  {entry.get('detail')}")
                problems.append(f"{name}: {entry.get('detail')}")
        wanted_model = "ready" if cutout else "missing"
        model = (checks.get("model_state") or {}).get("detail")
        if model != wanted_model:
            problems.append(f"model_state is {model!r}, expected {wanted_model!r}")
        if expect_version and report.get("version") != expect_version:
            problems.append(f"version is {report.get('version')!r}, expected {expect_version!r}")
        if problems:
            raise SmokeFailure("selfcheck: " + "; ".join(problems))
        if code != 0:
            raise SmokeFailure(f"selfcheck reported every check ok but exited with code {code}")
        return report
    except BaseException:
        kill_tree(proc)
        dump_diagnostics(output, data_dir)
        raise
    finally:
        kill_tree(proc)


# ---------------------------------------------------------------- server
def request(method: str, url: str, body: dict | None = None, cookie: str | None = None,
            timeout: float = 30) -> tuple[int, dict, bytes]:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, method=method, data=data)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if cookie:
        req.add_header("Cookie", cookie)
    try:
        with _opener.open(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers.items()) | {"_set_cookie": resp.headers.get_all("Set-Cookie") or []}, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, {"_set_cookie": []}, exc.read()


def expect(method: str, url: str, status: int, **kwargs) -> tuple[dict, bytes]:
    try:
        got, headers, body = request(method, url, **kwargs)
    except OSError as exc:
        raise SmokeFailure(f"{method} {url} failed: {exc!r}") from exc
    if got != status:
        raise SmokeFailure(f"{method} {url} -> HTTP {got}, expected {status}: {body[:500]!r}")
    return headers, body


def as_json(method: str, url: str, body: bytes) -> dict:
    try:
        return json.loads(body)
    except ValueError as exc:
        raise SmokeFailure(f"{method} {url} returned non-JSON: {body[:300]!r}") from exc


# what a browser needs to start the page; a wrong type (a registry on Windows can map .js to
# text/plain) leaves the owner with a blank page
ASSET_TYPES = {".js": "javascript", ".css": "text/css"}


def check_assets(base: str, page: str) -> None:
    assets = sorted(set(re.findall(r'(?:src|href)="(/assets/[^"?#]+)"', page)))
    if not any(a.endswith(".js") for a in assets):
        raise SmokeFailure(f"GET / links to no script under /assets/: {page[:500]!r}")
    for path in assets:
        headers, body = expect("GET", base + path, 200)
        kind = next((v for k, v in headers.items() if k.lower() == "content-type"), "")
        wanted = ASSET_TYPES.get(os.path.splitext(path)[1])
        if not body or (wanted and wanted not in kind):
            raise SmokeFailure(f"GET {path} -> {len(body)} bytes of {kind!r}, expected some {wanted or 'content'}")
        log(f"  GET {path} -> 200, {len(body):,} bytes of {kind}")


def check_drawing(base: str, cookie: str, items: list) -> None:
    item = items[0]
    _, body = expect("GET", f"{base}/api/items/{item['id']}/illustration.svg", 200, cookie=cookie)
    if not body.startswith(b"<svg"):
        raise SmokeFailure(f"the drawing of demo item {item['id']} is not an SVG: {body[:200]!r}")
    log(f"  GET /api/items/<demo item>/illustration.svg -> 200, {len(body):,} bytes of SVG")


def check_migrations(data_dir: Path, migrations: Path, report: dict) -> None:
    numbers = sorted(int(p.name.split("_", 1)[0]) for p in migrations.glob("*.sql"))
    if not numbers:
        raise SmokeFailure(f"no migrations found in {migrations} (pass --migrations DIR)")
    detail = str((report.get("checks", {}).get("database") or {}).get("detail"))
    found = re.search(r"(\d+) migration", detail)
    if not found or int(found.group(1)) != len(numbers):
        raise SmokeFailure(f"the program has {found.group(1) if found else 'no'} migration(s) bundled, "
                           f"the repository has {len(numbers)} ({detail!r})")
    latest = numbers[-1]
    for name, path in (("main", data_dir / "closet.db"), ("demo", data_dir / "demo" / "closet.db")):
        if not path.is_file():
            raise SmokeFailure(f"no {name} closet database at {path}")
        conn = sqlite3.connect(path)
        try:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        finally:
            conn.close()
        if version != latest:
            raise SmokeFailure(f"the {name} closet is at migration {version}, expected the latest, {latest}")
    log(f"  migrations: {len(numbers)} bundled; main and demo closets at {latest}, the latest")


def run_server(program: Path, data_dir: Path, work: Path, startup_timeout: float, quit_timeout: float,
               expect_version: str | None) -> None:
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    output = work / "server.log"
    cmd = [str(program), "--no-browser", "--no-tray", "--port", str(port)]
    log(f"$ {program.name} {' '.join(cmd[1:])}")
    proc = start(cmd, program_env(data_dir), output)
    try:
        _drive_server(proc, base, data_dir, startup_timeout, quit_timeout, expect_version)
    except BaseException:
        kill_tree(proc)
        dump_diagnostics(output, data_dir)
        raise
    finally:
        kill_tree(proc)


def _drive_server(proc: subprocess.Popen, base: str, data_dir: Path, startup_timeout: float, quit_timeout: float,
                  expect_version: str | None) -> None:
    started = time.monotonic()
    health = None
    last_error = "no answer yet"
    while time.monotonic() - started < startup_timeout:
        code = proc.poll()
        if code is not None:
            raise SmokeFailure(f"the program exited with code {code} before /api/health answered")
        try:
            status, _, body = request("GET", base + "/api/health", timeout=3)
            if status == 200:
                health = json.loads(body)
                break
            last_error = f"HTTP {status}: {body[:200]!r}"
        except (OSError, ValueError) as exc:
            last_error = repr(exc)
        time.sleep(0.5)
    if health is None:
        raise SmokeFailure(f"/api/health did not answer within {startup_timeout:.0f}s (last error: {last_error})")
    log(f"  GET /api/health after {time.monotonic() - started:.1f}s: {json.dumps(health)}")
    wanted = {"app": "closet", "status": "ok", "model_state": "missing", "setup_required": True}
    if expect_version:
        wanted["version"] = expect_version
    wrong = {k: health.get(k) for k, v in wanted.items() if health.get(k) != v}
    if wrong:
        raise SmokeFailure(f"/api/health has {wrong}, expected {wanted}")

    _, body = expect("GET", base + "/", 200)
    page = body.decode("utf-8", "replace")
    if 'id="root"' not in page:
        raise SmokeFailure(f'GET / is not the built page (no id="root"): {page[:300]!r}')
    log(f'  GET / -> 200, built page ({len(body)} bytes, has id="root")')
    check_assets(base, page)

    headers, _ = expect("POST", base + "/api/setup", 204, body={"passphrase": PASSPHRASE})
    cookies = [c.split(";", 1)[0].strip() for c in headers["_set_cookie"]]
    cookie = next((c for c in cookies if c.startswith("closet_session=") and len(c) > len("closet_session=")), None)
    if not cookie:
        raise SmokeFailure(f"POST /api/setup gave no closet_session cookie (Set-Cookie: {headers['_set_cookie']!r})")
    log("  POST /api/setup -> 204 with a session cookie")

    _, body = expect("GET", base + "/api/items", 200, cookie=cookie)
    log(f"  GET /api/items -> 200, {len(as_json('GET', '/api/items', body).get('items', []))} items in the main closet")

    _, body = expect("GET", base + "/api/tagging", 200, cookie=cookie, timeout=30)
    tagging = as_json("GET", "/api/tagging", body)
    if tagging.get("order") != ["plan", "api"] or [r.get("id") for r in tagging.get("routes") or []] != ["plan", "api"]:
        raise SmokeFailure(f"/api/tagging has order {tagging.get('order')!r}, expected the plan then the API key")
    log("  GET /api/tagging -> 200, routes " + ", ".join(f"{r['id']}={'available' if r.get('available') else 'unavailable'}"
                                                         for r in tagging["routes"]))

    expect("POST", base + "/api/profile", 200, body={"profile": "demo"}, cookie=cookie, timeout=120)
    _, body = expect("GET", base + "/api/items", 200, cookie=cookie)
    count = len(as_json("GET", "/api/items", body).get("items") or [])
    if count != DEMO_ITEMS:
        raise SmokeFailure(f"demo closet has {count} items, expected {DEMO_ITEMS}")
    log(f"  POST /api/profile demo -> GET /api/items: {count} items")
    check_drawing(base, cookie, as_json("GET", "/api/items", body)["items"])

    expect("POST", base + "/api/quit", 202, cookie=cookie)
    log("  POST /api/quit -> 202")
    stop = time.monotonic()
    try:
        code = proc.wait(timeout=quit_timeout)
    except subprocess.TimeoutExpired as exc:
        raise SmokeFailure(f"the program was still running {quit_timeout:.0f}s after POST /api/quit") from exc
    log(f"  exited with code {code} after {time.monotonic() - stop:.1f}s")
    if code != 0:
        raise SmokeFailure(f"the program exited with code {code} after /api/quit, expected 0")

    if not (data_dir / "closet.db").is_file():
        raise SmokeFailure(f"no closet.db in the data folder {data_dir}")
    if (data_dir / "closet.lock").exists():
        raise SmokeFailure(f"closet.lock was left behind in {data_dir}")
    log("  data folder has closet.db and no closet.lock")


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description="Smoke test for the built Closet program.")
    ap.add_argument("program", type=Path, help="the built executable (macOS: Closet.app/Contents/MacOS/Closet)")
    ap.add_argument("--cutout", action="store_true", help="run the background-removal check instead")
    ap.add_argument("--model", type=Path, help="isnet-general-use.onnx (required with --cutout)")
    ap.add_argument("--expect-version", help="require this version in the selfcheck report and /api/health")
    ap.add_argument("--migrations", type=Path, default=MIGRATIONS,
                    help="the repository's migrations folder (default: backend/closet/migrations next to this script)")
    ap.add_argument("--startup-timeout", type=float, default=120.0)
    ap.add_argument("--quit-timeout", type=float, default=30.0)
    ap.add_argument("--selfcheck-timeout", type=float, default=300.0)
    args = ap.parse_args()

    program = args.program.resolve()
    if args.cutout and (args.model is None or not args.model.is_file()):
        print(f"SMOKE TEST FAILED: --cutout needs --model pointing at the model file (got {args.model})", flush=True)
        return 1
    if not program.is_file():
        print(f"SMOKE TEST FAILED: program not found: {program}", flush=True)
        return 1
    mode = "cutout" if args.cutout else "default"
    log(f"program: {program} ({program.stat().st_size:,} bytes), mode: {mode}")

    work = Path(tempfile.mkdtemp(prefix="closet-smoke-"))
    data_dir = work / "data"
    data_dir.mkdir()
    log(f"data folder: {data_dir}")
    try:
        if args.cutout:
            models = data_dir / "models"
            models.mkdir()
            shutil.copyfile(args.model, models / "isnet-general-use.onnx")
            log(f"copied {args.model.name} ({args.model.stat().st_size:,} bytes) into the data folder")
            run_selfcheck(program, data_dir, work, True, args.selfcheck_timeout, args.expect_version)
        else:
            report = run_selfcheck(program, data_dir, work, False, args.selfcheck_timeout, args.expect_version)
            run_server(program, data_dir, work, args.startup_timeout, args.quit_timeout, args.expect_version)
            check_migrations(data_dir, args.migrations, report)
    except SmokeFailure as failure:
        print(f"SMOKE TEST FAILED ({mode}): {failure}", flush=True)
        return 1
    except KeyboardInterrupt:
        print("SMOKE TEST INTERRUPTED (processes were killed)", flush=True)
        return 1
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(f"SMOKE TEST PASSED ({mode})", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
