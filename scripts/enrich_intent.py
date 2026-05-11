#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run the T180 semantic enrichment engine."""

import sys
from pathlib import Path

skill_dir = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(skill_dir))


def main() -> None:
    from io_ring.layout.enrichment_engine import (
        enrich,
        InputError,
        WiringError,
        GateError,
    )

    if len(sys.argv) < 3:
        print("Usage: python enrich_intent.py <semantic_intent.json> <intent_graph.json> [tech_node]")
        print("")
        print("Exit codes:")
        print("  0 - Success")
        print("  1 - Semantic intent input error")
        print("  2 - Wiring table / engine bug")
        print("  3 - Gate failure")
        sys.exit(2)

    semantic_path = Path(sys.argv[1]).resolve()
    output_path = Path(sys.argv[2]).resolve()
    tech_node = sys.argv[3] if len(sys.argv) > 3 else "T180"
    if tech_node != "T180":
        print(f"[ERROR] Only T180 supported by this engine (got: {tech_node})", file=sys.stderr)
        sys.exit(2)

    wiring_path = skill_dir / "io_ring" / "schematic" / "devices" / "device_wiring_T180.json"
    print("[>>] Enriching T180 semantic intent...")
    print(f"   Input:  {semantic_path}")
    print(f"   Output: {output_path}")
    print(f"   Wiring: {wiring_path}")

    try:
        result = enrich(semantic_path, wiring_path, output_path)
    except InputError as e:
        print("", file=sys.stderr)
        print(str(e), file=sys.stderr)
        sys.exit(1)
    except WiringError as e:
        print("", file=sys.stderr)
        print(str(e), file=sys.stderr)
        sys.exit(2)
    except GateError as e:
        print("", file=sys.stderr)
        print(str(e), file=sys.stderr)
        sys.exit(3)
    except Exception as e:
        print("", file=sys.stderr)
        print(f"[ENGINE-BUG] Unexpected error: {type(e).__name__}: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(2)

    intent_graph = result["intent_graph"]
    n_pads = sum(1 for inst in intent_graph["instances"] if inst.get("type") == "pad")
    n_corners = sum(1 for inst in intent_graph["instances"] if inst.get("type") == "corner")

    print("")
    print(f"[OK] T180 enrichment complete in {result['duration_ms']}ms")
    print(f"   Pads: {n_pads}, Corners: {n_corners}")
    print("   Gates:")
    for gate_id, gate_result in result["gates"].items():
        status = "PASS" if gate_result.get("pass") else "FAIL"
        extra = ""
        if "counts" in gate_result:
            extra = f" ({gate_result['counts']})"
        print(f"     {gate_id}: {status}{extra}")
        for warning in gate_result.get("warnings", []):
            print(f"       [WARN] {warning}")
    print(f"   Wrote: {output_path}")
    sys.exit(0)


if __name__ == "__main__":
    main()

