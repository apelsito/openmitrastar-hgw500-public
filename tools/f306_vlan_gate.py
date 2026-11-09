#!/usr/bin/env python3
"""F306 VLAN 4090 gate using the proven F301 engine and SSH v2."""
from __future__ import annotations

import argparse
from typing import Any

import f306_post_promotion_common as common
import f301_vlan_gate as base


ORIGINAL_PARSER = base.parser
ACK = "OPENMITRASTAR_F306_VLAN4090_PHYSICAL"
PLAN_SCHEMA = "openmitrastar.f306-vlan4090-plan/v1"
RESULT_SCHEMA = "openmitrastar.f306-vlan4090-physical/v1"


def active_workflow_evidence() -> dict[str, Any]:
    return common.active_soak_evidence()


def parser() -> argparse.ArgumentParser:
    result = ORIGINAL_PARSER()
    common.add_ssh_v2_arguments(result)
    original_parse = result.parse_args

    def parse_args(args=None, namespace=None):
        parsed = original_parse(args, namespace)
        if parsed.output_dir is None:
            parsed.output_dir = common.ROOT / (
                f"outputs/certification/f306-vlan4090-{base.utcnow():%Y%m%dT%H%M%SZ}"
            )
        common.install_ssh_v2(base.wpa, parsed)
        return parsed

    result.parse_args = parse_args  # type: ignore[method-assign]
    return result


def configure_base() -> None:
    base.BUILD = common.BUILD
    base.MANIFEST = common.MANIFEST
    base.CONFIG = common.BUILD / (
        "openmitrastar-linux510-f306-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.config"
    )
    base.KNOWN_HOSTS = common.KNOWN_HOSTS
    base.EXPECTED_VERSION = common.EXPECTED_VERSION
    base.EXPECTED_CANDIDATE_SHA256 = common.EXPECTED_SHA256
    base.ACK = ACK
    base.PLAN_SCHEMA = PLAN_SCHEMA
    base.RESULT_SCHEMA = RESULT_SCHEMA
    base.active_workflow_evidence = active_workflow_evidence
    base.multicast_gate.active_soak_evidence = active_workflow_evidence
    base.parser = parser


def main(argv: list[str] | None = None) -> int:
    configure_base()
    return base.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())

