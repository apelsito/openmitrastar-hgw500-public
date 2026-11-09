#!/usr/bin/env python3
"""F310 multicast/IGMP gate using the proven F301 engine and SSH v2."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import f310_post_promotion_common as common
import run_f301_multicast_igmp_physical as base


ORIGINAL_PARSER = base.parser
ACK = "OPENMITRASTAR_F310_MULTICAST_IGMP_PHYSICAL"
PLAN_SCHEMA = "openmitrastar.f310-multicast-igmp-physical-plan/v1"
RESULT_SCHEMA = "openmitrastar.f310-multicast-igmp-physical/v1"
_LAST_ARGS: argparse.Namespace | None = None


def active_soak_evidence() -> dict[str, Any]:
    return common.active_soak_evidence()


def parser() -> argparse.ArgumentParser:
    result = ORIGINAL_PARSER()
    common.add_ssh_v2_arguments(result)
    original_parse = result.parse_args

    def parse_args(args=None, namespace=None):
        global _LAST_ARGS
        parsed = original_parse(args, namespace)
        if parsed.output_dir is None:
            parsed.output_dir = common.ROOT / (
                f"outputs/certification/f310-multicast-igmp-{base.utcnow():%Y%m%dT%H%M%SZ}"
            )
        common.install_ssh_v2(base.wpa, parsed)
        _LAST_ARGS = parsed
        return parsed

    result.parse_args = parse_args  # type: ignore[method-assign]
    return result


def configure_base() -> None:
    base.BUILD = common.BUILD
    base.MANIFEST = common.MANIFEST
    base.KNOWN_HOSTS = common.KNOWN_HOSTS
    base.EXPECTED_VERSION = common.EXPECTED_VERSION
    base.EXPECTED_SHA256 = common.EXPECTED_SHA256
    base.ACK = ACK
    base.PLAN_SCHEMA = PLAN_SCHEMA
    base.RESULT_SCHEMA = RESULT_SCHEMA
    base.active_soak_evidence = active_soak_evidence
    base.parser = parser


def main(argv: list[str] | None = None) -> int:
    configure_base()
    return base.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())

