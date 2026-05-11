#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate Intent Graph - T180 Skill Script."""

import sys
from pathlib import Path

skill_dir = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(skill_dir))

from io_ring.validation.json_validator import main


if __name__ == "__main__":
    main()
