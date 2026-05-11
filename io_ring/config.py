#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared configuration helpers for T180 IO Ring scripts."""

import os
from pathlib import Path


def resolve_output_root() -> Path:
    """Resolve unified output root for generated reports/artifacts."""
    env_root = os.environ.get("AMS_OUTPUT_ROOT", "").strip()
    if env_root:
        return Path(env_root).expanduser().resolve(strict=False)

    agent_root = os.environ.get("AMS_IO_AGENT_PATH", "").strip()
    if agent_root:
        return Path(agent_root).expanduser().resolve(strict=False) / "output"

    return (Path(os.getcwd()) / "output").resolve(strict=False)


def resolve_confirmed_config_path(config_path: Path, consume_confirmed_only: bool) -> Path:
    """Resolve confirmed config path with auto-build logic."""
    if not consume_confirmed_only:
        return config_path

    if config_path.name.endswith("_confirmed.json"):
        return config_path

    expected_confirmed = config_path.with_name(f"{config_path.stem}_confirmed.json")
    if expected_confirmed.exists():
        return expected_confirmed

    from io_ring.layout.confirmed_config import build_confirmed_config_from_io_config

    generated = Path(build_confirmed_config_from_io_config(str(config_path)))
    if generated.exists():
        return generated

    raise ValueError(
        "Editor-confirmed config required. "
        f"Expected: {expected_confirmed}. "
        "Please run build_confirmed_config.py first."
    )

