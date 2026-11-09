"""Pinned SSH file/API identity and public HTTP/auth boundary for exact F321.

Default is file-only dry-run. --execute is invoked by the authorized promoter;
it reads through pinned SSH and HTTP and never changes radio or flash state.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import urllib.error
import urllib.request

import f321_execution_contract as contract


def expected_identity() -> tuple[dict[str, str], dict]:
    manifest = contract.validate_sealed_inputs()
    package = contract.read_json(contract.PACKAGE / "manifest.json")
    files = {"/" + row["path"]: row["sha256"] for row in package["files"]}
    release = manifest["change_scope"]["release_identity"]
    files["/" + release["path"]] = release["sha256"]
    for transform in manifest["change_scope"]["api_transform"]:
        files["/" + transform["path"]] = transform["after_sha256"]
    return files, contract.read_json(contract.PACKAGE / "overlay/etc/lyoko/web-next.json")


def ssh_script(files: dict[str, str]) -> str:
    if not files or any(not re.fullmatch(r"/[A-Za-z0-9_./-]+", path) or ".." in Path(path).parts for path in files):
        raise ValueError("unsafe or empty UI hash allowlist")
    return "\n".join(("set -eu", "echo OMF321_FILES_BEGIN", "sha256sum " + " ".join(map(shlex.quote, sorted(files))),
        "echo OMF321_FILES_END", "echo OMF321_FRONTEND_BEGIN",
        "OM_API_AUTH_BYPASS=1 REQUEST_METHOD=GET /usr/libexec/openmitrastar/om-api-v1 frontend",
        "echo OMF321_FRONTEND_END", ""))


def verify_ssh(text: str, files: dict[str, str], bundle: dict) -> dict:
    match = re.search(r"(?ms)^OMF321_FILES_BEGIN\r?\n(.*?)^OMF321_FILES_END\r?$", text)
    if not match:
        raise ValueError("UI hash transcript incomplete")
    rows = re.findall(r"(?m)^([0-9a-f]{64})\s+(/[^\r\n]+)\r?$", match.group(1))
    observed = {path.rstrip("\r"): sha for sha, path in rows}
    if len(rows) != len(files) or observed != files:
        raise ValueError("installed UI/API/release hash mismatch")
    api = re.search(r"(?ms)^OMF321_FRONTEND_BEGIN\r?\n(.*?)^OMF321_FRONTEND_END\r?$", text)
    if not api:
        raise ValueError("frontend API transcript incomplete")
    start = api.group(1).find("{")
    payload = json.loads(api.group(1)[start:])
    if payload.get("schema") != "lyoko.api.frontend/v1" or payload.get("asset_layout") != "split-v1" or payload.get("bundle") != bundle:
        raise ValueError("frontend API does not identify the exact active bundle")
    return {"installed_hashes": True, "frontend_api_bundle": True, "checked_files": len(files)}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http_read(path: str) -> tuple[int, bytes, dict]:
    if not re.fullmatch(r"/[A-Za-z0-9_./-]+", path) or ".." in Path(path).parts:
        raise ValueError("unsafe HTTP path")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request("http://" + contract.HOST + path, headers={"Cache-Control": "no-cache"})
    try:
        response = opener.open(request, timeout=10)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.code, response.read(300_000), dict(response.headers)


def verify_http(bundle: dict, fetch=http_read) -> dict:
    checks: dict[str, bool] = {}
    for asset in bundle["assets"]:
        if not asset["url"].startswith("/assets/"):
            continue
        status, data, headers = fetch(asset["url"])
        checks[asset["url"]] = status == 200 and len(data) == asset["bytes"] and hashlib.sha256(data).hexdigest() == asset["sha256"]
        content_type = next((value for key, value in headers.items() if key.lower() == "content-type"), "").split(";", 1)[0].strip().lower()
        if asset["url"].endswith(".js"):
            # F314's mini_httpd serves this legacy JavaScript MIME type. Exact
            # bytes/hashes and the authentication checks still apply unchanged.
            checks[asset["url"] + ":mime"] = content_type in {"text/javascript", "application/javascript", "application/x-javascript"}
        elif asset["url"].endswith(".css"):
            checks[asset["url"] + ":mime"] = content_type == "text/css"
    status, _, headers = fetch("/dashboard.cgi")
    location = next((value for key, value in headers.items() if key.lower() == "location"), "")
    checks["dashboard_protected"] = status in {401, 403} or status in {301, 302, 303, 307, 308} and location == "/index.cgi"
    checks["public_dashboard_absent"] = fetch("/dashboard.html")[0] == 404
    for path in ("/api/v1/status", "/api/v1/frontend"):
        checks[path + ":unauthenticated"] = fetch(path)[0] in {401, 403}
    if not checks or not all(checks.values()):
        raise ValueError("HTTP bundle/auth checks failed: " + ", ".join(key for key, ok in checks.items() if not ok))
    return checks


def run_ssh(argv: list[str], script: str, runner=subprocess.run):
    # text=True performs newline conversion on Windows stdin. BusyBox sh must
    # receive LF bytes, never CRLF commands such as "set -eu\r".
    return runner(argv, input=script.replace("\r\n", "\n").encode("utf-8"),
                  capture_output=True, timeout=60, check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    files, bundle = expected_identity()
    if not args.execute:
        print(json.dumps({"status": "PASS_OFFLINE_UI_GATE_PLAN", "target_host": contract.HOST, "files": files,
                          "ui_build_id": bundle["build_id"], "hardware_actions_performed": False}))
        return 0
    if args.output_dir is None:
        parser.error("execution needs a new immutable evidence directory")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    known_hosts = Path(contract.F321["directory"]) / contract.F321["known_hosts"]
    ssh = Path.home().drive + r"\Windows\System32\OpenSSH\ssh.exe"
    argv = [ssh, "-i", str(Path.home() / ".ssh/id_ed25519"), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=yes", "-o", "UserKnownHostsFile=" + str(known_hosts), "-o", "ConnectTimeout=8",
            "-o", "LogLevel=ERROR", "root@" + contract.HOST, "sh", "-s"]
    result = {"schema": "openmitrastar.f321-ui-postflash/v1", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "status": "FAIL", "target_host": contract.HOST, "ui_build_id": bundle["build_id"],
              "radio_mutation": False, "flash": False, "authenticated_http_session": "NOT_TESTED_BY_THIS_READ_ONLY_GATE"}
    try:
        proc = run_ssh(argv, ssh_script(files))
        stdout, stderr = proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace")
        (args.output_dir / "ssh.stdout.log").write_text(stdout, encoding="utf-8")
        (args.output_dir / "ssh.stderr.log").write_text(stderr, encoding="utf-8")
        if proc.returncode != 0:
            raise ValueError("pinned SSH UI verification failed")
        result["ssh_checks"] = verify_ssh(stdout, files, bundle)
        result["http_checks"] = verify_http(bundle)
        result["status"] = "PASS_UI_FILE_API_AND_PUBLIC_HTTP"
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        result["error"] = str(error)
    (args.output_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS_UI_FILE_API_AND_PUBLIC_HTTP" else 1


if __name__ == "__main__":
    raise SystemExit(main())
