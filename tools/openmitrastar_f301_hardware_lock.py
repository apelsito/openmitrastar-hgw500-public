#!/usr/bin/env python3
"""Cross-process exclusion for F301 physical radio campaigns."""
from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[1]
LOCK_DIR = ROOT / "outputs/locks/f301-physical-radio.lock"


class HardwareLockBusy(RuntimeError):
    pass


class HardwareLock(AbstractContextManager["HardwareLock"]):
    def __init__(self, owner: str, evidence_dir: Path, lock_dir: Path = LOCK_DIR) -> None:
        self.owner = owner
        self.evidence_dir = evidence_dir.resolve()
        self.lock_dir = lock_dir
        self.acquired = False

    def acquire(self) -> "HardwareLock":
        self.lock_dir.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.lock_dir.mkdir()
        except FileExistsError as exc:
            details = ""
            owner_file = self.lock_dir / "owner.json"
            try:
                payload = json.loads(owner_file.read_text(encoding="ascii"))
                details = f" owner={payload.get('owner')!r} pid={payload.get('pid')!r}"
            except (OSError, ValueError, TypeError):
                details = " owner=unknown"
            raise HardwareLockBusy(f"F301 physical radio lock is already held:{details}") from exc

        payload = {
            "schema": "openmitrastar.f301-physical-radio-lock/v1",
            "owner": self.owner,
            "pid": os.getpid(),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "evidence_dir": str(self.evidence_dir),
        }
        try:
            (self.lock_dir / "owner.json").write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="ascii",
                newline="\n",
            )
        except Exception:
            shutil.rmtree(self.lock_dir, ignore_errors=True)
            raise
        self.acquired = True
        return self

    def release(self) -> None:
        if not self.acquired:
            return
        shutil.rmtree(self.lock_dir, ignore_errors=False)
        self.acquired = False

    def __enter__(self) -> "HardwareLock":
        return self.acquire()

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.release()


def acquire_physical_lock(owner: str, evidence_dir: Path, lock_dir: Path = LOCK_DIR) -> HardwareLock:
    return HardwareLock(owner, evidence_dir, lock_dir)
