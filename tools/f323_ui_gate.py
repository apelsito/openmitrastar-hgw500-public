"""Exact F323 installed-file, public HTTP and authenticated HTTP/API gate.

Default is file-only. --execute performs pinned SSH reads and one normal CGI
login/logout; it never configures a radio, writes firmware or changes settings.
This is NOT a browser JavaScript, CAC, client-traffic or release acceptance gate.
Only structured, allowlisted results are persisted, never transport transcripts.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from http.client import HTTPConnection
from http.cookies import SimpleCookie
import importlib
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
from urllib.parse import urlencode

import post_flash_f321_ui_gate as previous_ui
import verify_f321_authenticated_http as previous_session


HOST = "192.168.1.90"
MAX_RESPONSE_BYTES = 300_000
CONTROLLER_PATH = "work/lyoko-web-next/src/classic/controller.js"
API_PATH = "usr/libexec/openmitrastar/om-api-v1"
RELEASE_PATH = "etc/openmitrastar/release"
HTML_PATH = "usr/share/openmitrastar/web/dashboard.html"
DFS_PATH = "/api/v1/radios/5g/dfs"
DIAGNOSTICS_PATH = "/api/v1/diagnostics"
PANEL_ENDPOINTS = (
    ("status", "/api/v1/status", "lyoko.api.status/v1"),
    ("network", "/api/v1/network", "lyoko.api.network/v1"),
    ("radio2", "/api/v1/radios/2g", "lyoko.radio.status/v1"),
    ("radio5", "/api/v1/radios/5g", "lyoko.radio.status/v1"),
    ("clients", "/api/v1/clients", "lyoko.radio.clients/v1"),
    ("hardware", "/api/v1/hardware", "lyoko.api.hardware/v1"),
    ("storage", "/api/v1/storage", "lyoko.api.storage/v1"),
    ("diagnostics", DIAGNOSTICS_PATH, "lyoko.api.diagnostics/v1"),
    ("privacy", "/api/v1/privacy", "lyoko.api.privacy/v1"),
    ("firmware", "/api/v1/firmware", "lyoko.api.firmware/v1"),
    ("packages", "/api/v1/packages", "lyoko.api.packages/v1"),
    ("capabilities", "/api/v1/capabilities", "lyoko.api.capabilities/v1"),
    ("frontend", "/api/v1/frontend", "lyoko.api.frontend/v1"),
    ("session", "/api/v1/session", "lyoko.api.session/v1"),
    ("ssh", "/api/v1/ssh", "lyoko.api.ssh/v1"),
    ("transaction", "/api/v1/config/status", "lyoko.config.status/v2"),
    ("configStore", "/api/v1/config/store", "openmitrastar.config-store/v1"),
    ("radio2Contract", "/api/v1/radios/2g?view=contract", "lyoko.radio.contract/v1"),
    ("radio5Contract", "/api/v1/radios/5g?view=contract", "lyoko.radio.contract/v1"),
)
FRONTEND_ASSET_FIELDS = {
    "dashboard_html_sha256": "LYOKO_UI_DASHBOARD_HTML_SHA256",
    "app_js_sha256": "LYOKO_UI_APP_JS_SHA256",
    "app_css_sha256": "LYOKO_UI_APP_CSS_SHA256",
    "capabilities_css_sha256": "LYOKO_UI_CAPABILITIES_CSS_SHA256",
    "layout_fixes_css_sha256": "LYOKO_UI_LAYOUT_FIXES_CSS_SHA256",
    "f313_console_css_sha256": "LYOKO_UI_F313_CSS_SHA256",
    "login_html_sha256": "LYOKO_UI_LOGIN_HTML_SHA256",
    "login_css_sha256": "LYOKO_UI_LOGIN_CSS_SHA256",
}
NOT_PROVEN = [
    "browser JavaScript execution or rendering", "HTTPS/TLS", "CAC completion",
    "NOP completion", "5 GHz TX authorization", "Wi-Fi association or traffic",
    "persistent configuration writes", "cold boot or recovery", "release acceptance",
]


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def same_json(left, right) -> bool:
    # Unlike Python equality this distinguishes false/0 and true/1.
    return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(right, sort_keys=True, allow_nan=False)


def json_object(data: bytes | str) -> dict:
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON field")
            result[key] = value
        return result

    def invalid_constant(_):
        raise ValueError("non-finite JSON number")

    result = json.loads(data, object_pairs_hook=unique_pairs, parse_constant=invalid_constant)
    if not isinstance(result, dict):
        raise ValueError("JSON response is not an object")
    return result


def validate_path(path: str) -> None:
    if (not isinstance(path, str) or not re.fullmatch(r"/[A-Za-z0-9_./-]+", path)
            or path.startswith("//") or PurePosixPath(path).as_posix() != path
            or ".." in PurePosixPath(path).parts):
        raise ValueError("unsafe installed-file path")


def validate_classic_endpoints(source: str) -> None:
    blocks = re.findall(r"async function load\(\)\s*\{.*?const endpoints\s*=\s*\{(.*?)\};\s*const names", source, re.S)
    if len(blocks) != 1:
        raise ValueError("classic panel load mapping is missing or ambiguous")
    pattern = r'([A-Za-z][A-Za-z0-9]*)\s*:\s*"([^"\r\n]+)"'
    rows = re.findall(pattern, blocks[0])
    if re.sub(pattern, "", blocks[0]).strip(" \t\r\n,"):
        raise ValueError("classic panel load mapping contains unsupported expressions")
    if rows != [(name, path) for name, path, _ in PANEL_ENDPOINTS]:
        raise ValueError("classic panel load mapping is not the exact 19-read F323 contract")


def frontend_payload(manifest: dict, bundle: dict, environment: str) -> dict:
    values = {}
    for line in environment.splitlines():
        if "=" not in line:
            raise ValueError("invalid frontend identity line")
        key, value = line.split("=", 1)
        if key in values:
            raise ValueError("duplicate frontend identity field")
        values[key] = value
    required = set(FRONTEND_ASSET_FIELDS.values()) | {
        "LYOKO_UI_VERSION", "LYOKO_UI_BUILD_ID", "LYOKO_UI_SOURCE", "LYOKO_UI_ASSET_BYTES",
    }
    if set(values) != required or not re.fullmatch(r"[0-9]+", values["LYOKO_UI_ASSET_BYTES"]):
        raise ValueError("frontend identity fields do not match F323")
    if (values["LYOKO_UI_VERSION"] != bundle["ui_version"]
            or values["LYOKO_UI_BUILD_ID"] != bundle["build_id"]
            or values["LYOKO_UI_SOURCE"] != bundle["source"]):
        raise ValueError("frontend identity does not match the bundle")
    assets = {field: values[key] for field, key in FRONTEND_ASSET_FIELDS.items()}
    if any(not re.fullmatch(r"[0-9a-f]{64}", value) for value in assets.values()):
        raise ValueError("invalid frontend asset hash")
    return {
        "ok": True, "schema": "lyoko.api.frontend/v1", "runtime": "router",
        "ui_version": bundle["ui_version"], "build_id": bundle["build_id"],
        "source": bundle["source"], "asset_bytes": int(values["LYOKO_UI_ASSET_BYTES"]),
        "firmware_version": manifest["product_version"], "assets": assets,
        "asset_layout": "split-v1", "bundle": bundle,
    }


def identity_from_documents(manifest: dict, package: dict, inventory: dict,
                            bundle: dict, environment: str, html: bytes) -> dict:
    files = {}
    for row in package["files"]:
        path = "/" + row["path"]
        validate_path(path)
        if path in files or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"]):
            raise ValueError("duplicate or invalid UI hash")
        installed = inventory["after"][row["path"]]
        if (installed["type"] != "file" or installed["sha256"] != row["sha256"]
                or installed["bytes"] != row["bytes"]):
            raise ValueError("UI package and packed rootfs inventory disagree")
        files[path] = row["sha256"]
    for path in (API_PATH, RELEASE_PATH):
        row = inventory["after"][path]
        if row["type"] != "file" or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"]):
            raise ValueError("missing installed API/release identity")
        files["/" + path] = row["sha256"]
    if files["/" + API_PATH] != manifest["change_scope"]["api_after_sha256"]:
        raise ValueError("F323 API correction is not the pinned API")
    if files.get("/" + HTML_PATH) != digest_bytes(html):
        raise ValueError("local dashboard hash does not match the package")
    if (bundle["schema"] != "lyoko.frontend.bundle/v1" or bundle["entry"] != "/dashboard.cgi"
            or bundle["build_id"] != package["build_id"]
            or bundle["ui_version"] != package["ui_version"]
            or manifest["frontend"]["build_id"] != bundle["build_id"]):
        raise ValueError("F323 frontend bundle identity mismatch")
    urls = set()
    for asset in bundle["assets"]:
        path, url = asset["path"], asset["url"]
        validate_path("/" + path)
        validate_path(url)
        expected_url = "/dashboard.cgi" if path == HTML_PATH else "/" + path.removeprefix("www/")
        if (url != expected_url or url in urls or files.get("/" + path) != asset["sha256"]
                or inventory["after"][path]["bytes"] != asset["bytes"]):
            raise ValueError("bundle asset binding mismatch")
        urls.add(url)
    if "/dashboard.cgi" not in urls or not any(url.endswith(".js") for url in urls):
        raise ValueError("bundle has no dashboard or JavaScript asset")
    frontend = frontend_payload(manifest, bundle, environment)
    if frontend["assets"]["dashboard_html_sha256"] != digest_bytes(html):
        raise ValueError("frontend dashboard identity mismatch")
    return {"files": files, "bundle": bundle, "frontend": frontend, "html": html,
            "firmware": {"version": manifest["product_version"], "build_id": manifest["firmware_build_id"]}}


def expected_identity(contract=None) -> dict:
    contract = contract or importlib.import_module("f323_execution_contract")
    manifest = contract.validate_sealed_inputs()
    package = contract.read_json(contract.PACKAGE / "manifest.json")
    inventory = contract.read_json(Path(contract.F323["directory"]) / "rootfs-inventory.json")
    bundle = contract.read_json(contract.PACKAGE / "overlay/etc/lyoko/web-next.json")
    environment = (contract.PACKAGE / "overlay/etc/lyoko/frontend.env").read_text(encoding="ascii")
    html = (contract.PACKAGE / "overlay" / HTML_PATH).read_bytes()
    validate_classic_endpoints((contract.ROOT / CONTROLLER_PATH).read_text(encoding="utf-8"))
    return identity_from_documents(manifest, package, inventory, bundle, environment, html)


def ssh_script(files: dict[str, str]) -> str:
    if not files:
        raise ValueError("empty installed-file allowlist")
    for path, sha in files.items():
        validate_path(path)
        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise ValueError("invalid installed-file hash")
    return "\n".join((
        "set -eu", "echo OMF323_FILES_BEGIN",
        "sha256sum " + " ".join(shlex.quote(path) for path in sorted(files)),
        "echo OMF323_FILES_END", "echo OMF323_FRONTEND_BEGIN",
        "OM_API_AUTH_BYPASS=1 REQUEST_METHOD=GET /usr/libexec/openmitrastar/om-api-v1 frontend",
        "echo OMF323_FRONTEND_END", "",
    ))


def verify_ssh(stdout: str, files: dict[str, str], frontend: dict) -> dict:
    text = stdout.replace("\r\n", "\n")
    match = re.fullmatch(r"OMF323_FILES_BEGIN\n(.*?)OMF323_FILES_END\nOMF323_FRONTEND_BEGIN\n(.*?)\nOMF323_FRONTEND_END\n?", text, re.S)
    if not match:
        raise ValueError("installed-file/API transcript is incomplete or ambiguous")
    observed = {}
    for line in match.group(1).splitlines():
        row = re.fullmatch(r"([0-9a-f]{64})  (/[^\r\n]+)", line)
        if not row or row[2] in observed:
            raise ValueError("invalid or duplicate installed-file row")
        observed[row[2]] = row[1]
    if observed != files:
        raise ValueError("installed UI/API/release hashes differ")
    header_block, separator, body = match.group(2).partition("\n\n")
    if not separator:
        raise ValueError("frontend CGI headers missing")
    headers = {}
    for line in header_block.splitlines():
        key, separator, value = line.partition(": ")
        if not separator or key.lower() in headers:
            raise ValueError("frontend CGI headers invalid")
        headers[key.lower()] = value
    if (headers.get("content-type") != "application/json" or headers.get("cache-control") != "no-store"
            or headers.get("status", "200 OK") != "200 OK"):
        raise ValueError("frontend CGI did not return uncached JSON")
    if not same_json(json_object(body), frontend):
        raise ValueError("frontend API is not the exact F323 payload")
    return {"installed_hashes": True, "frontend_api_exact": True, "checked_files": len(files),
            "files": files, "frontend_payload_sha256": digest_bytes(json.dumps(frontend, sort_keys=True).encode("ascii"))}


class HttpReader:
    """Fixed device, no redirect/proxy handling, bounded responses, exact routes."""

    def __init__(self, bundle: dict, *, host: str = HOST, connection_factory=HTTPConnection):
        if host != HOST:
            raise ValueError("F323 HTTP target is not the pinned HGW")
        self.host, self.connection_factory = host, connection_factory
        assets = {asset["url"] for asset in bundle["assets"] if asset["url"].startswith("/assets/")}
        for path in assets:
            validate_path(path)
        self.allowed = assets | {path for _, path, _ in PANEL_ENDPOINTS} | {
            DFS_PATH, "/index.cgi", "/dashboard.cgi", "/logout.cgi", "/dashboard.html",
        }

    def __call__(self, path: str, body: bytes | None = None, cookie: str | None = None):
        if path not in self.allowed or (body is not None and path != "/index.cgi"):
            raise ValueError("HTTP request is outside the F323 read/login/logout allowlist")
        if body is not None and (not isinstance(body, bytes) or len(body) > 4096):
            raise ValueError("invalid login form")
        if cookie is not None and not re.fullmatch(r"OMSESSION=[0-9a-f]{64}", cookie):
            raise ValueError("invalid session cookie")
        headers = {"Cache-Control": "no-cache", "Content-Type": "application/x-www-form-urlencoded"}
        if cookie is not None:
            headers["Cookie"] = cookie
        connection = self.connection_factory(self.host, 80, timeout=10)
        try:
            connection.request("POST" if body is not None else "GET", path, body=body, headers=headers)
            response = connection.getresponse()
            data = response.read(MAX_RESPONSE_BYTES + 1)
            if len(data) > MAX_RESPONSE_BYTES:
                raise ValueError("HTTP response exceeds the bounded read")
            return response.status, {key.lower(): value for key, value in response.getheaders()}, data
        finally:
            connection.close()


def response_json(status: int, headers: dict, data: bytes) -> dict:
    mime = headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if status != 200 or mime != "application/json":
        raise ValueError("API did not return HTTP 200 JSON")
    payload = json_object(data)
    if payload.get("ok") is False or "error" in payload:
        raise ValueError("API returned an error payload")
    return payload


def verify_config_store(payload: dict) -> dict:
    if payload.get("schema") != "openmitrastar.config-store/v1":
        raise ValueError("config/store schema mismatch")
    fields = ("enabled", "store_ready", "active_valid", "boot_consumer", "apply_on_boot", "secrets")
    if any(payload.get(field) is not False for field in fields):
        raise ValueError("config/store disabled persistence contract changed")
    if payload.get("active_slot") != "" or payload.get("format") != "jffs2-ab":
        raise ValueError("config/store slot/format contract changed")
    for field in ("persistent", "persistent_writes_enabled", "persistent_config_writes", "writable"):
        if field in payload and payload[field] is not False:
            raise ValueError("config/store unexpectedly reports persistent authority")
    return {"schema": "openmitrastar.config-store/v1", "http_200_json": True,
            "persistent_writes_enabled": False, "disabled_fields_verified": list(fields)}


def verify_panel(name: str, payload: dict, identity: dict) -> None:
    expected = next(schema for entry, _, schema in PANEL_ENDPOINTS if entry == name)
    if payload.get("schema") != expected:
        raise ValueError("panel schema mismatch")
    if name != "configStore" and payload.get("ok") is not True:
        raise ValueError("panel did not report success")
    if name in {"radio2", "radio2Contract", "radio5", "radio5Contract"}:
        band = "2g" if name.startswith("radio2") else "5g"
        if payload.get("id") != band:
            raise ValueError("radio panel identity mismatch")
    if name == "frontend" and not same_json(payload, identity["frontend"]):
        raise ValueError("authenticated frontend payload mismatch")
    if name == "session" and payload.get("authenticated") is not True:
        raise ValueError("API session is not authenticated")
    if name == "firmware":
        if any(payload.get(key) != value for key, value in identity["firmware"].items()):
            raise ValueError("firmware release identity mismatch")
        if payload.get("active_slot") != "mtd4/linux_live" or payload.get("firmware_write_api") is not False:
            raise ValueError("firmware slot/write boundary mismatch")
    if name == "privacy" and any(payload.get(key) is not False for key in (
            "firmware_write_api", "persistent_config_writes", "persistent_package_writes")):
        raise ValueError("privacy write boundary mismatch")
    if name == "configStore":
        verify_config_store(payload)


def verify_dfs_alias(payload: dict) -> None:
    if (payload.get("ok") is not True or payload.get("schema") != "lyoko.radio.status/v1"
            or payload.get("id") != "5g"):
        raise ValueError("DFS endpoint is not the explicit legacy 5 GHz status alias")


def verify_legacy_dfs(payload: dict) -> dict:
    dfs = payload.get("dfs")
    allowed = {"lyoko.radio.dfs/v1", "lyoko.api.radar-native/v1", "lyoko.api.radar-shadow/v1"}
    if (payload.get("ok") is not True or payload.get("schema") != "lyoko.api.diagnostics/v1"
            or not isinstance(dfs, dict) or dfs.get("ok") is not True or dfs.get("schema") not in allowed):
        raise ValueError("diagnostics did not publish recognized legacy DFS")
    if any("simulation" in row and row["simulation"] is not False for row in (payload, dfs)):
        raise ValueError("simulated DFS is not physical HTTP/API acceptance")
    # Match F323's legacy normalization: raw legacy CAC/TX claims have no
    # authority. Do not copy channel identifiers or arbitrary backend fields.
    return {"kind": "legacy", "endpoint": DIAGNOSTICS_PATH, "recognized_schema": dfs["schema"],
            "cac": {"state": "unknown", "active": None, "remaining_seconds": None},
            "nop": {"active": None, "complete": False, "entries": []},
            "detector_running": None, "detector_liveness": None, "tx_authorized": None,
            "physical_radio_acceptance": False}


def verify_authenticated_session(password: str, identity: dict, fetch) -> dict:
    checks, panel_reads, errors = {}, [], []
    cookie, form, step = None, b"", "login-page"
    store_result, dfs_result = None, None

    def check(name: str, passed: bool) -> None:
        checks[name] = bool(passed)
        if not passed:
            raise ValueError("HTTP/API check failed")

    def failure(where: str, error: Exception) -> None:
        # Exception text may contain a password, cookie, MAC or response body.
        errors.append({"step": where, "type": type(error).__name__})

    try:
        status, _, data = fetch("/index.cgi")
        check("login_page", status == 200 and b"login_password" in data)
        step = "login"
        form = urlencode({"login_password": password}).encode("utf-8")
        password = ""
        status, headers, _ = fetch("/index.cgi", form)
        form = b""
        jar = SimpleCookie()
        jar.load(headers.get("set-cookie", ""))
        session = jar.get("OMSESSION")
        if session and re.fullmatch(r"[0-9a-f]{64}", session.value):
            cookie = "OMSESSION=" + session.value
        check("login_redirect", status == 302 and headers.get("location") == "/dashboard.cgi")
        check("session_cookie", cookie is not None and bool(session["httponly"])
              and session["samesite"].lower() == "strict" and session["path"] == "/" and not session["secure"])
        step = "dashboard"
        status, headers, data = fetch("/dashboard.cgi", cookie=cookie)
        check("authenticated_dashboard_exact_bytes", status == 200 and data == identity["html"])
        check("dashboard_headers", headers.get("cache-control") == "no-store"
              and "script-src 'self'" in headers.get("content-security-policy", ""))
        for name, path, schema in PANEL_ENDPOINTS:
            step = "panel:" + name
            row = {"name": name, "path": path, "expected_schema": schema, "passed": False}
            try:
                status, headers, data = fetch(path, cookie=cookie)
                row.update(http_status=status, response_bytes=len(data))
                payload = response_json(status, headers, data)
                verify_panel(name, payload, identity)
                if name == "configStore":
                    store_result = verify_config_store(payload)
                row["passed"] = True
            except Exception as error:
                failure(step, error)
            checks["panel:" + name] = row["passed"]
            panel_reads.append(row)
        step = "dfs-legacy-status-alias"
        status, headers, data = fetch(DFS_PATH, cookie=cookie)
        verify_dfs_alias(response_json(status, headers, data))
        check("dfs_explicit_legacy_status_alias", True)
        # Fetch after the alias even though load() already read diagnostics.
        # This is the exact order followed by the F323 frontend fallback.
        step = "dfs-diagnostics-fallback"
        status, headers, data = fetch(DIAGNOSTICS_PATH, cookie=cookie)
        dfs_result = verify_legacy_dfs(response_json(status, headers, data))
        check("dfs_recognized_legacy_diagnostics", True)
    except Exception as error:
        failure(step, error)
    finally:
        password, form = "", b""
        if cookie is not None:
            for action in ("logout", "session-invalid-after-logout", "dashboard-protected-after-logout"):
                try:
                    if action == "logout":
                        status, headers, _ = fetch("/logout.cgi", cookie=cookie)
                        expired = SimpleCookie()
                        expired.load(headers.get("set-cookie", ""))
                        expired_session = expired.get("OMSESSION")
                        check("logout", status == 302 and headers.get("location") == "/index.cgi"
                              and expired_session is not None and expired_session["max-age"] == "0")
                    elif action == "session-invalid-after-logout":
                        status, _, _ = fetch("/api/v1/session", cookie=cookie)
                        check("session_invalid_after_logout", status == 403)
                    else:
                        status, headers, _ = fetch("/dashboard.cgi", cookie=cookie)
                        check("dashboard_protected_after_logout", status == 302 and headers.get("location") == "/index.cgi")
                except Exception as error:
                    failure(action, error)
        cookie = None
    passed = not errors and len(panel_reads) == 19 and checks and all(checks.values())
    return {"status": "PASS_F323_AUTHENTICATED_HTTP_API" if passed else "FAIL", "checks": checks,
            "panel_reads": panel_reads, "panel_read_count": len(panel_reads), "config_store": store_result,
            "dfs_observation": dfs_result, "errors": errors, "credential_logged": False,
            "cookie_logged": False, "raw_responses_logged": False,
            "session_logout_verified": checks.get("session_invalid_after_logout") is True}


def execute_gate(identity: dict, ssh_argv: list[str], fetch, password_reader, *, ssh_runner=None) -> dict:
    result = {"status": "FAIL", "ssh_checks": None, "public_http_checks": None, "authenticated_http": None}
    step = "pinned-ssh"
    try:
        # Existing helper submits UTF-8 LF bytes, without text=True / Windows
        # CRLF translation. The runner is injectable for offline tests.
        proc = previous_ui.run_ssh(ssh_argv, ssh_script(identity["files"]),
                                   runner=ssh_runner or subprocess.run)
        if proc.returncode != 0:
            raise ValueError("pinned SSH failed")
        result["ssh_checks"] = verify_ssh(proc.stdout.decode("utf-8", "strict"), identity["files"], identity["frontend"])
        step = "public-http"

        def public_fetch(path):
            status, headers, data = fetch(path)
            return status, data, headers

        result["public_http_checks"] = previous_ui.verify_http(identity["bundle"], fetch=public_fetch)
        step = "private-credential"
        password = password_reader()
        step = "authenticated-http"
        result["authenticated_http"] = verify_authenticated_session(password, identity, fetch)
        password = ""
        if result["authenticated_http"]["status"] == "PASS_F323_AUTHENTICATED_HTTP_API":
            result["status"] = "PASS_F323_UI_HTTP_API"
    except Exception as error:
        result["error"] = {"step": step, "type": type(error).__name__}
    return result


def pinned_ssh_argv(contract) -> list[str]:
    if contract.HOST != HOST:
        raise ValueError("SSH target is not the pinned HGW")
    known_hosts = Path(contract.F323["directory"]) / contract.F323["known_hosts"]
    ssh = Path.home().drive + r"\Windows\System32\OpenSSH\ssh.exe"
    return [ssh, "-i", str(Path.home() / ".ssh/id_ed25519"), "-o", "IdentitiesOnly=yes",
            "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o",
            "UserKnownHostsFile=" + str(known_hosts), "-o", "ConnectTimeout=8", "-o", "LogLevel=ERROR",
            "root@" + HOST, "sh", "-s"]


def new_output_directory(path: Path, contract) -> Path:
    target = path.absolute()
    if any(parent.is_symlink() or getattr(parent, "is_junction", lambda: False)()
           for parent in (target, *target.parents)):
        raise ValueError("evidence path has a symlink or junction")
    target = target.resolve()
    for protected in (Path(contract.F323["directory"]), contract.PACKAGE):
        if target.is_relative_to(protected.resolve()):
            raise ValueError("evidence must be outside immutable candidate/package inputs")
    target.mkdir(parents=True, exist_ok=False)
    return target


def main(argv=None, *, contract=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    if args.execute and args.output_dir is None:
        parser.error("--execute requires a new immutable evidence directory")
    contract = contract or importlib.import_module("f323_execution_contract")
    identity = expected_identity(contract)
    result = {
        "schema": "openmitrastar.f323-ui-http-api/v1", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target_host": HOST, "candidate_sha256": contract.F323["sha256"],
        "ui_build_id": identity["bundle"]["build_id"], "files": identity["files"],
        "script_sha256": contract.digest(Path(__file__)), "hardware_actions_performed": False,
        "radio_mutation": False, "flash": False, "persistent_writes_performed": False,
        "expected_persistent_writes_enabled": False,
        "browser_javascript_tested": False, "release_eligible": False, "not_proven": NOT_PROVEN,
        "credential_logged": False, "cookie_logged": False, "raw_responses_logged": False,
    }
    if not args.execute:
        result.update(status="PASS_OFFLINE_F323_UI_HTTP_API_PLAN", mode="dry-run", network_access=False,
                      credential_read=False, panel_gets=[path for _, path, _ in PANEL_ENDPOINTS],
                      dfs_gets=[DFS_PATH, DIAGNOSTICS_PATH])
        print(json.dumps(result, indent=2))
        return 0
    output = new_output_directory(args.output_dir, contract)
    result.update(mode="execute", transport="pinned SSH and HTTP/80", network_access=True,
                  hardware_actions_performed=True,
                  session_action="normal CGI login/logout; temporary session in RAM")
    result.update(execute_gate(identity, pinned_ssh_argv(contract), HttpReader(identity["bundle"], host=contract.HOST),
                               previous_session.private_password))
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS_F323_UI_HTTP_API" else 1


if __name__ == "__main__":
    raise SystemExit(main())
