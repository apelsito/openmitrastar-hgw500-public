#!/usr/bin/env python3
"""Recover the exact F314 presentation/assets and generate static TSX markup.

The legacy controller is retained explicitly during the incremental TSX port.
This reads a local pinned firmware image; it never connects to a router.
"""
from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import posixpath
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "work/lyoko-web-next"
IMAGE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f314-device-bound/openmitrastar-linux510-f314-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.rootfs.squashfs"
PIN = "ee2c7a63ee738382ba8eaf813cfd725e64e52ce0686bfbf83129a78dcf323cce"
DISTRO = "podman-mem9-tidb"
STYLES = {"app.css": "LYOKO_UI_APP_CSS_SHA256", "layout-fixes.css": "LYOKO_UI_LAYOUT_FIXES_CSS_SHA256",
          "capabilities.css": "LYOKO_UI_CAPABILITIES_CSS_SHA256", "f313-console.css": "LYOKO_UI_F313_CSS_SHA256"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
ATTRS = {"for": "htmlFor", "tabindex": "tabIndex", "maxlength": "maxLength", "minlength": "minLength",
         "autocomplete": "autoComplete", "autofocus": "autoFocus", "readonly": "readOnly", "spellcheck": "spellCheck"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_member(name):
    image = "/mnt/" + IMAGE.drive[0].lower() + "/" + IMAGE.as_posix()[3:]
    result = subprocess.run(["wsl.exe", "-d", DISTRO, "-u", "root", "-e", "unsquashfs", "-cat", image, name],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return result.stdout


class Markup(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_body = False
        self.skip = False
        self.parts = []
        self.media = set()
        self.ids = []

    def handle_starttag(self, tag, attrs):
        if tag == "body": self.in_body = True; return
        if not self.in_body: return
        if tag == "script": self.skip = True; return
        if self.skip: return
        encoded = []
        for key, value in attrs:
            if key.startswith("on") or key == "style": raise ValueError(f"unexpected inline behavior: {key}")
            if key == "src" and value: self.media.add(value)
            if key == "id": self.ids.append(value)
            key = ATTRS.get(key, key)
            if value is None: encoded.append(key)
            elif key in {"tabIndex", "maxLength", "minLength", "rows", "cols"}: encoded.append(f"{key}={{{int(value)}}}")
            else: encoded.append(key + "={" + json.dumps(value, ensure_ascii=False) + "}")
        self.parts.append("<" + tag + (" " + " ".join(encoded) if encoded else "") + (" />" if tag in VOID else ">"))

    def handle_endtag(self, tag):
        if tag == "body": self.in_body = False; return
        if tag == "script": self.skip = False; return
        if self.in_body and not self.skip and tag not in VOID: self.parts.append("</" + tag + ">")

    def handle_data(self, data):
        if self.in_body and not self.skip and data: self.parts.append("{" + json.dumps(data, ensure_ascii=False) + "}")


def main():
    if digest(IMAGE.read_bytes()) != PIN: raise ValueError("F314 rootfs hash mismatch")
    env = dict(line.split("=", 1) for line in read_member("etc/lyoko/frontend.env").decode().splitlines() if "=" in line)
    html = read_member("usr/share/openmitrastar/web/dashboard.html")
    if digest(html) != env["LYOKO_UI_DASHBOARD_HTML_SHA256"]: raise ValueError("dashboard hash mismatch")
    parser = Markup(); parser.feed(html.decode("utf-8"))
    if len(parser.ids) != len(set(parser.ids)): raise ValueError("duplicate classic DOM IDs")
    source = APP / "src/classic"
    source.mkdir(parents=True, exist_ok=True)
    records = []
    def save(path, data, origin):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        records.append({"path": path.relative_to(APP).as_posix(), "origin": origin, "sha256": digest(data), "bytes": len(data)})
    markup = "// Generated from the pinned F314 HTML. Edit its generator, not the DOM by hand.\nexport default function ClassicMarkup() { return <>\n" + "".join(parser.parts) + "\n</>; }\n"
    save(source / "ClassicMarkup.tsx", markup.encode(), "generated-from-F314-HTML")
    save(APP / "reference/classic.html", html, "usr/share/openmitrastar/web/dashboard.html")
    controller = read_member("www/app.js")
    if digest(controller) != env["LYOKO_UI_APP_JS_SHA256"]: raise ValueError("controller hash mismatch")
    save(source / "controller.js", controller, "www/app.js")
    save(source / "controller.d.ts", b"export {};\n", "module declaration only; controller remains legacy JavaScript")
    assets = set(parser.media) | {"/assets/movistar-m.png"}
    for name, field in STYLES.items():
        data = read_member("www/" + name)
        if digest(data) != env[field]: raise ValueError(f"stylesheet hash mismatch: {name}")
        save(source / name, data, "www/" + name)
        for url in re.findall(r"url\(\s*['\"]?([^)'\"]+)", data.decode("utf-8")):
            if not url.startswith("data:"): assets.add("/" + posixpath.normpath(posixpath.join(posixpath.dirname(name), url.lstrip("/"))))
    for url in sorted(assets):
        relative = url.removeprefix("/").split("?", 1)[0]
        if ".." in Path(relative).parts or not relative.startswith(("assets/", "branding/", "font/", "img/")):
            raise ValueError(f"unexpected public asset: {url}")
        save(APP / "public" / relative, read_member("www/" + relative), "www/" + relative)
    save(APP / "reference/classic-provenance.json", (json.dumps({"source_rootfs_sha256": PIN, "source_dashboard_sha256": digest(html),
         "dom_ids": parser.ids, "files": records, "controller_migration": "legacy retained; typed modules are separate work in progress"}, indent=2) + "\n").encode(), "extraction manifest")
    print(json.dumps({"status": "PASS", "files": len(records), "dom_ids": len(parser.ids), "source": PIN,
                      "logos": [url for url in sorted(assets) if "logo" in url]}, indent=2))


if __name__ == "__main__": main()
