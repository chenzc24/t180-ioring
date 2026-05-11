#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Semantic enrichment engine for T180 IO rings.

The AI owns semantic decisions: signal class, base device, voltage-domain block,
and digital direction. The engine owns mechanical execution: pin wiring, corner
insertion, and gate checks.
"""

from __future__ import annotations

import json
import re
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class EngineError(Exception):
    exit_code = 2

    def __init__(
        self,
        summary: str,
        *,
        position: str = "",
        device: str = "",
        detail: str = "",
        hint: str = "",
        section: str = "",
    ):
        self.summary = summary
        self.position = position
        self.device = device
        self.detail = detail
        self.hint = hint
        self.section = section
        super().__init__(self.format_message())

    @property
    def kind(self) -> str:
        return "ERROR"

    def format_message(self) -> str:
        lines = [f"[ENGINE-{self.kind}] {self.summary}"]
        ctx = []
        if self.position:
            ctx.append(f"position={self.position}")
        if self.device:
            ctx.append(f"device={self.device}")
        if ctx:
            lines.append(f"  At: {', '.join(ctx)}")
        if self.detail:
            lines.append(f"  Detail: {self.detail}")
        if self.hint:
            lines.append(f"  Hint: {self.hint}")
        if self.section:
            lines.append(f"  See: references/enrichment_rules_T180.md {self.section}")
        return "\n".join(lines)


class InputError(EngineError):
    exit_code = 1

    @property
    def kind(self) -> str:
        return "INPUT"


class WiringError(EngineError):
    exit_code = 2

    @property
    def kind(self) -> str:
        return "WIRING"


class GateError(EngineError):
    exit_code = 3

    @property
    def kind(self) -> str:
        return "GATE"


VALID_LABEL_FROM = {
    "self",
    "self_core",
    "domain.vdd_consumer",
    "domain.vss_consumer",
    "domain.vdd_provider",
    "domain.vss_provider",
    "const.noConn",
}

_POS_PAD = re.compile(r"^(left|right|top|bottom)_(\d+)$")
_POS_CORNER = re.compile(r"^(top_left|top_right|bottom_left|bottom_right)$")

CORNER_NAMES = {
    "top_left": "CORNER_TL",
    "top_right": "CORNER_TR",
    "bottom_right": "CORNER_BR",
    "bottom_left": "CORNER_BL",
}

CORNER_BY_SIDE_PAIR = {
    frozenset(("top", "left")): "top_left",
    frozenset(("top", "right")): "top_right",
    frozenset(("bottom", "right")): "bottom_right",
    frozenset(("bottom", "left")): "bottom_left",
}


def load_wiring_table(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise WiringError(
            f"Wiring table not found: {path}",
            hint="Ensure io_ring/schematic/devices/device_wiring_T180.json exists.",
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise WiringError(f"Wiring table is not valid JSON: {e}")

    if data.get("tech_node") != "T180":
        raise WiringError("Wiring table tech_node must be T180")
    devices = data.get("devices")
    if not isinstance(devices, dict) or not devices:
        raise WiringError("Wiring table missing non-empty devices section")

    for device, spec in devices.items():
        if not isinstance(spec, dict):
            raise WiringError(f"Device {device}: spec must be an object")
        if not spec.get("family"):
            raise WiringError(f"Device {device}: missing family")
        pins = spec.get("pins")
        if not isinstance(pins, dict) or not pins:
            raise WiringError(f"Device {device}: missing pins")
        for pin_name, pin_spec in pins.items():
            label_from = pin_spec.get("label_from")
            if label_from not in VALID_LABEL_FROM:
                raise WiringError(
                    f"Device {device}, pin {pin_name}: unknown label_from='{label_from}'",
                    hint=f"Valid values: {sorted(VALID_LABEL_FROM)}",
                )
    return data


def parse_position(position: str) -> Tuple[str, str, Tuple[int, ...]]:
    if _POS_CORNER.match(position):
        return "corner", position, ()
    match = _POS_PAD.match(position)
    if match:
        return "pad", match.group(1), (int(match.group(2)),)
    raise InputError(
        f"Position '{position}' does not match T180 position format",
        position=position,
        hint="Use side_idx positions such as left_0, top_3, or fixed corner names.",
        section="Final JSON Templates",
    )


def _self_core(name: str) -> str:
    match = re.match(r"^(.+?)(<[^>]+>)$", name)
    if match:
        return f"{match.group(1)}_CORE{match.group(2)}"
    return f"{name}_CORE"


class ResolutionContext:
    def __init__(
        self,
        instance: Dict[str, Any],
        domain_id: str,
        domains: Dict[str, Any],
    ):
        self.instance = instance
        self.name = instance["name"]
        self.position = instance["position"]
        self.domain_id = domain_id
        self.domain = domains[domain_id]

    def resolve(self, label_from: str) -> str:
        if label_from == "self":
            return self.name
        if label_from == "self_core":
            return _self_core(self.name)
        if label_from == "const.noConn":
            return "noConn"
        if label_from.startswith("domain."):
            key = label_from.split(".", 1)[1]
            if key not in self.domain:
                raise InputError(
                    f"Domain '{self.domain_id}' has no '{key}'",
                    position=self.position,
                    detail=f"domain definition: {self.domain}",
                    hint=(
                        "Define vdd_consumer, vss_consumer, vdd_provider, "
                        "and vss_provider for each T180 voltage-domain block."
                    ),
                    section="Semantic Intent Schema",
                )
            return self.domain[key]
        raise WiringError(f"Cannot resolve label_from '{label_from}'")


def _resolve_domain_id(instance: Dict[str, Any], domains: Dict[str, Any]) -> str:
    requested = instance.get("voltage_domain") or instance.get("domain")
    if requested in domains:
        return str(requested)

    if requested in ("analog", "digital"):
        matching = [key for key, value in domains.items() if value.get("kind") == requested]
        if len(matching) == 1:
            return matching[0]
        raise InputError(
            f"Instance domain '{requested}' is ambiguous",
            position=instance.get("position", ""),
            hint=(
                "Set instance.domain to a concrete domain id such as analog_1 "
                "or digital_1 when more than one domain of that kind exists."
            ),
            section="Semantic Intent Schema",
        )

    raise InputError(
        "Instance missing a valid domain id",
        position=instance.get("position", ""),
        device=instance.get("device", ""),
        hint="Set instance.domain to a key in top-level domains.",
        section="Semantic Intent Schema",
    )


def expand_instance(
    instance: Dict[str, Any],
    wiring: Dict[str, Any],
    domains: Dict[str, Any],
) -> Dict[str, Any]:
    for required in ("name", "position", "device"):
        if required not in instance:
            raise InputError(f"Instance missing '{required}' field", section="Semantic Intent Schema")

    name = instance["name"]
    position = instance["position"]
    device = instance["device"]
    inst_type = instance.get("type", "pad")

    kind, _side, _indices = parse_position(position)
    if kind == "corner" or inst_type == "corner":
        raise InputError(
            "Semantic intent must not include corner instances",
            position=position,
            hint="Remove corner entries; the T180 engine inserts PCORNER instances.",
            section="Semantic Intent Schema",
        )
    if inst_type != "pad":
        raise InputError(
            f"T180 semantic instance type must be 'pad', got '{inst_type}'",
            position=position,
            hint="T180 supports outer-ring pad instances in semantic intent.",
        )
    if device not in wiring["devices"]:
        raise InputError(
            f"Device '{device}' not in T180 wiring table",
            position=position,
            device=device,
            hint=f"Known devices: {sorted(wiring['devices'].keys())}",
            section="Step 2: Device Selection",
        )

    domain_id = _resolve_domain_id(instance, domains)
    domain = domains[domain_id]
    domain_kind = domain.get("kind")
    if domain_kind not in ("analog", "digital"):
        raise InputError(
            f"Domain '{domain_id}' kind must be analog or digital",
            position=position,
            detail=f"domain definition: {domain}",
        )

    digital_io = set(wiring.get("digital_io_devices", {}).get("list", []))
    if device in digital_io:
        if instance.get("direction") not in ("input", "output"):
            raise InputError(
                "Digital IO device requires direction",
                position=position,
                device=device,
                hint="Set direction to input or output for PDDW0412SCDG.",
                section="Step 4: Direction Determination",
            )
    elif "direction" in instance and instance["direction"] is not None:
        raise InputError(
            "Only digital IO instances may carry direction",
            position=position,
            device=device,
            hint="Remove direction from power, ground, analog IO, and corner instances.",
            section="Step 4: Direction Determination",
        )

    ctx = ResolutionContext(instance, domain_id, domains)
    pins = OrderedDict()
    for pin_name, pin_spec in wiring["devices"][device]["pins"].items():
        if not pin_spec.get("emit", True):
            continue
        pins[pin_name] = {"label": ctx.resolve(pin_spec["label_from"])}

    out = OrderedDict()
    out["name"] = name
    out["device"] = device
    out["view_name"] = "layout"
    out["domain"] = domain_kind
    out["voltage_domain"] = domain_id
    out["position"] = position
    out["type"] = "pad"
    if device in digital_io:
        out["direction"] = instance["direction"]
    out["pin_connection"] = pins
    return out


def _make_corner(position: str) -> Dict[str, Any]:
    return OrderedDict(
        [
            ("name", CORNER_NAMES[position]),
            ("device", "PCORNER"),
            ("view_name", "layout"),
            ("domain", "null"),
            ("position", position),
            ("type", "corner"),
        ]
    )


def insert_corners_in_sequence(instances: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not instances:
        return []

    sides = []
    for inst in instances:
        _kind, side, _indices = parse_position(inst["position"])
        sides.append(side)

    output: List[Dict[str, Any]] = []
    inserted = set()
    total = len(instances)
    for idx, inst in enumerate(instances):
        output.append(inst)
        next_side = sides[(idx + 1) % total]
        side = sides[idx]
        if side == next_side:
            continue
        corner_pos = CORNER_BY_SIDE_PAIR.get(frozenset((side, next_side)))
        if corner_pos and corner_pos not in inserted:
            output.append(_make_corner(corner_pos))
            inserted.add(corner_pos)

    missing = [pos for pos in CORNER_NAMES if pos not in inserted]
    if missing:
        raise GateError(
            "Corner insertion did not find all four side transitions",
            detail=f"missing={missing}",
            hint="Ensure the draft instances are ordered around the ring and include all four sides.",
            section="Step 5: Corner Insertion",
        )
    return output


def run_gates(intent_graph: Dict[str, Any], semantic: Dict[str, Any], wiring: Dict[str, Any]) -> Dict[str, Any]:
    instances = intent_graph["instances"]
    ring = intent_graph["ring_config"]
    width = int(ring.get("width", max(int(ring.get("top_count", 0)), int(ring.get("bottom_count", 0)))))
    height = int(ring.get("height", max(int(ring.get("left_count", 0)), int(ring.get("right_count", 0)))))
    results: Dict[str, Any] = {}

    side_counts = {"left": 0, "right": 0, "top": 0, "bottom": 0}
    positions = set()
    for inst in instances:
        pos = inst.get("position", "")
        if pos in positions:
            raise GateError("Duplicate position", position=pos)
        positions.add(pos)
        if inst.get("type") != "pad":
            continue
        _kind, side, _indices = parse_position(pos)
        side_counts[side] += 1
    expected = {
        "left": int(ring.get("left_count", height)),
        "right": int(ring.get("right_count", height)),
        "top": int(ring.get("top_count", width)),
        "bottom": int(ring.get("bottom_count", width)),
    }
    if side_counts != expected:
        raise GateError(
            "G1: Outer pad side counts mismatch",
            detail=f"expected={expected}, actual={side_counts}",
            hint="Check ring_config width/height and draft instance positions.",
        )
    results["G1_side_counts"] = {"pass": True, "counts": side_counts}

    corners = [i for i in instances if i.get("type") == "corner"]
    corner_positions = {i.get("position") for i in corners}
    if corner_positions != set(CORNER_NAMES):
        raise GateError(
            "G2: Corner positions mismatch",
            detail=f"found={sorted(corner_positions)}",
            hint="Engine should insert exactly top_left, top_right, bottom_right, bottom_left.",
        )
    results["G2_corners"] = {"pass": True}

    domains = semantic.get("domains", {})
    sem_instances = semantic.get("instances", [])
    for domain_id, domain in domains.items():
        domain_instances = [i for i in sem_instances if _safe_domain_id(i, domains) == domain_id]
        devices_by_name = [(i.get("name"), i.get("device")) for i in domain_instances]

        _check_named_role(domain_id, domain, devices_by_name, "vdd_provider", "PVDD2CDG")
        _check_named_role(domain_id, domain, devices_by_name, "vdd_consumer", "PVDD1CDG")
        _check_named_role(domain_id, domain, devices_by_name, "vss_consumer", "PVSS1CDG")

        vss_provider_name = domain.get("vss_provider")
        vss_providers = [
            name for name, device in devices_by_name
            if device == "PVSS2CDG"
        ]
        if not vss_providers:
            raise GateError(
                f"G3: Domain '{domain_id}' missing PVSS2CDG provider",
                hint=f"Add a PVSS2CDG instance named '{vss_provider_name}'.",
                section="Provider-Count Gate",
            )
        if any(name != vss_provider_name for name in vss_providers):
            raise GateError(
                f"G3: Domain '{domain_id}' has PVSS2CDG with wrong name",
                detail=f"expected all '{vss_provider_name}', found={sorted(set(vss_providers))}",
                section="Provider-Count Gate",
            )

    results["G3_provider_count"] = {"pass": True}

    for inst in instances:
        if inst.get("type") != "pad":
            continue
        vd = inst.get("voltage_domain")
        domain = domains.get(vd, {})
        pins = inst.get("pin_connection", {})
        if pins.get("VDD", {}).get("label") != domain.get("vdd_consumer"):
            raise GateError(
                "G4: VDD label does not match domain consumer",
                position=inst.get("position", ""),
                detail=f"expected={domain.get('vdd_consumer')}, actual={pins.get('VDD')}",
                section="VSS-Consistency Gate",
            )
        if pins.get("VSS", {}).get("label") != domain.get("vss_consumer"):
            raise GateError(
                "G4: VSS label does not match domain consumer",
                position=inst.get("position", ""),
                detail=f"expected={domain.get('vss_consumer')}, actual={pins.get('VSS')}",
                section="VSS-Consistency Gate",
            )
    results["G4_vdd_vss_consistency"] = {"pass": True}

    digital_io = set(wiring.get("digital_io_devices", {}).get("list", []))
    for inst in instances:
        if inst.get("type") == "pad" and inst.get("device") in digital_io and "direction" not in inst:
            raise GateError(
                "G5: Digital IO missing direction",
                position=inst.get("position", ""),
                device=inst.get("device", ""),
            )
    results["G5_direction_field"] = {"pass": True}

    warnings = _check_domain_continuity(intent_graph, domains)
    results["G6_domain_continuity"] = {"pass": True, "warnings": warnings}
    return results


def _safe_domain_id(instance: Dict[str, Any], domains: Dict[str, Any]) -> Optional[str]:
    try:
        return _resolve_domain_id(instance, domains)
    except InputError:
        return None


def _check_named_role(
    domain_id: str,
    domain: Dict[str, Any],
    devices_by_name: List[Tuple[str, str]],
    key: str,
    expected_device: str,
) -> None:
    expected_name = domain.get(key)
    if not expected_name:
        raise GateError(
            f"G3: Domain '{domain_id}' missing '{key}'",
            section="Semantic Intent Schema",
        )
    matches = [device for name, device in devices_by_name if name == expected_name]
    if expected_device == "PVDD2CDG":
        provider_matches = [device for name, device in devices_by_name if device == expected_device]
        if len(provider_matches) != 1:
            raise GateError(
                f"G3: Domain '{domain_id}' must contain exactly one {expected_device}",
                detail=f"found={len(provider_matches)}",
                section="Provider-Count Gate",
            )
    if expected_device not in matches:
        raise GateError(
            f"G3: Domain '{domain_id}' {key}='{expected_name}' does not use {expected_device}",
            detail=f"matching devices for name: {matches}",
            section="Provider-Count Gate",
        )


def _check_domain_continuity(intent_graph: Dict[str, Any], domains: Dict[str, Any]) -> List[str]:
    ring = intent_graph["ring_config"]
    width = int(ring.get("width", max(int(ring.get("top_count", 0)), int(ring.get("bottom_count", 0)))))
    height = int(ring.get("height", max(int(ring.get("left_count", 0)), int(ring.get("right_count", 0)))))
    placement = ring.get("placement_order", "counterclockwise")
    if placement == "counterclockwise":
        sides = [
            ("left", int(ring.get("left_count", height))),
            ("bottom", int(ring.get("bottom_count", width))),
            ("right", int(ring.get("right_count", height))),
            ("top", int(ring.get("top_count", width))),
        ]
    else:
        sides = [
            ("top", int(ring.get("top_count", width))),
            ("right", int(ring.get("right_count", height))),
            ("bottom", int(ring.get("bottom_count", width))),
            ("left", int(ring.get("left_count", height))),
        ]

    pos_to_domain = {
        inst["position"]: inst.get("voltage_domain")
        for inst in intent_graph["instances"]
        if inst.get("type") == "pad"
    }
    seq = []
    for side, count in sides:
        for idx in range(count):
            domain_id = pos_to_domain.get(f"{side}_{idx}")
            if domain_id:
                seq.append(domain_id)

    warnings = []
    for domain_id in domains:
        blocks = 0
        in_block = False
        for item in seq:
            if item == domain_id:
                if not in_block:
                    blocks += 1
                    in_block = True
            else:
                in_block = False
        if blocks > 1 and seq and seq[0] == domain_id and seq[-1] == domain_id:
            blocks -= 1
        if blocks > 1:
            warnings.append(
                f"Domain '{domain_id}' has {blocks} non-contiguous blocks; "
                "verify each block has its own provider/consumer pair."
            )
    return warnings


def enrich(semantic_path: Path, wiring_path: Path, output_path: Path) -> Dict[str, Any]:
    started = time.time()
    wiring = load_wiring_table(wiring_path)

    if not semantic_path.exists():
        raise InputError(f"Semantic intent file not found: {semantic_path}")
    try:
        semantic = json.loads(semantic_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        raise InputError(f"Semantic intent is not valid JSON: {e}")

    for required in ("ring_config", "instances", "domains"):
        if required not in semantic:
            raise InputError(
                f"Semantic intent missing top-level '{required}'",
                hint="See references/enrichment_rules_T180.md Semantic Intent Schema.",
                section="Semantic Intent Schema",
            )

    ring = semantic["ring_config"]
    for required in ("placement_order",):
        if required not in ring:
            raise InputError(f"ring_config missing '{required}'", section="Semantic Intent Schema")
    if ring["placement_order"] not in ("clockwise", "counterclockwise"):
        raise InputError("placement_order must be clockwise or counterclockwise")
    if "width" not in ring or "height" not in ring:
        count_fields = ("top_count", "bottom_count", "left_count", "right_count")
        if not all(field in ring for field in count_fields):
            raise InputError(
                "ring_config missing width/height or top_count/bottom_count/left_count/right_count",
                section="Semantic Intent Schema",
            )

    domains = semantic["domains"]
    if not isinstance(domains, dict) or not domains:
        raise InputError("domains must be a non-empty object", section="Semantic Intent Schema")

    expanded = [expand_instance(inst, wiring, domains) for inst in semantic["instances"]]
    with_corners = insert_corners_in_sequence(expanded)

    output_ring = OrderedDict()
    output_ring["process_node"] = "T180"
    for key, value in ring.items():
        if key == "process_node":
            continue
        output_ring[key] = value
    if "width" not in output_ring:
        output_ring["width"] = max(int(ring["top_count"]), int(ring["bottom_count"]))
    if "height" not in output_ring:
        output_ring["height"] = max(int(ring["left_count"]), int(ring["right_count"]))

    intent_graph = OrderedDict()
    intent_graph["ring_config"] = output_ring
    intent_graph["instances"] = with_corners

    gates = run_gates(intent_graph, semantic, wiring)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(intent_graph, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "intent_graph": intent_graph,
        "duration_ms": int((time.time() - started) * 1000),
        "gates": gates,
    }
