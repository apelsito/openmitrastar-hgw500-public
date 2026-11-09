# OpenMitraStar front-panel LED identification gate

The installed F222 firmware exposes six LED class devices and includes
`/usr/sbin/om-ledctl`. The controller reports five user-facing channels plus the
separate `topaz:stage0:alive` boot LED.

`tools/run_frontpanel_led_identification_gate.ps1` provides a guarded physical
identification sequence. It records the complete LED state before the test,
cycles each channel for one to three seconds, exercises composite lower-panel
colours and requires an exact state restoration afterwards.

The gate is dry-run by default and requires
`OPENMITRASTAR_FRONTPANEL_LED_IDENTIFY` for execution. It performs no MTD,
radio, bootloader or persistent configuration writes. Visual colour/window
mapping still requires an observer beside the physical router.
