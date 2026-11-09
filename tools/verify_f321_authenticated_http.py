"""Verify F321 login/dashboard/API/logout without logging credential or cookie.

Default mode only describes the gate. --execute is a separate owner-authorized
HTTP session check; it changes no password, firmware, radio or boot setting.
It is deliberately outside the sealed flash executor review.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from http.client import HTTPConnection
from http.cookies import SimpleCookie
import json
from pathlib import Path
import re
from urllib.parse import urlencode

import f321_execution_contract as contract


DEVICE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary"
PASSWORD = DEVICE / "web_password.txt"
PASSWORD_HASH = DEVICE / "web_password.sha256"


def private_password(path: Path = PASSWORD, hash_path: Path = PASSWORD_HASH) -> str:
    value = path.read_text(encoding="utf-8").rstrip("\r\n")
    expected = hash_path.read_text(encoding="ascii").strip()
    if not value or not re.fullmatch(r"[0-9a-f]{64}", expected) or hashlib.sha256(value.encode("utf-8")).hexdigest() != expected:
        raise ValueError("Private login credential failed its local identity check")
    return value


def request(path: str, body: bytes | None = None, cookie: str | None = None):
    if path not in {"/index.cgi", "/dashboard.cgi", "/logout.cgi", "/api/v1/frontend", "/api/v1/session"}:
        raise ValueError("HTTP endpoint outside the session verification allowlist")
    headers = {"Cache-Control": "no-cache", "Content-Type": "application/x-www-form-urlencoded"}
    if cookie:
        headers["Cookie"] = cookie
    connection = HTTPConnection(contract.HOST, 80, timeout=10)
    try:
        connection.request("POST" if body is not None else "GET", path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, {name.lower(): value for name, value in response.getheaders()}, response.read(300_000)
    finally:
        connection.close()


def verify_session(password: str, expected_html: bytes, expected_bundle: dict, fetch=request) -> dict:
    checks: dict[str, bool] = {}
    cookie = None
    error = None
    step = "login-page"
    def check(name: str, passed: bool):
        checks[name] = bool(passed)
        if not passed:
            raise ValueError("Session verification check failed")
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
        check("session_cookie", cookie is not None and bool(session["httponly"]) and session["samesite"].lower() == "strict" and session["path"] == "/" and not session["secure"])
        step = "dashboard"
        status, headers, data = fetch("/dashboard.cgi", cookie=cookie)
        check("authenticated_dashboard_exact_bytes", status == 200 and data == expected_html)
        check("dashboard_headers", headers.get("cache-control") == "no-store" and "script-src 'self'" in headers.get("content-security-policy", ""))
        step = "frontend-api"
        status, _, data = fetch("/api/v1/frontend", cookie=cookie)
        frontend = json.loads(data)
        check("authenticated_frontend_bundle", status == 200 and frontend.get("schema") == "lyoko.api.frontend/v1" and frontend.get("asset_layout") == "split-v1" and frontend.get("bundle") == expected_bundle)
        step = "session-api"
        status, _, data = fetch("/api/v1/session", cookie=cookie)
        session_api = json.loads(data)
        check("authenticated_session_api", status == 200 and session_api.get("schema") == "lyoko.api.session/v1" and session_api.get("authenticated") is True)
    except Exception as failure:
        # Never put response bodies, headers, form data or exception arguments
        # into evidence: those could contain a credential/session identifier.
        error = {"step": step, "type": type(failure).__name__}
    finally:
        password = ""
        if cookie is not None:
            try:
                status, headers, _ = fetch("/logout.cgi", cookie=cookie)
                check("logout", status == 302 and headers.get("location") == "/index.cgi" and "Max-Age=0" in headers.get("set-cookie", ""))
                status, _, _ = fetch("/api/v1/session", cookie=cookie)
                check("session_invalid_after_logout", status == 403)
                status, headers, _ = fetch("/dashboard.cgi", cookie=cookie)
                check("dashboard_protected_after_logout", status == 302 and headers.get("location") == "/index.cgi")
            except Exception as failure:
                error = error or {"step": "logout-verification", "type": type(failure).__name__}
        cookie = None
    return {"status": "PASS_AUTHENTICATED_HTTP_SESSION" if not error and checks and all(checks.values()) else "FAIL",
            "checks": checks, "error": error, "credential_logged": False, "cookie_logged": False,
            "session_logout_verified": checks.get("session_invalid_after_logout") is True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({"mode": "dry-run", "target": contract.HOST, "transport": "HTTP/80",
                          "credential_file_present": PASSWORD.is_file(), "credential_hash_file_present": PASSWORD_HASH.is_file(),
                          "endpoints": ["POST /index.cgi", "GET /dashboard.cgi", "GET /api/v1/frontend", "GET /api/v1/session", "GET /logout.cgi"],
                          "network_access": False, "credential_read": False, "hardware_actions_performed": False}))
        return 0
    if args.output_dir is None:
        parser.error("--execute requires a new evidence directory")
    contract.validate_sealed_inputs()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    bundle = contract.read_json(contract.PACKAGE / "overlay/etc/lyoko/web-next.json")
    html = (contract.PACKAGE / "overlay/usr/share/openmitrastar/web/dashboard.html").read_bytes()
    result = verify_session(private_password(), html, bundle)
    result.update(schema="openmitrastar.f321-authenticated-http/v1", generated_at_utc=datetime.now(timezone.utc).isoformat(),
                  host=contract.HOST, transport="HTTP/80", ui_build_id=bundle["build_id"],
                  session_action="normal CGI login/logout; temporary session in RAM", password_changed=False,
                  radio_mutation=False, flash=False, script_sha256=contract.digest(Path(__file__)),
                  not_proven=["browser JavaScript execution", "HTTPS/TLS", "physical Wi-Fi traffic"])
    (args.output_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS_AUTHENTICATED_HTTP_SESSION" else 1


if __name__ == "__main__":
    raise SystemExit(main())
