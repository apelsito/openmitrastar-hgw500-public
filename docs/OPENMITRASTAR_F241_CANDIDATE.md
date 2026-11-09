# OpenMitraStar F241 Network Observability

F241 extends F239 with read-only bridge, multicast, IGMP and VLAN state.

The API and web expose snooping, querier, multicast-router mode, IGMP version,
IPv4 interface/group counts, IPv6 group count, configured VLAN interfaces and
bridge VLAN-filtering availability. No bridge, multicast or VLAN value is
modified.

Live F222 reference on September 2, 2026: snooping `0`, querier `0`, router `1`,
IGMPv2, five IPv4 interfaces/groups, eleven IPv6 entries, zero configured VLAN
interfaces and no exposed bridge `vlan_filtering` attribute.

## Artifact

- Bytes: `5218304`
- SHA-256: `61f9d00c09e4146d816d48115910e216967e09a8b4115b4f1106d4af6f0aecbe`
- Full-slot SHA-256: `c1d1b436ce5bed1f288d5cf5c16858898f448c8e321ab873230d27b12e2fd65d`
- Rootfs SHA-256: `58cd8500719697879368d3fab7542f92134b5e2fd8fc3ed783b8428d674040e5`

F241 is offline and not flash-eligible.
