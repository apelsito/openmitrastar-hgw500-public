import pytest

from lyoko_https_profile import BINARY_PATH, CONFIG_PATH
from verify_lyoko_tls_rootfs import replace_payload


@pytest.mark.parametrize("path,mode", [
    ("../outside", 0o644), ("/etc/passwd", 0o644), ("etc/init.d/S44-oem-web", 0o755),
    (BINARY_PATH, 0o777), (CONFIG_PATH, 0o755), ("etc/minihttpd-https.conf/../passwd", 0o644),
])
def test_payload_scope_is_exactly_two_files_before_any_filesystem_action(tmp_path, path, mode):
    with pytest.raises(ValueError, match="outside the two-file delta"):
        replace_payload(tmp_path, path, b"must not be written", mode)
    assert not list(tmp_path.iterdir())
