# HGW-500BNA-QCv2 GPIO4 RAM diagnostic

This artifact identifies the physical GPIO4 control without assigning product
semantics to it. It performs no WPS request, radio toggle, persistence update,
reboot, MTD access or flash write.

## OEM basis

The exact `monitor_button` binary defines its second record as:

```text
label:       5G WIFI Button
GPIO:        4
released:    1
pressed:     0
sample:      500000 us
threshold:   10 samples (~5 s)
```

That proves the static OEM interpretation. This diagnostic exists to identify
the corresponding physical button and observe its electrical behavior on the
current A2 unit before porting any action.

## Safety contract

- Exact-machine gate: `mitrastar,hgw-500bna-qcv2`.
- Explicit load gate: module parameter `diagnostic=1`.
- GPIO aperture is mapped read-only by policy; the module only reads
  `GPIO_IN_DATA` and does not alter direction, mux or output registers.
- No automatic integration or boot service exists.
- Unload synchronously stops the worker and releases the input device.

## RAM experiment

Upload the module to the already-running Linux 5.10 RAM image, then:

```sh
insmod /tmp/hgw500-gpio4-diag.ko diagnostic=1
dmesg | tail -n 20
cat /proc/bus/input/devices
```

Required arm marker:

```text
OMGPIO4_DIAG armed gpio=4 active_low=1 poll_ms=20 debounce_ms=50 release_ms=500 long_ms=5000 action=observation-only
```

Perform two separate physical experiments:

1. Briefly press only the candidate second button and release it.
2. After the first result, hold it for at least six seconds and release it.

Expected markers:

```text
OMGPIO4_DIAG kind=pressed ... action=observation-only
OMGPIO4_DIAG seq=1 kind=short ... action=observation-only
OMGPIO4_DIAG seq=2 kind=long ... action=observation-only
OMGPIO4_DIAG kind=released-after-long ... action=observation-only
```

Each physical actuation must yield one semantic `short` or `long` marker. The
500 ms stable-release interval suppresses switch chatter.

Stop the probe:

```sh
rmmod hgw500_gpio4_diag
```

Required stop marker:

```text
OMGPIO4_DIAG stopped reason=module-unload action=observation-only
```

Do not infer WPS or radio-toggle behavior merely from seeing an input event.
Product semantics require a separate decision backed by the resulting log.
