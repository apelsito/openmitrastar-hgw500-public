from __future__ import annotations

import hashlib
import json
import pytest
import verify_f321_authenticated_http as gate


def responses(fail_dashboard=False, failed_login=False):
    state = {"logout": False, "calls": []}
    bundle = {"build_id": "synthetic"}
    def fetch(path, body=None, cookie=None):
        state["calls"].append(path)
        if path == "/index.cgi":
            if body is None:
                return 200, {}, b"login_password"
            return (403, {}, b"private synthetic failure") if failed_login else (302, {"location": "/dashboard.cgi", "set-cookie": "OMSESSION=" + "a" * 64 + "; Path=/; HttpOnly; SameSite=Strict"}, b"")
        if path == "/logout.cgi":
            state["logout"] = True
            return 302, {"location": "/index.cgi", "set-cookie": "OMSESSION=deleted; Max-Age=0"}, b""
        if state["logout"]:
            return (403, {}, b"") if path == "/api/v1/session" else (302, {"location": "/index.cgi"}, b"")
        assert cookie == "OMSESSION=" + "a" * 64
        if path == "/dashboard.cgi":
            return 200, {"cache-control": "no-store", "content-security-policy": "script-src 'self'"}, b"wrong" if fail_dashboard else b"exact"
        if path == "/api/v1/frontend":
            return 200, {}, json.dumps({"schema": "lyoko.api.frontend/v1", "asset_layout": "split-v1", "bundle": bundle}).encode()
        if path == "/api/v1/session":
            return 200, {}, b'{"schema":"lyoko.api.session/v1","authenticated":true}'
        raise AssertionError(path)
    return fetch, state, bundle


def test_session_sequence_without_logging_secret_or_cookie():
    fetch, state, bundle = responses()
    report = gate.verify_session("private-synthetic-credential", b"exact", bundle, fetch)
    assert report["status"] == "PASS_AUTHENTICATED_HTTP_SESSION"
    assert state["logout"]
    text = json.dumps(report)
    assert "private-synthetic-credential" not in text and "a" * 64 not in text


def test_dashboard_mismatch_still_logs_out():
    fetch, state, bundle = responses(fail_dashboard=True)
    report = gate.verify_session("private-synthetic-credential", b"exact", bundle, fetch)
    assert report["status"] == "FAIL" and state["logout"]
    assert report["session_logout_verified"]


def test_failed_login_is_not_retried():
    fetch, state, bundle = responses(failed_login=True)
    report = gate.verify_session("private-synthetic-credential", b"exact", bundle, fetch)
    assert report["status"] == "FAIL" and state["calls"] == ["/index.cgi", "/index.cgi"]
    assert "private synthetic failure" not in json.dumps(report)


def test_private_password_preserves_spaces_and_only_removes_line_ending(tmp_path):
    value = " example "
    plain, hashed = tmp_path / "password", tmp_path / "hash"
    plain.write_bytes(value.encode() + b"\r\n")
    hashed.write_text(hashlib.sha256(value.encode()).hexdigest() + "\n", encoding="ascii")
    assert gate.private_password(plain, hashed) == value
    plain.write_text("different", encoding="ascii")
    with pytest.raises(ValueError):
        gate.private_password(plain, hashed)
