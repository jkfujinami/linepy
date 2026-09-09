#!/usr/bin/env python3
"""Pull LINE's primary-device auth/refresh token off a connected Android
device and write a ready-to-use linepy storage file, with no root.

How it works: the token lives in the app's androidx EncryptedSharedPreferences
(`com_linecorp_legy_auth_credentials`), whose values are AES-GCM-encrypted
under a key sealed in AndroidKeyStore. That key can only be *used* (not
exported) -- but it can be used by code running as the app's own uid, and
`run-as` gives us exactly that on a debuggable build, no root required. This
script compiles a tiny Java program that asks AndroidKeyStore to decrypt the
prefs values, runs it as the app via `run-as` + `app_process`, and parses the
two JWTs it finds (access token, refresh token) plus the mid out of their
claims.

Requirements:
  - `adb` on PATH, one device attached, USB debugging enabled
  - the target LINE package is a *debuggable* build (`run-as <pkg> id` must
    work) -- true for the CHRLINE-Patch build this was written against, NOT
    for a stock Play Store install
  - `javac` and `d8` (Android SDK build-tools) on PATH or found via
    $ANDROID_HOME / $ANDROID_SDK_ROOT

Usage:
    python3 tools/device/extract_primary_token.py
    python3 tools/device/extract_primary_token.py --package jp.naver.line0.android \\
        --storage .linepy_storage.json

The account's device type (from the access token's `ctype` claim, e.g.
ANDROID) is printed at the end -- use that same string as the `device=`
argument to BaseClient/Client so linepy's PRIMARY_DEVICES token-refresh guard
applies correctly.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

DEFAULT_PACKAGE = "jp.naver.line0.android"
PREFS_NAME = "com_linecorp_legy_auth_credentials"
TEMPLATE = Path(__file__).with_name("Dump.java.tmpl")


class ExtractError(RuntimeError):
    pass


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def _sdk_roots() -> list[Path]:
    import os
    roots = []
    for env in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        v = os.environ.get(env)
        if v:
            roots.append(Path(v))
    # Common default install locations, checked even when the env vars
    # (which e.g. Android Studio sets per-shell-profile, not globally)
    # aren't set in the current shell.
    roots.append(Path.home() / "Library" / "Android" / "sdk")  # macOS
    roots.append(Path.home() / "Android" / "Sdk")               # Linux
    return [r for r in roots if r.is_dir()]


def find_tool(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    for root in _sdk_roots():
        for candidate in sorted(root.glob(f"build-tools/*/{name}"), reverse=True):
            if candidate.exists():
                return str(candidate)
    raise ExtractError(
        f"'{name}' not found on PATH and no build-tools match under "
        f"$ANDROID_HOME, $ANDROID_SDK_ROOT, or the default SDK location. "
        f"Install Android SDK build-tools (e.g. via Android Studio's SDK Manager)."
    )


def adb(args: list[str], **kw) -> subprocess.CompletedProcess:
    return run(["adb", *args], **kw)


def require_device() -> None:
    r = adb(["get-state"])
    if r.returncode != 0 or "device" not in r.stdout:
        raise ExtractError(
            "no adb device attached (or device unauthorized). "
            "Connect via USB, enable USB debugging, and accept the RSA prompt."
        )


def require_debuggable(package: str) -> None:
    r = adb(["shell", f"run-as {package} id"])
    if r.returncode != 0:
        raise ExtractError(
            f"`run-as {package}` failed:\n{r.stdout}{r.stderr}\n"
            f"This package must be a debuggable build for this technique to work."
        )


def build_dex(package: str, workdir: Path) -> Path:
    src = TEMPLATE.read_text().replace("{{PACKAGE}}", package).replace(
        "{{PREFS_NAME}}", PREFS_NAME
    )
    java_file = workdir / "Dump.java"
    java_file.write_text(src)

    javac = find_tool("javac")
    d8 = find_tool("d8")

    android_jar = _find_android_jar()
    javac_cmd = [javac, "--release", "8"]
    if android_jar:
        javac_cmd += ["-cp", str(android_jar)]
    javac_cmd += ["-d", str(workdir), str(java_file)]
    r = run(javac_cmd)
    if r.returncode != 0:
        raise ExtractError(f"javac failed:\n{r.stdout}{r.stderr}")

    r = run([d8, "--min-api", "26", "--output", str(workdir), str(workdir / "Dump.class")])
    if r.returncode != 0:
        raise ExtractError(f"d8 failed:\n{r.stdout}{r.stderr}")

    return workdir / "classes.dex"


def _find_android_jar() -> Path | None:
    for root in _sdk_roots():
        candidates = sorted(root.glob("platforms/android-*/android.jar"), reverse=True)
        if candidates:
            return candidates[0]
    return None


def run_on_device(package: str, dex_path: Path) -> str:
    device_dir = f"/data/user/0/{package}"
    remote_dex = "files/d.dex"  # relative to the app's data dir, as run-as sees it

    # A world-writable dex fails ART's "won't load a writable dex" check, so
    # push then lock it down before executing.
    push = subprocess.run(
        ["adb", "shell", f"run-as {package} sh -c 'rm -f {remote_dex} && cat > {remote_dex}'"],
        input=dex_path.read_bytes(),
    )
    if push.returncode != 0:
        raise ExtractError("failed to push dex into the app's data directory")

    chmod = adb(["shell", f"run-as {package} sh -c 'chmod 0444 {remote_dex}'"])
    if chmod.returncode != 0:
        raise ExtractError(f"chmod failed:\n{chmod.stdout}{chmod.stderr}")

    out_file = "files/extract_out.txt"
    cmd = (
        f"run-as {package} sh -c "
        f"'cd {device_dir} && CLASSPATH={device_dir}/{remote_dex} "
        f"app_process /system/bin Dump > {out_file} 2>&1'"
    )
    exec_result = adb(["shell", cmd])
    # app_process's own exit code isn't reliable through this chain; read the
    # captured output regardless and let the caller judge it.
    time.sleep(0.3)
    read = adb(["shell", f"run-as {package} sh -c 'cat {out_file}'"])
    output = read.stdout

    adb(["shell", f"run-as {package} sh -c 'rm -f {remote_dex} {out_file}'"])

    if not output.strip():
        raise ExtractError(
            "no output from the on-device decrypt step. stderr:\n"
            + (exec_result.stderr or "") + (read.stderr or "")
        )
    return output


def _b64url_decode(seg: str) -> bytes:
    seg += "=" * (-len(seg) % 4)
    return base64.urlsafe_b64decode(seg)


def jwt_claims(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("not a 3-part JWT")
    return json.loads(_b64url_decode(parts[1]))


def classify_tokens(output: str) -> dict:
    """Pick the access token, refresh token and mid out of every STR: line."""
    candidates = []
    for line in output.splitlines():
        if not line.startswith("STR:"):
            continue
        value = line[len("STR:"):]
        if re.match(r"^eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$", value):
            try:
                candidates.append((value, jwt_claims(value)))
            except Exception:
                continue

    access = next((tok for tok, c in candidates if "rtid" in c and "ati" not in c), None)
    refresh = next((tok for tok, c in candidates if "ati" in c), None)
    if not access or not refresh:
        raise ExtractError(
            f"found {len(candidates)} JWT(s) but couldn't identify both "
            f"access and refresh tokens by their claims. Is the account "
            f"actually logged in on this device right now?"
        )

    access_claims = jwt_claims(access)
    refresh_claims = jwt_claims(refresh)
    mid = access_claims.get("aid") or refresh_claims.get("aid")
    if not mid:
        raise ExtractError("tokens found but neither carries an 'aid' (mid) claim")

    return {
        "auth_token": access,
        "refresh_token": refresh,
        "mid": mid,
        "expire": access_claims.get("exp"),
        "device_type": access_claims.get("ctype"),
        "login_mode": access_claims.get("cmode"),
    }


def write_storage(path: Path, info: dict) -> None:
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text() or "{}")
        except json.JSONDecodeError:
            data = {}
    data["auth_token"] = info["auth_token"]
    data["refresh_token"] = info["refresh_token"]
    data["mid"] = info["mid"]
    if info.get("expire"):
        data["expire"] = info["expire"]
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--package", default=DEFAULT_PACKAGE, help=f"target app id (default: {DEFAULT_PACKAGE})")
    ap.add_argument("--storage", default=".linepy_storage.json", type=Path,
                     help="linepy storage file to write/update (default: .linepy_storage.json)")
    ap.add_argument("--show-secrets", action="store_true",
                     help="print full tokens to stdout (default: truncated)")
    args = ap.parse_args()

    try:
        require_device()
        require_debuggable(args.package)

        with tempfile.TemporaryDirectory() as tmp:
            dex_path = build_dex(args.package, Path(tmp))
            output = run_on_device(args.package, dex_path)

        info = classify_tokens(output)
        write_storage(args.storage, info)

    except ExtractError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    def show(tok: str) -> str:
        return tok if args.show_secrets else f"{tok[:24]}...{tok[-12:]}"

    print(f"mid:          {info['mid']}")
    print(f"device type:  {info['device_type']}  (cmode={info['login_mode']})")
    if info.get("expire"):
        print(f"access exp:   {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(info['expire']))}")
    print(f"access token: {show(info['auth_token'])}")
    print(f"refresh tok:  {show(info['refresh_token'])}")
    print(f"\nwrote {args.storage}")
    print(
        f"\nUse it with:\n"
        f"    from linepy import BaseClient\n"
        f"    client = BaseClient({info['device_type']!r}, storage={str(args.storage)!r})\n"
        f"    client.auto_login()\n"
    )
    if info.get("login_mode") == "PRIMARY":
        print(
            "Note: this is a PRIMARY-device token, so linepy disables automatic\n"
            "token refresh for it (refreshing would invalidate the session on the\n"
            "physical phone). Re-run this script to get a fresh token once it expires."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
