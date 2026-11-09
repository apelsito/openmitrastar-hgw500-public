# F344 — AP, station and repeater components

F344 implements the missing managed mode workflow and builds its native ARC
program, OEM MADWIFI supplicant and coherent driver set. It is **not complete
AP/STA/repeater parity and not a release-qualified firmware image**. Every
Wi-Fi/RF/client test remains **USER_DEFERRED**. No F344 loader or driver has
been executed on the router; F340/F341 images and recovery helpers are unchanged.

## Implemented contracts

| Mode | Native topology and startup |
|---|---|
| AP | `start 0 ap wifi0 FACTORY_MAC`, hostapd-QTN, existing br0 membership |
| STA | `start 0 sta wifi0 FACTORY_MAC`, MADWIFI supplicant on wifi0 and br0 |
| Repeater | Primary STA, native `repeater 1`, then `start 0 ap wifi1`; the driver derives wifi1's MAC, and hostapd follows the authenticated upstream channel |

The source is the OEM `start-prod`, `start-vap` and `start-helpers.sh`, together
with the real qdrv/wlan handlers. A CGI station list is not station mode.
The OEM selector values are 0=AP, 1=STA and 2=AUTO; AUTO chooses AP/STA from
configuration/lease state. No HGW A2 physical selector/GPIO mapping was proven.
QHOP/WDS MBS/RBS remains a distinct, incompatible extender topology and is
rejected by this workflow. Those distinctions are not removed to obtain PASS.

The proprietary radio firmware's structures are unchanged. F344 appends
host-only callbacks and generations at the end of `ieee80211com`, rebuilds
all 26 kernel modules against F340's exact configuration, and introduces an
exported wlan ABI marker that qdrv checks. ARC-compiled layout witnesses
compare host prefix offsets and the actual ioctl/shared/MuC structures.
The 26-module set must be consumed together; replacing qdrv alone is invalid.

The F338 provider is retained with `hardware_enable=0`,
`diagnostic_capture=0`, `authoritative_enable=0`; no math service is launched.
This preserves the external radar API and context handling for channels
36/40/44/48 without opening acquisition MMIO. F341's diagnostic provider is
not used because it deliberately permits only channel 36. DFS remains gated
by real readiness; this component bundle does not supply that readiness.
The retained `fwt_ctrl` module is proprietary, with no GPL-only import/taint
conflict in this closure; the provider/qdrv dependency chain is GPL compatible.

## Snapshot, transition and rollback

`om-f344-mode --launch-ap CONFIG` captures the exact private configuration
before execing the original hostapd in the same PID. `--confirm-bootstrap`
checks live driver/daemon/bridge state before the bootstrap script removes
its old temporary config. No legacy daemon is adopted by guessing its PSK,
and WPS is never enabled merely to retrieve GET_CONFIG secrets.

Private state is under `/run/openmitrastar/f344`, with directories 0700 and
regular files 0600. Records contain boot ID, generation, PID/starttime,
executable/config identity, integrity SHA-256 and the private profile needed
for restoration. Public output excludes credentials, calibration and MACs.
Embedded NUL config text, symlink files, incomplete profiles, unknown VAPs,
extenders and missing readbacks are rejected before service shutdown.

`--apply PRIVATE_PROFILE_DIRECTORY` snapshots actual management and radio
state, holds new CSA admissions, stops only owned 5GHz security daemons,
administratively lowers wifi interfaces, closes the future-open gate, drains
CSA software work, detaches only wifi interfaces, then creates the selected
native topology. It sets and reads back the actual driver channel mask before
enabling station scanning. OFDM SETCHANLIST uses bit(channel−1), while its
GETCHANLIST result uses bit(channel). Supplicant `scan_freq` cannot substitute
for that gate: the vendor MADWIFI backend ignores `params.freqs`.

STA/repeater observes current frequency through SIOCGIWFREQ; OEM STATUS does
not contain it. Both modes permit only channels 36/40/44/48. Repeater starts
the station first and renders the AP on its authenticated upstream channel;
it does not rewrite the running station's config. The full vendor OpenSSL,
EAP, MADWIFI/WEXT and `-r` parser profile is preserved. `-r` alone is not proof
of driver repeater mode. CLI exit status alone is insufficient because vendor
wpa_cli can exit 0 after a `FAIL` reply.

Applied/rolled-back states require fresh daemon, ioctl, MAC, bridge,
configured/operating bandwidth and management readbacks. A failure starts
restoration from the retained private profile, bounded by the original
120-second total deadline. A verified rollback is explicitly distinguished
from an attempted or failed rollback. An existing NOP/radar restriction is
not erased. DHCP, br0 addressing, Ethernet power and persistent flash are
outside this workflow. The same observed management MAC is retained across
bridge membership changes; br0/eth0/wlan0 IFF_UP and routes are checked.

Snapshot identity proves the managed launched configuration, not arbitrary
later hostapd/supplicant SET/WPS mutations. Future integration of such writers
must call `--invalidate` before changing a managed daemon and publish a new
managed generation through the workflow. That production UI/config-writer
wiring is not installed by this component bundle. Full data-plane bridging,
three-address/four-address interoperability and client traffic remain untested.

## Exact MuC limitation

`include/qtn/lhost_muc_comm.h:413–443` defines `qtn_csa_info`. It carries
`req_tsf`, `switch_tsf`, host status and MuC status, but no generation token.
The OEM IRQ schedules its completion work at **POST (0x08)**; the work clears
host ACTIVE. This does not itself prove **COMPLETE (0x40)**, and an old IRQ
after reusing that descriptor cannot be authenticated by a host-only epoch.
F344 does not write MuC status, clear ACTIVE as a simulated cancellation, or
change the firmware ABI to invent a token.

F344 therefore exposes and applies these conditions:

- `csa_reuse_supported=1` only while this boot has never published a deferred
  CSA. A recorded publication permanently makes this 0 until a demonstrated
  new radio epoch; this implementation only obtains that state at initialization.
- `csa_pending` includes in-flight host admissions, native count/flags/timer,
  firmware ACTIVE and, after publication, lack of MuC COMPLETE.
- The public apply path returns **EOPNOTSUPP (-95)** before stopping daemons
  if descriptor reuse is unsupported. Seeing COMPLETE does not waive this.
- HOLD increments a host-only, nonwrapping generation and prevents new
  admission. In a supported epoch, drain waits for admitted producers, joins
  the timer and CSA work outside spin/RTNL locks, and checks state again.
  Only then can it publish `csa_drained=1` and release HOLD.
- If a CSA wins the race between snapshot and HOLD, later drain refuses the
  transition. No completed rollback is promised in that case. Actual state
  and failed rollback remain visible; a dirty module is not unloaded.
- Old timer and callback generations are rejected after a legitimate new
  host epoch. Residual IRQs with host ACTIVE=0 are ignored. This is software
  lifetime protection, not proof of hardware cancellation or RF quiescence.

The next parity task is to recover and prove the OEM full radio/MuC stop/start
sequence that establishes a fresh firmware epoch while preserving Ethernet,
2.4GHz management, configuration and NOP state. That task and RF acceptance
remain open; they are not replaced by a timeout or an unconditional success.

## Offline evidence and packaging

Canonical result paths and hashes are collected in the final versioned bundle
manifest. The test sets include actual C functions, not only specifications:

- 25 real drain/timer checks, including unsupported descriptor reuse after
  POST and COMPLETE, generation changes, custom callbacks and nonwrapping epoch.
- 756 portable transaction checks: all nine mode pairs and 17 action failures.
- 1,325 checks through the actual action backend with explicitly fake ioctl,
  CLI and daemon transports: all nine pairs and 31 primitive failures.
- 82 real host process/private-profile checks, including a reaped leader's
  lingering child, clock failure, pipe overflow, embedded NUL, 32-byte SSID,
  symlinks, permissions and AP-follow preserving the running station config.
- Mode admission/topology tests, inert bootstrap transformation checks, ARC
  ABI witnesses, identical paired builds and full import/license/load-order audit.

The native mode executable and vendor WPA binaries are static ARC700 and
contain no llock/scond. Their ARC execution is UNRUN. A host execution result
is not a router/Linux execution result, and fake transports are not RF tests.

The bundle includes a versioned bootstrap helper and updated driver contract,
but no flashable full image or installer. Its feature file is disabled by
default; the loader is not connected to init. Neither running a tool build
nor producing this package authorizes device access.

## Final sealed handoff — 2026-09-21 16:26 UTC

- Manifest: `outputs/handoff/f344-mode-components-20260921T162648Z/manifest.json`,
  SHA-256 `fffd6643a7db9f186aefa02e06f29995f8742ad7f91f824a34f8cb80ecf84401`.
- Component ZIP: `f344-components-a.zip` beside that manifest, 1,377,341 bytes,
  SHA-256 `a9acbf41d04cd83dc9187a3a4e74519d4b8bbdef77e8f0a230620a795ea1744f`.
  Both independently packed ZIPs are identical; 34 files and 33 catalog entries
  were checked after packing. The closure audit resolves 1,086 imports.
- Final native mode tool: 89,640 bytes,
  SHA-256 `f60191f84a3d549ce5d79d3d0eb7ae41229173549e877e755bd97eb17db6e580`.
- Final qdrv: 694,516 bytes,
  SHA-256 `8d6d95da33805f27edc23ad2ccd1dfc2cab946e3c72206fec0795f6e66e65b51`.
- Final F338 provider rebuilt against F340: 67,628 bytes,
  SHA-256 `c64047758968c164945673028a940bbd911c10a5e960caf34de5fbf37d139769`.

The first two closure directories (16:07:25 and 16:15:35 UTC) used the
channel-36-only F341 diagnostic provider and are intermediate artifacts,
not this handoff. The 16:19:20 build was stopped after a command quoting error
left that same incorrect provider selection; its FAIL evidence is preserved.
The final closure is `analysis/f344-closure-20260921T162003Z/manifest.json`
under the device-private directory, with the F338 provider and exact F340
configuration. No failed or intermediate artifact is promoted by this result.
