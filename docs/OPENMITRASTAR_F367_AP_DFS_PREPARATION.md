# F367 AP DFS preparation: not a firmware image

2026-09-22. The source is `work/kernel-port/f367/`. Its checked-in build gate
keeps authority zero. No F367 full image has been composed, sealed or installed.
The first F366 physical acquisition failed; corrected F366r2 acquisition and
exact F365 return are mandatory prerequisites for further promotion.

The prepared first functional profile is AP-only, channel52/BW20, with channel36
as the fixed non-DFS evacuation target. It preserves the existing native
classifier, preprocessing, acquisition, postfilter and F355 lifetime. STA,
repeater, OCAC and weather-channel operation are excluded from this first
profile; later expansion needs separate physical evidence.

The source closes concrete OEM control shortcuts: quick CAC/NOP timers,
instant CAC completion, optional interception before radar marking, mutable
DOTH/test bypasses, administrative disable that clears NOP/reopens TX, and
unconfirmed TX-off being reported as stopped. Existing generation/readiness
checks and the existing CSA implementation are retained.

A small production admission policy requires a complete70-second CAC with the
same detector generation, rejects unsupported role/channel/width and denies TX
on detector loss or radar. NOP is at least1,800 seconds. Because no persisted NOP
record or trusted elapsed wall clock has yet been integrated, each driver
initialization also imposes a1,800-second DFS quarantine while channel36 stays
usable. **This extra startup quarantine is our conservative local policy, not
a new normative requirement.** It does not backdate any event or shorten NOP.
The intended later optimization is qualified persistent NOP without this
general extra delay.

Offline evidence:

- `outputs/preflight/f367-policy-20260922T100305Z/result.json` executes the
  actual admission policy in2,180 checks, including tick wrap, exact timer
  boundaries, generation changes, loss, invalid role and invalid width.
- `/workspace/OpenMitraStar-build/f367/f367-components-20260922T100323Z/result.json`
  records two identical authority-disabled component builds against F365,
  41 modules and1,975 audited imports. This is not permission to enable it.

Remaining integration is explicit: carry the corrected F366r2 native startup
admission/call into this branch after physical PASS; prepare the AP channel
transition/controller and observable state; qualify a separate bounded long
watchdog supervisor and health reporting covering real CAC70/600 and NOP1800;
bind successful acquisition/recovery evidence before an authority-enabled build
or image composition. The proposed long supervisor has not been implemented
or qualified in this preparation. Its planned use of the existing protocol
does not prove long-duration physical health.

F367 is therefore a tested source/component preparation, not an operational
DFS release or a ready physical candidate. The authoritative immediate next
artifact is the separate F366r2 native-start diagnostic.
