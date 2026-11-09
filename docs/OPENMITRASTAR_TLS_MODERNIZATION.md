# Lyoko HTTPS modernization — offline milestone

Verified on 2026-09-06. This work preserves the restored F314 Movistar /
Telefonica UI and changes the prospective HTTPS implementation underneath it.
It does not change the installed device or authorize a new firmware hash.

## Current result

The pinned mini_httpd 1.19 server source now links against wolfSSL 5.9.2 for
static ARC700/v4 execution. The result has no dynamic interpreter and no
unsupported `llock`/`scond` instructions. Its C source is byte-identical to the
host implementation that passed TLS and CGI integration tests.

| Component | Bytes | SHA-256 |
| --- | ---: | --- |
| F314 mini_httpd-tls / OpenSSL 1.0.2d | 1,300,436 | `2a366556ee9ff59b590efc685fcfd5232e64845f2a3ce84244ec4b42b0433d9f` |
| Prospective mini_httpd / wolfSSL 5.9.2 | 463,384 | `b105f5c80010b2cb09120e9c7b6dbee0cd2f4ea67be9834d66015f96b0102575` |
| Prospective HTTPS configuration | 531 | `a2829c466bf7ce3e63a32f70dfe4e3c9288746688d595a8878d11577c7e5bd5c` |

The executable is 837,052 bytes smaller. This is an ELF size comparison, not a
measurement of device RAM, handshake latency or radio throughput. The old HTTP
parser is retained: replacing its TLS library is not a complete web-server
modernization or a comprehensive security audit.

Artifact:
`outputs/userland/minihttpd-wolfssl-5.9.2-arc700-cgi-tls-trial/manifest.json`.
Configuration and its qualification:
`outputs/userland/https-config-f314-qualification/` and
`outputs/userland/https-config-f317-qualification/`.

## Concrete fixes and proof

1. **Missing CGI transport identity.** Before the fix, the wolfSSL-compatible
   server did not set `HTTPS=on`; the existing CGI consequently omitted `Secure`
   from a session cookie even over TLS. The correction derives the flag only
   from the server's TLS state. Actual HTTPS tests verify the flag and cookie;
   plain HTTP cannot spoof it using `HTTPS` or forwarded-protocol headers.
2. **Missing HTTPS API routing.** The exact F314/F317 HTTPS configuration had
   `cgipat=**.cgi|cgi-bin/*|api/status`, without `api/v1/*`. An isolated host test
   reproduces a `200` response containing the session wrapper's source rather
   than executing it. Keeping that old routing while using compatible new TLS
   cipher syntax isolates the defect; no source contents are stored in the
   report. The corrected profile includes `api/v1/*`, rejects anonymous API
   access, and executes authenticated session/frontend requests correctly.
3. **TLS 1.2 compatibility.** The library advertises RFC5746 server indication
   with `HAVE_SERVER_RENEGOTIATION_INFO`; full renegotiation is not enabled. The
   host client retains certificate verification and modern default security.
   It negotiates TLS 1.2 and TLS 1.3; TLS 1.0 and 1.1 receive a server protocol
   rejection. An untrusted certificate is rejected by the client.
4. **Explicit failure handling.** The adapted server checks SSL context/session
   creation and socket attachment and treats every nonpositive accept result
   as failure. CGI flags are not copied from client headers.

The configuration changes only its descriptive comment, CGI route list and
cipher list. Host binding, port, certificate/pid paths and startup scripts are
unchanged in the prospective product. Tests substitute only loopback binding,
an ephemeral port and temporary certificate/pid paths.

The initial protocol/cookie qualification has 22 HTTP checks per TLS protocol.
The subsequent exact-configuration qualification repeats 22 checks per protocol
on **each** F314 and F317 base: 88 checks across both bases. These include login,
logout, CSRF-header forwarding, authenticated API behavior, protected HTML,
exact JS/CSS/logo hashes, MIME types, CSP and cookies. The source/profile/scope
unit regression set is 24 passing tests.

Evidence:

- `outputs/userland/wolfssl-https-host-qualification/manifest.json`
- `outputs/userland/https-config-f314-qualification/manifest.json`
- `outputs/userland/https-config-f317-qualification/manifest.json`

All certificates and credentials in those tests are synthetic and temporary.
No test private key is retained. No router or UART connection is opened.

## Native rootfs fit and preservation

The same classic TSX package,
`outputs/frontend/lyoko-classic-tsx-5de8852058ef58ec`, was combined with the two
TLS files in temporary native-Linux rootfs trees. Two independent SquashFS
builds per base match exactly; both produced images were then extracted and
every entry compared, including bytes, ownership, modes, directories, symlinks
and hardlinks. No blanket source chmod was used.

| Base | UI + TLS SquashFS bytes | Headroom in 4,587,520-byte window | SHA-256 |
| --- | ---: | ---: | --- |
| F314 | 3,395,584 | 1,191,936 | `df0ad58f335d5109da04880b952f6775654ca347bbe71aa024ecdf67b9823c55` |
| F317 | 3,465,216 | 1,122,304 | `e0299e9b4e34a036f69089a4d7bdd7d2219ba2f0586402b71f72dbc5faae8298` |

The only delta beyond the separately qualified UI is
`usr/sbin/mini_httpd-tls` and `etc/minihttpd-https.conf`. Existing radio controls,
modules, firmware, init scripts and CGI authentication logic remain unchanged.
The API receives only the already-pinned frontend-identity transform.

Reports: `outputs/userland/ui-tls-rootfs-f314.json` and
`outputs/userland/ui-tls-rootfs-f317.json`. The temporary rootfs images are
removed after verification; no deployable webformat image is generated.

## Build provenance and superseded trials

wolfSSL is pinned to commit `ac01707f552c611fbd135cc723b2682b3e7f80f2`, resolved
from `v5.9.2-stable`; archive SHA-256
`f1e121e2cb56aa40f85eb0995116c9858d2d8f184c08428e6a2db66b97e2c903`.
The recorded provenance is the official repository over HTTPS and a fixed
commit; an upstream cryptographic signature has **not** been verified.
See `work/sources/wolfssl-5.9.2-ac01707f.tar.gz.json`.

The ARC build uses the existing GCC 15.2.0 no-atomic/uClibc sysroot and a local,
hash-pinned CMake tool. Options select single-threaded static code, TLS 1.2/1.3,
no old TLS, no assembly and constant-size DH computation. The CMake metadata
patch exports the actual single-thread and server-indication definitions to
consumers. Cryptographic implementation sources are not modified.

Current library:
`outputs/userland/wolfssl-5.9.2-arc700-tlscompat-trial/manifest.json`, SHA-256
`bcc4b08148e11f9ea1f8c3515f6e98437b12d41c9807248d8c5b5341a95afb46`.
Qualified server C SHA-256:
`7846d659529961d1ef6e03f7e3d3bfe27e43ca53e81569278473c641b50198e7`.

Earlier `wolfssl-5.9.2-arc700-trial`, `wolfssl-5.9.2-arc700-dhconst-trial` and
`minihttpd-wolfssl-5.9.2-arc700-trial` outputs are historical experiments, not the
qualified profile. Their earlier missing dependencies, TLS 1.2 indication and
CGI transport identity must not be carried into an integration. They are kept
as evidence rather than silently replaced.

## Remaining gates

- Actual ARC TLS handshake, CPU/peak RAM and boot-time entropy behavior.
- Real certificate provisioning and startup. The unchanged init script enables
  HTTPS only when a root-owned, mode-0600 runtime PEM already exists; none is
  bundled. A successful host test does not prove HTTPS is enabled on the HGW.
- Browser/client interoperability on the actual device, session and certificate
  trust provisioning, and an explicit policy for the retained plaintext HTTP
  management endpoint. Password storage/KDF modernization is not claimed here.
- Physical platform, dual-radio traffic, management continuity and rollback.
- The F315/F316 radar/CAC/evacuation/NOP and F319 ownership campaigns retain their
  separate gates. Simulated channels do not authorize RF transmission.

`release_eligible=false` and `flash_supported=false` remain in force. F314 is the
recorded persistent baseline, not a freshly queried live state. A free COM port
does not identify the attached board. HGW UART binding and release from Askey
must be established before any physical campaign. The existing F319 approval
does not authorize flashing this different UI/TLS payload.
