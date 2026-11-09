#!/usr/bin/env python3
"""Build and verify deterministic Lyoko-compatible OpenWrt IPK packages."""
from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile
import tempfile

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


ARCH = "arc700_uclibc_lyoko_v1"
KERNEL_ABI = "5.10.260-openmitrastar-radiohw"
PLATFORM = "hgw-500bna-qcv2"
EPOCH = 1785024000
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9+_.-]*$")
MAX_PACKAGE_BYTES = 16 * 1024 * 1024
MAX_CONTROL_BYTES = 256 * 1024
MAX_MEMBERS = 1024


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_target(value: str) -> PurePosixPath:
    target = PurePosixPath(value)
    if not target.is_absolute() or ".." in target.parts or target == PurePosixPath("/"):
        raise ValueError(f"unsafe package target: {value}")
    return PurePosixPath(*target.parts[1:])


def safe_archive_member(value: str) -> PurePosixPath:
    if "\\" in value:
        raise ValueError(f"unsafe package entry: {value}")
    target = PurePosixPath(value)
    if target.is_absolute() or ".." in target.parts:
        raise ValueError(f"unsafe package entry: {value}")
    parts = tuple(part for part in target.parts if part not in ("", "."))
    if not parts:
        raise ValueError(f"unsafe package entry: {value}")
    return PurePosixPath(*parts)


def single_line(value: object, field: str, maximum: int = 256) -> str:
    text = str(value)
    if not text or len(text) > maximum or "\n" in text or "\r" in text or "\0" in text:
        raise ValueError(f"invalid {field}")
    return text


def decompress_gzip_bounded(payload: bytes, maximum: int) -> bytes:
    with gzip.GzipFile(fileobj=io.BytesIO(payload), mode="rb") as stream:
        result = stream.read(maximum + 1)
    if len(result) > maximum:
        raise ValueError("compressed archive exceeds unpacked size limit")
    return result


def validated_tar(payload: bytes, *, maximum: int) -> tuple[tarfile.TarFile, list[tarfile.TarInfo]]:
    archive = tarfile.open(fileobj=io.BytesIO(decompress_gzip_bounded(payload, maximum)), mode="r:")
    members = archive.getmembers()
    if len(members) > MAX_MEMBERS:
        archive.close()
        raise ValueError("too many package entries")
    normalized: dict[str, bool] = {}
    for member in members:
        target = safe_archive_member(member.name)
        name = target.as_posix()
        if name in normalized:
            archive.close()
            raise ValueError(f"duplicate package entry: /{name}")
        if not member.isfile() and not member.isdir():
            archive.close()
            raise ValueError(f"unsupported package entry: {member.name}")
        if member.mode & 0o7000:
            archive.close()
            raise ValueError(f"privileged package mode: {member.name}")
        for existing, existing_is_dir in normalized.items():
            if name.startswith(existing + "/") and not existing_is_dir:
                archive.close()
                raise ValueError(f"package path crosses file: /{name}")
            if existing.startswith(name + "/") and not member.isdir():
                archive.close()
                raise ValueError(f"package file shadows directory: /{name}")
        normalized[name] = member.isdir()
    return archive, members


def control_fields(recipe: dict[str, object]) -> dict[str, str]:
    name = str(recipe.get("package", ""))
    version = single_line(recipe.get("version", ""), "package version")
    architecture = str(recipe.get("architecture", ""))
    description = str(recipe.get("description", "")).strip()
    if not NAME_RE.fullmatch(name):
        raise ValueError("invalid package name")
    if any(ch.isspace() for ch in version):
        raise ValueError("invalid package version")
    if architecture != ARCH:
        raise ValueError(f"unsupported architecture: {architecture}")
    if not description:
        raise ValueError("description is required")
    fields = {
        "Package": name,
        "Version": version,
        "Architecture": architecture,
        "Description": description.replace("\n", " "),
        "Maintainer": single_line(recipe.get("maintainer", "Lyoko Project"), "maintainer"),
        "X-Lyoko-Kernel-ABI": str(recipe.get("kernel_abi", KERNEL_ABI)),
        "X-Lyoko-Libc-ABI": str(recipe.get("libc_abi", "uclibc")),
        "X-Lyoko-Platform": str(recipe.get("platform", PLATFORM)),
    }
    depends = recipe.get("depends", [])
    if depends:
        if not isinstance(depends, list) or len(depends) > 16:
            raise ValueError("invalid dependency list")
        normalized_dependencies: list[str] = []
        for item in depends:
            dependency = single_line(item, "dependency")
            if not NAME_RE.fullmatch(dependency):
                raise ValueError("dependencies must be exact package names")
            if dependency == name:
                raise ValueError("package cannot depend on itself")
            if dependency in normalized_dependencies:
                raise ValueError("duplicate dependency")
            normalized_dependencies.append(dependency)
        fields["Depends"] = ", ".join(normalized_dependencies)
    if fields["X-Lyoko-Kernel-ABI"] != KERNEL_ABI:
        raise ValueError("kernel ABI mismatch")
    if fields["X-Lyoko-Libc-ABI"] != "uclibc":
        raise ValueError("libc ABI mismatch")
    if fields["X-Lyoko-Platform"] != PLATFORM:
        raise ValueError("platform mismatch")
    return fields


def render_control(fields: dict[str, str]) -> bytes:
    order = (
        "Package", "Version", "Architecture", "Maintainer", "Depends", "Installed-Size",
        "Description", "X-Lyoko-Kernel-ABI", "X-Lyoko-Libc-ABI", "X-Lyoko-Platform",
        "Filename", "Size", "SHA256sum",
    )
    known = [key for key in order if key in fields]
    extra = sorted(set(fields) - set(known))
    return ("".join(f"{key}: {fields[key]}\n" for key in known + extra)).encode("utf-8")


def deterministic_tar_gz(entries: list[tuple[str, bytes, int]]) -> bytes:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, payload, mode in sorted(entries):
            safe_target("/" + name.lstrip("./"))
            info = tarfile.TarInfo("./" + name.lstrip("./"))
            info.size = len(payload)
            info.mode = mode
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            info.mtime = EPOCH
            archive.addfile(info, io.BytesIO(payload))
    compressed = io.BytesIO()
    with gzip.GzipFile(fileobj=compressed, mode="wb", filename="", mtime=0, compresslevel=9) as stream:
        stream.write(raw.getvalue())
    return compressed.getvalue()


def write_ar(path: Path, members: list[tuple[str, bytes]]) -> None:
    with path.open("wb") as archive:
        archive.write(b"!<arch>\n")
        for name, payload in members:
            if len(name) > 15:
                raise ValueError(f"ar member name too long: {name}")
            header = (
                f"{name + '/':<16}{EPOCH:<12}{0:<6}{0:<6}{0o100644:<8o}{len(payload):<10}`\n"
            ).encode("ascii")
            if len(header) != 60:
                raise AssertionError("invalid ar header size")
            archive.write(header)
            archive.write(payload)
            if len(payload) & 1:
                archive.write(b"\n")


def read_ar(path: Path) -> dict[str, bytes]:
    data = path.read_bytes()
    if not data.startswith(b"!<arch>\n"):
        raise ValueError("not an ar archive")
    members: dict[str, bytes] = {}
    offset = 8
    while offset < len(data):
        if offset + 60 > len(data):
            raise ValueError("truncated ar header")
        header = data[offset:offset + 60]
        if header[58:60] != b"`\n":
            raise ValueError("invalid ar member header")
        name = header[:16].decode("ascii").strip().rstrip("/")
        size = int(header[48:58].decode("ascii").strip())
        start = offset + 60
        end = start + size
        if end > len(data) or name in members:
            raise ValueError("invalid ar member layout")
        members[name] = data[start:end]
        offset = end + (size & 1)
    return members


def parse_control(payload: bytes) -> dict[str, str]:
    result: dict[str, str] = {}
    current = ""
    for raw in payload.decode("utf-8", "strict").splitlines():
        if raw.startswith((" ", "\t")) and current:
            result[current] += "\n" + raw[1:]
            continue
        if ":" not in raw:
            raise ValueError("invalid control line")
        current, value = raw.split(":", 1)
        if not re.fullmatch(r"[A-Za-z0-9-]+", current) or current in result:
            raise ValueError("invalid or duplicate control field")
        result[current] = value.strip()
    return result


def read_control(ipk: Path) -> tuple[dict[str, str], dict[str, bytes]]:
    if ipk.stat().st_size > MAX_PACKAGE_BYTES:
        raise ValueError("package exceeds size limit")
    members = read_ar(ipk)
    if set(members) != {"debian-binary", "control.tar.gz", "data.tar.gz"}:
        raise ValueError("unexpected IPK members")
    if members["debian-binary"] != b"2.0\n":
        raise ValueError("unsupported IPK format")
    archive, control_members = validated_tar(members["control.tar.gz"], maximum=MAX_CONTROL_BYTES)
    with archive:
        normalized_control = {safe_archive_member(item.name).as_posix() for item in control_members}
        if normalized_control != {"control"}:
            raise ValueError("package maintainer scripts are not supported")
        control_member = next((item for item in control_members if item.name.lstrip("./") == "control"), None)
        if not control_member or not control_member.isfile():
            raise ValueError("missing control file")
        handle = archive.extractfile(control_member)
        if handle is None:
            raise ValueError("unreadable control file")
        fields = parse_control(handle.read())
    data_archive, _ = validated_tar(members["data.tar.gz"], maximum=MAX_PACKAGE_BYTES)
    data_archive.close()
    if not NAME_RE.fullmatch(fields.get("Package", "")):
        raise ValueError("invalid package name")
    if not fields.get("Version") or any(ch.isspace() for ch in fields["Version"]):
        raise ValueError("invalid package version")
    if fields.get("Architecture") != ARCH:
        raise ValueError("package architecture is not Lyoko ABI")
    if fields.get("X-Lyoko-Kernel-ABI") != KERNEL_ABI:
        raise ValueError("package kernel ABI mismatch")
    if fields.get("X-Lyoko-Libc-ABI") != "uclibc":
        raise ValueError("package libc ABI mismatch")
    if fields.get("X-Lyoko-Platform") != PLATFORM:
        raise ValueError("package platform mismatch")
    return fields, members


def build_package(package_dir: Path, output_dir: Path) -> Path:
    recipe = json.loads((package_dir / "package.json").read_text(encoding="utf-8"))
    fields = control_fields(recipe)
    entries: list[tuple[str, bytes, int]] = []
    targets: set[str] = set()
    total = 0
    for item in recipe.get("files", []):
        declared_source = package_dir / str(item["source"])
        source = declared_source.resolve()
        if declared_source.is_symlink() or package_dir.resolve() not in source.parents or not source.is_file():
            raise ValueError(f"invalid package source: {source}")
        target = safe_target(str(item["target"]))
        mode = int(str(item.get("mode", "0644")), 8)
        if mode < 0 or mode > 0o777:
            raise ValueError(f"privileged package mode: {oct(mode)}")
        normalized = target.as_posix()
        if normalized in targets:
            raise ValueError(f"duplicate package target: /{normalized}")
        targets.add(normalized)
        payload = source.read_bytes()
        total += len(payload)
        if total > MAX_PACKAGE_BYTES:
            raise ValueError("package payload exceeds size limit")
        entries.append((target.as_posix(), payload, mode))
    fields["Installed-Size"] = str((total + 1023) // 1024)
    control_entries = [("control", render_control(fields), 0o644)]
    scripts = package_dir / "control"
    if scripts.is_dir():
        if any(scripts.iterdir()):
            raise ValueError("package maintainer scripts are not supported")
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{fields['Package']}_{fields['Version']}_{ARCH}.ipk"
    write_ar(output, [
        ("debian-binary", b"2.0\n"),
        ("control.tar.gz", deterministic_tar_gz(control_entries)),
        ("data.tar.gz", deterministic_tar_gz(entries)),
    ])
    return output


def build_index(package_dir: Path, output_dir: Path, private_key_path: Path) -> tuple[Path, Path]:
    rows = []
    for ipk in sorted(package_dir.glob("*.ipk")):
        fields, _ = read_control(ipk)
        fields = dict(fields)
        fields["Filename"] = ipk.name
        fields["Size"] = str(ipk.stat().st_size)
        fields["SHA256sum"] = sha256_file(ipk)
        rows.append(render_control(fields).decode("utf-8").rstrip() + "\n")
    if not rows:
        raise ValueError("no IPK packages found")
    payload = ("\n".join(rows)).encode("utf-8")
    key = serialization.load_pem_private_key(private_key_path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("repository key must be Ed25519")
    signature = key.sign(payload)
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    output_dir.mkdir(parents=True, exist_ok=True)
    packages = output_dir / "Packages"
    packages_gz = output_dir / "Packages.gz"
    signature_path = output_dir / "Packages.sig.json"
    signature_raw_path = output_dir / "Packages.sig"
    public_path = output_dir / "lyoko-feed-ed25519.pub"
    public_raw_path = output_dir / "lyoko-feed-ed25519.raw"
    packages.write_bytes(payload)
    with packages_gz.open("wb") as handle:
        with gzip.GzipFile(fileobj=handle, mode="wb", filename="", mtime=0, compresslevel=9) as stream:
            stream.write(payload)
    public_path.write_bytes(public)
    public_raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    public_raw_path.write_bytes(public_raw)
    signature_raw_path.write_bytes(signature)
    signature_path.write_text(json.dumps({
        "schema": "lyoko.package-feed-signature/v1",
        "algorithm": "ed25519",
        "key_id": sha256_bytes(public_raw)[:16],
        "signed_file": "Packages",
        "sha256": sha256_bytes(payload),
        "signature": base64.b64encode(signature).decode("ascii"),
    }, indent=2, sort_keys=True) + "\n", encoding="ascii")
    return packages, signature_path


def verify_index(packages: Path, signature_path: Path, public_key_path: Path, package_dir: Path) -> None:
    payload = packages.read_bytes()
    signature = json.loads(signature_path.read_text(encoding="ascii"))
    if signature.get("schema") != "lyoko.package-feed-signature/v1" or signature.get("algorithm") != "ed25519" or signature.get("signed_file") != "Packages":
        raise ValueError("unsupported repository signature contract")
    if signature.get("sha256") != sha256_bytes(payload):
        raise ValueError("repository index hash mismatch")
    public = serialization.load_pem_public_key(public_key_path.read_bytes())
    if not isinstance(public, Ed25519PublicKey):
        raise ValueError("repository public key must be Ed25519")
    public_raw = public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    if signature.get("key_id") != sha256_bytes(public_raw)[:16]:
        raise ValueError("repository key id mismatch")
    public.verify(base64.b64decode(signature["signature"], validate=True), payload)
    for stanza in payload.decode("utf-8").strip().split("\n\n"):
        fields = parse_control(stanza.encode("utf-8"))
        filename = fields.get("Filename", "")
        if not filename or PurePosixPath(filename).name != filename or "\\" in filename or not filename.endswith(".ipk"):
            raise ValueError("unsafe package filename")
        ipk = package_dir / filename
        read_control(ipk)
        if ipk.stat().st_size != int(fields["Size"]) or sha256_file(ipk) != fields["SHA256sum"]:
            raise ValueError(f"package digest mismatch: {ipk.name}")


def install_tree(ipk: Path, destination: Path, *, allow_replace: bool = False) -> list[str]:
    _, members = read_control(ipk)
    if destination.is_symlink():
        raise ValueError("installation root must not be a symlink")
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not allow_replace:
        raise ValueError(f"package destination exists: {destination}")
    installed: list[str] = []
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.stage-", dir=destination.parent))
    backup = destination.with_name(f".{destination.name}.previous")
    try:
        archive, archive_members = validated_tar(members["data.tar.gz"], maximum=MAX_PACKAGE_BYTES)
        with archive:
            for member in archive_members:
                relative = safe_archive_member(member.name)
                target = staging / Path(*relative.parts)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    os.chmod(target, member.mode & 0o777)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError(f"unreadable package entry: {member.name}")
                with target.open("xb") as handle:
                    shutil.copyfileobj(source, handle)
                os.chmod(target, member.mode & 0o777)
                installed.append("/" + relative.as_posix())
        if destination.exists():
            if backup.exists():
                raise ValueError(f"stale package backup: {backup}")
            destination.replace(backup)
        staging.replace(destination)
        if backup.exists():
            shutil.rmtree(backup)
    except BaseException:
        if backup.exists() and not destination.exists():
            backup.replace(destination)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return installed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("package_dir", type=Path)
    build.add_argument("output_dir", type=Path)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("package", type=Path)
    index = commands.add_parser("index")
    index.add_argument("package_dir", type=Path)
    index.add_argument("output_dir", type=Path)
    index.add_argument("private_key", type=Path)
    verify = commands.add_parser("verify-index")
    verify.add_argument("packages", type=Path)
    verify.add_argument("signature", type=Path)
    verify.add_argument("public_key", type=Path)
    verify.add_argument("package_dir", type=Path)
    install = commands.add_parser("install-tree")
    install.add_argument("package", type=Path)
    install.add_argument("destination", type=Path)
    install.add_argument("--allow-replace", action="store_true")
    args = parser.parse_args()

    if args.command == "build":
        output = build_package(args.package_dir.resolve(), args.output_dir.resolve())
        print(json.dumps({"package": str(output), "sha256": sha256_file(output), "bytes": output.stat().st_size}, indent=2))
    elif args.command == "inspect":
        fields, members = read_control(args.package.resolve())
        print(json.dumps({"control": fields, "members": sorted(members), "sha256": sha256_file(args.package)}, indent=2))
    elif args.command == "index":
        packages, signature = build_index(args.package_dir.resolve(), args.output_dir.resolve(), args.private_key.resolve())
        print(json.dumps({"packages": str(packages), "signature": str(signature)}, indent=2))
    elif args.command == "verify-index":
        verify_index(args.packages.resolve(), args.signature.resolve(), args.public_key.resolve(), args.package_dir.resolve())
        print("LYOKO_PACKAGE_FEED_VERIFY_PASS=1")
    else:
        installed = install_tree(args.package.resolve(), args.destination.resolve(), allow_replace=args.allow_replace)
        print(json.dumps({"status": "PASS", "installed": installed}, indent=2))
        print("LYOKO_PACKAGE_INSTALL_TREE_PASS=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
