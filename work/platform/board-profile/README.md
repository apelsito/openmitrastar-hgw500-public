# Lyoko board profile v1

> Public source snapshot. [Scope, provenance and verification](docs/PUBLIC_SNAPSHOT.md).

This directory defines the hardware contract consumed by portable Lyoko
components. A board profile describes what exists and what is allowed; it is
not a runtime configuration file and it never contains device identity data.

## Design rules

- Profiles are UTF-8 JSON restricted to printable ASCII content.
- `schema.json` is a strict JSON Schema Draft 2020-12 document.
- Every object rejects unknown properties.
- Byte sizes and offsets are decimal integers. Human-readable hexadecimal
  values belong in documentation, not in the machine contract.
- Physical flash partitions and logical Linux views are separate collections.
- Radio firmware names are permitted; firmware bytes and calibration data are
  not.
- MAC addresses, passwords, PSKs, private keys, serial numbers and calibration
  payloads are forbidden.
- A profile records evidence status. It must not turn an inferred capability
  into a proven one.

## Sections

The top-level contract deliberately keeps these concerns independent:

| Section | Purpose |
| --- | --- |
| `identity` | Non-unique vendor, model, board family and revisions. |
| `cpu`, `ram` | Execution ABI and usable/reserved memory windows. |
| `flash` | Physical device geometry, partitions and logical views. |
| `boot` | Loader, console, transports, slots and normal update target. |
| `network` | Management, Ethernet and bridge topology. |
| `radios` | Per-radio bus, interface, drivers, firmware and calibration policy. |
| `hardware_io` | GPIO-backed LEDs, buttons, thermal and watchdog support. |
| `writable_store` | Optional persistent state region and update semantics. |
| `recovery` | Ordered recovery methods and immutable regions. |
| `capabilities` | Evidence-qualified feature registry. |
| `constraints` | Machine-enforced platform invariants. |
| `evidence` | Local, non-secret sources supporting profile claims. |

## HGW-500BNA-QCv2 example

`hgw500bna-qcv2.json` describes the A2 unit from local OpenMitraStar evidence.
It records the 16 MiB SPI NOR physical layout, the logical rootfs view, the
ARC700 ABI, the direct Ethernet path, both radio stacks and the known GPIO
contract. `lyoko_store` is a read-only logical view inside the live firmware
slot. It starts at `0x5e0000`, immediately after the `0x180000` kernel region
and `0x460000` SquashFS window, so the current layout is non-overlapping.
`mtd5/data` remains factory/calibration data and is not advertised as general
writable storage. Store writes still require the SPI protection and bounded
single-eraseblock hardware gates.

The example contains no deployed IP address, MAC address, Wi-Fi credential,
SSH key, serial number or calibration payload.

## Validation

Run from the repository root:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
python tools\test_lyoko_board_profile.py
```

The test runner uses only the Python standard library. It validates the JSON
against the checked-in schema and applies semantic checks that JSON Schema
cannot express compactly:

- duplicate JSON keys are rejected;
- physical partitions are aligned, contiguous, non-overlapping and fill the
  declared flash device;
- logical views and the writable store stay inside their source partition;
- the store must have one exact logical store view;
- any separate rootfs/kernel overlap keeps the store disabled and requires a
  layout change;
- slot, store, calibration, evidence and recovery references must resolve;
- normal firmware writes must target the declared live slot only;
- sensitive partitions cannot become writable stores;
- secret-like keys and literal MAC addresses are rejected.

Consumers should validate a profile before using it and fail closed when a
capability is absent, blocked, partial or unproven.
