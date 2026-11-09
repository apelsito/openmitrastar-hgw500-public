from pathlib import Path
import tarfile

import pytest
from build_wolfssl_arc700_trial import SOURCE_COMMIT, patch_options_template, patch_cmake_profile

ROOT = Path(__file__).resolve().parents[1]


def test_public_options_export_matches_single_thread_library_definition():
    with tarfile.open(ROOT / "work/sources/wolfssl-5.9.2-ac01707f.tar.gz") as source:
        template = source.extractfile(f"wolfssl-{SOURCE_COMMIT}/cmake/options.h.in").read()
    patched = patch_options_template(template)
    addition = b"#undef SINGLE_THREADED\n#cmakedefine SINGLE_THREADED\n\n#undef HAVE_SERVER_RENEGOTIATION_INFO\n#cmakedefine HAVE_SERVER_RENEGOTIATION_INFO\n\n"
    assert patched.count(addition) == 1
    assert patched.replace(addition, b"") == template
    assert patch_options_template(patched) == patched


def test_unrecognized_template_is_not_silently_patched():
    with pytest.raises(ValueError):
        patch_options_template(b"unknown configuration")


def test_server_indication_is_configured_without_full_renegotiation():
    with tarfile.open(ROOT / "work/sources/wolfssl-5.9.2-ac01707f.tar.gz") as source:
        cmake = source.extractfile(f"wolfssl-{SOURCE_COMMIT}/CMakeLists.txt").read()
    patched = patch_cmake_profile(cmake)
    added = b'set(WOLFSSL_DEFINITIONS "-DHAVE_SERVER_RENEGOTIATION_INFO")'
    assert patched.replace(added, b"set(WOLFSSL_DEFINITIONS)") == cmake
