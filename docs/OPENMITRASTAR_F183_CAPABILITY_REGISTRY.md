# OpenMitraStar F183 capability registry

Date: `2026-09-01`

F183 adds the machine-readable capability registry required by the Lyoko web
roadmap. Six states are supported:

```text
available
readonly
experimental
blocked
unsupported
certification_required
```

Each capability records its domain, minimum UI mode, risk, evidence and real
backend. The Developer view renders all 16 entries as localized status rows.

No writable endpoint is added. Kernel, DTB, radios, package manager and signed
package payload are byte-identical to F177.

Build:

```powershell
.\tools\build_f183_capability_registry.ps1
```

Hardware validation remains `NOT_RUN`.
