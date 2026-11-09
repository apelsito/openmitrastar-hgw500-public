from __future__ import annotations

import json
import base64
import gzip
import io
from pathlib import Path
import tarfile
import tempfile

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import lyoko_ipk
import integrate_lyoko_packages as integration


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "packages/lyoko/lyoko-sysinfo"


def private_key(path: Path) -> None:
    key = Ed25519PrivateKey.generate()
    path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))


def malicious_ipk(tmp: Path, entries: list[tarfile.TarInfo]) -> Path:
    control = lyoko_ipk.deterministic_tar_gz([
        ("control", lyoko_ipk.render_control({
            "Package": "malicious",
            "Version": "1.0",
            "Architecture": lyoko_ipk.ARCH,
            "Description": "negative test",
            "X-Lyoko-Kernel-ABI": lyoko_ipk.KERNEL_ABI,
            "X-Lyoko-Libc-ABI": "uclibc",
            "X-Lyoko-Platform": lyoko_ipk.PLATFORM,
        }), 0o644),
    ])
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for member in entries:
            payload = b"x" if member.isfile() else None
            if payload is not None:
                member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload) if payload is not None else None)
    data = io.BytesIO()
    with gzip.GzipFile(fileobj=data, mode="wb", filename="", mtime=0) as stream:
        stream.write(raw.getvalue())
    output = tmp / "malicious.ipk"
    lyoko_ipk.write_ar(output, [("debian-binary", b"2.0\n"), ("control.tar.gz", control), ("data.tar.gz", data.getvalue())])
    return output


def test_build_inspect_install_and_signed_feed() -> None:
    with tempfile.TemporaryDirectory(prefix="lyoko-ipk-") as directory:
        tmp = Path(directory)
        package = lyoko_ipk.build_package(PACKAGE, tmp / "packages")
        fields, members = lyoko_ipk.read_control(package)
        assert fields["Architecture"] == lyoko_ipk.ARCH
        assert fields["X-Lyoko-Kernel-ABI"] == lyoko_ipk.KERNEL_ABI
        assert set(members) == {"debian-binary", "control.tar.gz", "data.tar.gz"}

        installed = tmp / "root"
        lyoko_ipk.install_tree(package, installed)
        command = installed / "usr/bin/lyoko-sysinfo"
        assert command.is_file()
        with tarfile.open(fileobj=io.BytesIO(gzip.decompress(members["data.tar.gz"])), mode="r:") as archive:
            packaged = archive.getmember("./usr/bin/lyoko-sysinfo")
        assert packaged.mode == 0o755

        key = tmp / "repo.key"
        private_key(key)
        packages, signature = lyoko_ipk.build_index(tmp / "packages", tmp / "feed", key)
        public = tmp / "feed/lyoko-feed-ed25519.pub"
        lyoko_ipk.verify_index(packages, signature, public, tmp / "packages")
        assert (tmp / "feed/Packages.gz").is_file()
        index = packages.read_text(encoding="utf-8")
        assert "Filename: lyoko-sysinfo_1.0.0-1_arc700_uclibc_lyoko_v1.ipk" in index
        assert "SHA256sum:" in index


def test_build_is_deterministic() -> None:
    with tempfile.TemporaryDirectory(prefix="lyoko-ipk-") as directory:
        tmp = Path(directory)
        first = lyoko_ipk.build_package(PACKAGE, tmp / "a")
        second = lyoko_ipk.build_package(PACKAGE, tmp / "b")
        assert first.read_bytes() == second.read_bytes()


def test_rejects_foreign_abi() -> None:
    with tempfile.TemporaryDirectory(prefix="lyoko-ipk-") as directory:
        tmp = Path(directory)
        recipe = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
        recipe["architecture"] = "mipsel_24kc"
        broken = tmp / "package"
        (broken / "files").mkdir(parents=True)
        (broken / "package.json").write_text(json.dumps(recipe), encoding="utf-8")
        (broken / "files/lyoko-sysinfo").write_bytes((PACKAGE / "files/lyoko-sysinfo").read_bytes())
        with pytest.raises(ValueError, match="unsupported architecture"):
            lyoko_ipk.build_package(broken, tmp / "out")


def test_feed_signature_detects_tampering() -> None:
    with tempfile.TemporaryDirectory(prefix="lyoko-ipk-") as directory:
        tmp = Path(directory)
        lyoko_ipk.build_package(PACKAGE, tmp / "packages")
        key = tmp / "repo.key"
        private_key(key)
        packages, signature = lyoko_ipk.build_index(tmp / "packages", tmp / "feed", key)
        packages.write_bytes(packages.read_bytes() + b"tampered\n")
        with pytest.raises(ValueError, match="index hash mismatch"):
            lyoko_ipk.verify_index(packages, signature, tmp / "feed/lyoko-feed-ed25519.pub", tmp / "packages")


def test_signed_feed_integration_writes_manifest() -> None:
    with tempfile.TemporaryDirectory(prefix="lyoko-ipk-") as directory:
        tmp = Path(directory)
        package = lyoko_ipk.build_package(PACKAGE, tmp / "feed/packages")
        key = tmp / "repo.key"
        private_key(key)
        packages, signature = lyoko_ipk.build_index(tmp / "feed/packages", tmp / "feed/repository", key)
        destination = tmp / "root"
        lyoko_ipk.verify_index(packages, signature, tmp / "feed/repository/lyoko-feed-ed25519.pub", tmp / "feed/packages")
        rows = {row["Package"]: row for row in integration.read_index(packages)}
        paths = lyoko_ipk.install_tree(tmp / "feed/packages" / rows["lyoko-sysinfo"]["Filename"], destination)
        assert paths == ["/usr/bin/lyoko-sysinfo"]
        assert package.is_file()


def test_install_rejects_file_conflict() -> None:
    with tempfile.TemporaryDirectory(prefix="lyoko-ipk-") as directory:
        tmp = Path(directory)
        package = lyoko_ipk.build_package(PACKAGE, tmp / "packages")
        destination = tmp / "root"
        target = destination / "usr/bin/lyoko-sysinfo"
        target.parent.mkdir(parents=True)
        target.write_text("existing", encoding="ascii")
        with pytest.raises(ValueError, match="package destination exists"):
            lyoko_ipk.install_tree(package, destination)


@pytest.mark.parametrize(
    ("member", "message"),
    [
        (tarfile.TarInfo("../escape"), "unsafe package entry"),
        (tarfile.TarInfo("./usr/bin/tool"), "unsupported package entry"),
    ],
)
def test_rejects_traversal_and_symlink_members(member: tarfile.TarInfo, message: str) -> None:
    with tempfile.TemporaryDirectory(prefix="lyoko-ipk-") as directory:
        tmp = Path(directory)
        if "symlink" in message:
            member.type = tarfile.SYMTYPE
            member.linkname = "/etc/passwd"
        elif member.name.endswith("tool"):
            member.type = tarfile.SYMTYPE
            member.linkname = "/etc/passwd"
            message = "unsupported package entry"
        else:
            member.type = tarfile.REGTYPE
        package = malicious_ipk(tmp, [member])
        with pytest.raises(ValueError, match=message):
            lyoko_ipk.read_control(package)


def test_rejects_privileged_mode_and_duplicate_targets() -> None:
    with tempfile.TemporaryDirectory(prefix="lyoko-ipk-") as directory:
        tmp = Path(directory)
        privileged = tarfile.TarInfo("./usr/bin/tool")
        privileged.type = tarfile.REGTYPE
        privileged.mode = 0o4755
        with pytest.raises(ValueError, match="privileged package mode"):
            lyoko_ipk.read_control(malicious_ipk(tmp, [privileged]))

        first = tarfile.TarInfo("./usr/bin/tool")
        first.type = tarfile.REGTYPE
        first.mode = 0o755
        second = tarfile.TarInfo("usr/bin/tool")
        second.type = tarfile.REGTYPE
        second.mode = 0o755
        with pytest.raises(ValueError, match="duplicate package entry"):
            lyoko_ipk.read_control(malicious_ipk(tmp, [first, second]))


def test_rejects_control_field_injection_and_recipe_setuid() -> None:
    with tempfile.TemporaryDirectory(prefix="lyoko-ipk-") as directory:
        tmp = Path(directory)
        recipe = json.loads((PACKAGE / "package.json").read_text(encoding="utf-8"))
        recipe["maintainer"] = "safe\nInjected: yes"
        broken = tmp / "metadata"
        (broken / "files").mkdir(parents=True)
        (broken / "package.json").write_text(json.dumps(recipe), encoding="utf-8")
        (broken / "files/lyoko-sysinfo").write_bytes((PACKAGE / "files/lyoko-sysinfo").read_bytes())
        with pytest.raises(ValueError, match="invalid maintainer"):
            lyoko_ipk.build_package(broken, tmp / "out")

        recipe["maintainer"] = "Lyoko"
        recipe["files"][0]["mode"] = "4755"
        (broken / "package.json").write_text(json.dumps(recipe), encoding="utf-8")
        with pytest.raises(ValueError, match="privileged package mode"):
            lyoko_ipk.build_package(broken, tmp / "out")


def test_rejects_unsafe_index_filename_and_key_id() -> None:
    with tempfile.TemporaryDirectory(prefix="lyoko-ipk-") as directory:
        tmp = Path(directory)
        lyoko_ipk.build_package(PACKAGE, tmp / "packages")
        key = tmp / "repo.key"
        private_key(key)
        packages, signature = lyoko_ipk.build_index(tmp / "packages", tmp / "feed", key)
        payload = packages.read_text(encoding="utf-8").replace(
            "Filename: lyoko-sysinfo_1.0.0-1_arc700_uclibc_lyoko_v1.ipk",
            "Filename: ../outside.ipk",
        )
        packages.write_bytes(payload.encode("utf-8"))
        signature_data = json.loads(signature.read_text(encoding="ascii"))
        signature_data["sha256"] = lyoko_ipk.sha256_bytes(payload.encode("utf-8"))
        key_object = serialization.load_pem_private_key(key.read_bytes(), password=None)
        signature_data["signature"] = base64.b64encode(key_object.sign(payload.encode("utf-8"))).decode("ascii")
        signature.write_text(json.dumps(signature_data), encoding="ascii")
        with pytest.raises(ValueError, match="unsafe package filename"):
            lyoko_ipk.verify_index(packages, signature, tmp / "feed/lyoko-feed-ed25519.pub", tmp / "packages")

        packages, signature = lyoko_ipk.build_index(tmp / "packages", tmp / "feed2", key)
        signature_data = json.loads(signature.read_text(encoding="ascii"))
        signature_data["key_id"] = "0000000000000000"
        signature.write_text(json.dumps(signature_data), encoding="ascii")
        with pytest.raises(ValueError, match="repository key id mismatch"):
            lyoko_ipk.verify_index(packages, signature, tmp / "feed2/lyoko-feed-ed25519.pub", tmp / "packages")
