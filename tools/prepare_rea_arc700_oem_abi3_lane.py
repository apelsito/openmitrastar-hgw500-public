"""Derive isolated REA runtime accepting genuine ARC700 OEM e_flags 0x303.

This preserves ELF headers, the installed runtime and the previously used lab.
It reuses that lab's Ghidra processor without editing it. Static work only.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--parent", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    parent_manifest = a.parent / "manifest.json"
    before = sha(parent_manifest)
    manifest = json.loads(parent_manifest.read_text())
    runtime = Path(manifest["runtime"])
    a.output.mkdir(parents=True, exist_ok=False)
    derived = a.output / "rea-agents"
    derived.mkdir()
    for name in ("dist", "bridge", "scripts"):
        shutil.copytree(runtime / name, derived / name)
    for name in ("package.json", "LICENSE", "README.md"):
        shutil.copyfile(runtime / name, derived / name)
    (derived / "node_modules").symlink_to((runtime / "node_modules").resolve(), target_is_directory=True)
    patches = []
    for file in (derived / "dist").rglob("*.js"):
        old = file.read_text()
        if "![0x3, 0x403].includes(readU32(36))" not in old:
            continue
        new = old.replace("![0x3, 0x403].includes(readU32(36))", "![0x3, 0x303, 0x403].includes(readU32(36))")
        new = new.replace("ET_REL/ET_EXEC flags 0x3/0x403", "ET_REL/ET_EXEC flags 0x3/0x303/0x403")
        old_sha = sha(file)
        file.write_text(new)
        patches.append(dict(path=str(file.relative_to(derived)), parent_sha256=old_sha, derived_sha256=sha(file)))
    assert patches, "bounded header gate missing"
    assert sha(parent_manifest) == before
    manifest.update(runtime=str(derived), parent_manifest_sha256=before,
                    parent_lab=str(a.parent), derivative_patches=patches,
                    status="DERIVED_OEM_ABI3_STATIC_LANE_REQUIRES_ASSEMBLY_VERIFICATION",
                    admission_delta="Only genuine EM_ARC_COMPACT93 ELF32LE ET_REL/ET_EXEC e_flags0x303 additionally admitted",
                    parent_runtime_modified=False, installed_rea_modified=False, original_artifacts_modified=False)
    (a.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"output": str(a.output), "patches": len(patches), "parent_unchanged": True}))


if __name__ == "__main__":
    main()
