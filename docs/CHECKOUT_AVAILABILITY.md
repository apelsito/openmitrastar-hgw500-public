> Public export: availability below describes the source base. Check `PUBLICATION.json` for excluded native databases and private authoring files.

> Public export: availability below describes the source base. Check `PUBLICATION.json` for excluded native databases and private authoring files.

# Published checkout availability

The table below is derived from the remote base tree used for this documentation
update. It makes newer maintainer-local source selections visible without claiming
that they are already in this clone. A documentation commit does not change
firmware sources, original binaries, toolchain pins or selected submodule commits.

| Entry point | Available in remote base |
| --- | --- |
| `docs/AGENT_CURRENT_MISSION.md` | Yes |
| `handoff/AELITA_HANDOFF.md` | Yes |
| `handoff/SOURCE_MANIFEST.json` | Yes |
| `docs/STATUS.md` | No; newer/local or separately provisioned reference |
| `docs/RELEASE.md` | No; newer/local or separately provisioned reference |
| `build/releases/api-v2-r3/SOURCE_MAP_RELEASE.json` | No; newer/local or separately provisioned reference |
| `sources/uboot-hgw500/` | No; newer/local or separately provisioned reference |
| `tools/` | Yes |

## Submodule handoffs

Source and analysis submodule revisions stay pinned. Use the direct child
repository links in [the repository map](REPOSITORY_MAP.md) to read newer handoff
documentation; a parent clone intentionally retains the selected child revision.

## Integrity manifests

Where an artifact manifest includes README/documentation bytes, this update
refreshes only those members and aggregate counts. Existing non-document source
and evidence rows remain unchanged. Historical reports are not rewritten to
pretend that new builds or physical checks were run.
