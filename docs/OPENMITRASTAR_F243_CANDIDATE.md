# OpenMitraStar F243 Hardware Provenance

F243 extends F241 with an exact read-only hardware map.

- Wi-Fi 2.4 GHz button: GPIO2 / event0.
- Wi-Fi 5 GHz button: GPIO4 / event1.
- Reset button: GPIO5 / event2.
- Six LED-class devices originate from `e0000000.recovery`.
- No thermal class, hwmon device, watchdog device/class or GPIO sysfs class is
  exposed by the current Linux 5.10 kernel.

Absence is reported explicitly and is not interpreted as broken hardware.
No LED, GPIO, input or watchdog write operation is present.

## Artifact

- Bytes: `5238784`
- SHA-256: `b3e1d8b1577b38e2eda6b9b8d9cf2cadd88c8cbe909d765f33c02efc49227b75`
- Full-slot SHA-256: `a70296326987ad9e610a6dfeacb7179bd4a4197b111ddb4f626d745cc1e2c39e`
- Rootfs SHA-256: `df73a903ddd7ac5f5ec209dfeda499b590da68c562655fa31763686d9cd67135`

F243 is an offline observability experiment and is not flash-eligible.
