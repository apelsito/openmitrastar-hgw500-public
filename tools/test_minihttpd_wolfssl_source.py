from pathlib import Path

import pytest
from build_minihttpd_wolfssl_trial import SOURCE_SHA, adapt_source, digest, patch_tls_environment

SOURCE = Path(__file__).resolve().parents[1] / "work/sources/Quantenna-GPL/buildroot/package/zminihttpd/mini_httpd-1.19/mini_httpd.c"


def test_compatibility_header_and_failure_guards_are_explicit():
    original = SOURCE.read_bytes()
    assert digest(original) == SOURCE_SHA
    adapted = adapt_source(original)
    assert b"#include <wolfssl/options.h>" in adapted
    assert b"#include <openssl/ssl.h>" not in adapted
    assert b"if ( SSL_accept( ssl ) <= 0 )" in adapted
    assert b"SSL_set_fd( ssl, conn_fd ) != 1" in adapted
    assert adapted.index(b"ssl_ctx == (SSL_CTX*) 0") < adapted.index(b"SSL_CTX_use_certificate_file")


@pytest.mark.parametrize("marker", [b"if ( SSL_accept( ssl ) == 0 )", b"SSL_set_fd( ssl, conn_fd );"])
def test_changed_source_is_not_partially_patched(marker):
    with pytest.raises(ValueError):
        adapt_source(SOURCE.read_bytes().replace(marker, b"changed"))


def test_cgi_transport_flag_comes_only_from_server_tls_state():
    adapted = adapt_source(SOURCE.read_bytes())
    assert adapted.count(b'"HTTPS=on"') == 1
    segment = adapted.split(b'"SERVER_PROTOCOL=HTTP/1.0";', 1)[1].split(b'#endif /* USE_SSL */', 1)[0]
    assert b'if ( do_ssl' in segment and b'&& doing_ssl' in segment
    assert b'HTTP_' not in segment and b'getenv' not in segment
    with pytest.raises(ValueError, match="unexpected CGI transport"):
        patch_tls_environment(adapted)
