#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build confirmed IO config from initial io_config (T180): filler + IO editor confirmation only."""

import json
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from .device_classifier import DeviceClassifier
from .validator import LayoutValidator
from .auto_filler import AutoFillerGeneratorT180


def _ensure_unique_nonfunctional_names(classifier: DeviceClassifier, components: List[dict]) -> List[dict]:
    used_names = set()
    for component in components:
        if not isinstance(component, dict):
            continue

        comp_type = component.get("type")
        device = str(component.get("device", ""))
        is_nonfunctional = comp_type in {"filler", "blank"} or classifier.is_filler(device)

        raw_name = component.get("name")
        name = str(raw_name).strip() if raw_name is not None else ""

        if not is_nonfunctional:
            if name:
                used_names.add(name)
            continue

        base_name = name or f"{comp_type or 'instance'}"
        candidate = base_name

        if candidate in used_names:
            relative_pos = component.get("position_str")
            if not isinstance(relative_pos, str) or not relative_pos:
                pos_field = component.get("position")
                relative_pos = pos_field if isinstance(pos_field, str) and pos_field else ""

            candidate = f"{base_name}_{relative_pos}" if relative_pos else base_name
            dedup_index = 1
            while candidate in used_names:
                candidate = f"{base_name}_{dedup_index}"
                dedup_index += 1

            component["name"] = candidate

        used_names.add(candidate)

    return components


def _prepare_t180_components(
    source_json_path: str,
) -> Tuple[Any, DeviceClassifier, LayoutValidator, AutoFillerGeneratorT180, dict, List[dict]]:
    with open(source_json_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    instances = config.get("instances", [])
    ring_config = config.get("ring_config", {})
    ring_config["process_node"] = "T180"

    from .generator import LayoutGeneratorT180

    generator = LayoutGeneratorT180()

    if ring_config.get("chip_width") is None or ring_config.get("chip_height") is None:
        pad_spacing = ring_config.get("pad_spacing", generator.config["pad_spacing"])
        corner_size = ring_config.get("corner_size", generator.config["corner_size"])

        def _as_count(value, default=3):
            if isinstance(value, (int, float)):
                return int(value)
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        top_count = _as_count(ring_config.get("top_count", 3))
        bottom_count = _as_count(ring_config.get("bottom_count", 3))
        left_count = _as_count(ring_config.get("left_count", 3))
        right_count = _as_count(ring_config.get("right_count", 3))
        width_filler10 = 10

        if ring_config.get("chip_width") is None:
            horizontal_count = max(top_count, bottom_count)
            ring_config["chip_width"] = horizontal_count * pad_spacing + corner_size * 2 + width_filler10
        if ring_config.get("chip_height") is None:
            vertical_count = max(left_count, right_count)
            ring_config["chip_height"] = vertical_count * pad_spacing + corner_size * 2 + width_filler10

    if "library_name" in config and "library_name" not in ring_config:
        ring_config["library_name"] = config["library_name"]
    if "cell_name" in config and "cell_name" not in ring_config:
        ring_config["cell_name"] = config["cell_name"]

    generator.set_config(ring_config)
    if "pad_width" not in ring_config:
        ring_config["pad_width"] = generator.config["pad_width"]
    if "pad_height" not in ring_config:
        ring_config["pad_height"] = generator.config["pad_height"]
    if "corner_size" not in ring_config:
        ring_config["corner_size"] = generator.config["corner_size"]
    if "pad_spacing" not in ring_config:
        ring_config["pad_spacing"] = generator.config["pad_spacing"]
    if "library_name" not in ring_config:
        ring_config["library_name"] = generator.config["library_name"]
    if "view_name" not in ring_config:
        ring_config["view_name"] = generator.config["view_name"]
    if "device_masters" not in ring_config:
        ring_config["device_masters"] = generator.config.get("device_masters", {})

    classifier = DeviceClassifier(process_node="T180")
    layout_validator = LayoutValidator()
    auto_filler_generator = AutoFillerGeneratorT180(generator.config)

    outer_pads = []
    corners = []
    for instance in instances:
        if instance.get("type") == "pad":
            outer_pads.append(instance)
        elif instance.get("type") == "corner":
            corners.append(instance)

    validation_source_components = outer_pads + corners
    validation_components = generator.convert_relative_to_absolute(
        validation_source_components,
        ring_config,
        require_corners=True,
    )
    validation_result = layout_validator.validate_layout_rules(validation_components, "T180")
    if not validation_result["valid"]:
        raise ValueError(f"Layout rule validation failed: {validation_result['message']}")

    has_input_fillers = any(
        comp.get("type") == "filler" or classifier.is_filler(comp.get("device", ""))
        for comp in instances
    )
    if has_input_fillers:
        all_components_with_fillers = instances
    else:
        all_components_with_fillers = auto_filler_generator.auto_insert_default_fillers(validation_source_components)

    all_components_with_fillers = _ensure_unique_nonfunctional_names(classifier, all_components_with_fillers)
    return generator, classifier, layout_validator, auto_filler_generator, ring_config, all_components_with_fillers


def _import_traceback_if_error() -> str:
    return traceback.format_exc()


def run_t180_editor_confirmation_pipeline(
    json_file: str,
    ring_config: Dict[str, Any],
    all_components_with_fillers: List[dict],
    generator: Any,
    editor_output_path: Optional[str] = None,
    skip_editor_confirmation: bool = False,
) -> Dict[str, Any]:
    """Run T180 IO-editor confirmation pipeline and return updated runtime payload.

    Args:
        json_file: Source JSON config file path
        ring_config: Ring configuration dict
        all_components_with_fillers: List of all components with auto-inserted fillers
        generator: Layout generator instance
        editor_output_path: Optional path for intermediate editor JSON export
        skip_editor_confirmation: If True, skip GUI editor wait loop (CLI mode).
                                  Fillers are still inserted and confirmed JSON is auto-generated.
    """
    result = {
        "ring_config": ring_config,
        "all_components_with_fillers": all_components_with_fillers,
        "all_instances": all_components_with_fillers,
        "outer_pads": [c for c in all_components_with_fillers if isinstance(c, dict) and c.get("type") == "pad"],
        "corners": [c for c in all_components_with_fillers if isinstance(c, dict) and c.get("type") == "corner"],
        "editor_path": None,
        "editor_payload": None,
    }

    # CLI mode: auto-generate confirmed JSON without GUI editor wait
    if skip_editor_confirmation:
        print(f"[CLI] CLI mode: Auto-generating confirmed config (no GUI editor)...")
        # Use the filler-completed layout as the confirmed payload
        editor_payload = {
            "ring_config": ring_config,
            "instances": all_components_with_fillers,
        }
        result["editor_payload"] = editor_payload
        print(f"[OK] Auto-confirmed layout generated with {len(all_components_with_fillers)} components")
        # Early return - skip export and GUI wait logic
        return result

    # GUI mode: export intermediate JSON and wait for user confirmation
    try:
        from io_ring.editor.utils import export_to_editor_json
        from .visualizer import DEVICE_COLORS_180NM as VISUAL_COLORS

        json_path = Path(json_file)
        if editor_output_path:
            editor_path = Path(editor_output_path)
            if editor_path.suffix.lower() != ".json":
                editor_path = editor_path.with_suffix(".json")
        else:
            editor_path = json_path.parent / f"{json_path.stem}_intermediate_editor.json"

        print(f"[SAVE] Exporting intermediate layout for Editor validation: {editor_path}")
        exported_path = export_to_editor_json(
            all_components_with_fillers,
            ring_config,
            VISUAL_COLORS,
            str(editor_path),
        )
        editor_path = Path(exported_path)
        # Wait for confirmation next to the exported intermediate JSON so
        # backend polling path matches /api/agent/editor/confirm write path.
        editor_stem = editor_path.stem
        if editor_stem.endswith("_intermediate_editor"):
            editor_stem = editor_stem[: -len("_intermediate_editor")]
        confirmed_path = editor_path.with_name(f"{editor_stem}_confirmed.json")

        # GUI mode: wait for user to edit in frontend
        initial_confirmed_mtime = (
            confirmed_path.stat().st_mtime if confirmed_path.exists() else 0
        )

        print(f"⏳ SUSPENDING EXECUTION: Waiting for user confirmation at {confirmed_path}...")
        print("   PLEASE EDIT AND SAVE/CONFIRM IN THE FRONTEND TO CONTINUE.")

        print(f"   Waiting for updates on {confirmed_path.name}...")
        while True:
            if confirmed_path.exists():
                current_mtime = confirmed_path.stat().st_mtime
                if current_mtime > initial_confirmed_mtime:
                    break
            time.sleep(2)

        print(f"[OK] Confirmation received! Loading validated layout from {confirmed_path}")

        with open(confirmed_path, "r", encoding="utf-8") as f:
            idx_data = json.load(f)
        result["editor_path"] = str(editor_path)
        result["editor_payload"] = idx_data

        # Process editor payload
        if "ring_config" in idx_data:
            print("   Updating ring configuration from editor...")
            ring_config.update(idx_data["ring_config"])
            if hasattr(generator, "config"):
                generator.config.update(idx_data["ring_config"])

        incoming_components = None
        if "layout_data" in idx_data:
            incoming_components = idx_data["layout_data"]
        elif "instances" in idx_data:
            incoming_components = idx_data["instances"]

        if incoming_components is not None:
            print(f"   Updating layout components from editor ({len(incoming_components)} items)...")
            result["all_components_with_fillers"] = incoming_components
            result["all_instances"] = incoming_components

            new_pads = []
            new_corners = []
            for comp in incoming_components:
                c_type = comp.get("type", "unknown") if isinstance(comp, dict) else "unknown"
                if c_type == "pad":
                    new_pads.append(comp)
                elif c_type == "corner":
                    new_corners.append(comp)

            result["outer_pads"] = new_pads
            result["corners"] = new_corners
            print(f"   Re-classified: {len(new_pads)} pads, {len(new_corners)} corners")

    except ImportError:
        print("[WARN]  Warning: editor_utils not found, skipping intermediate export.")
    except Exception as e:
        print(f"[WARN]  Failed to export intermediate layout: {e}\n{_import_traceback_if_error()}")

    return result


def build_confirmed_config_from_io_config(
    source_json_path: str,
    confirmed_output_path: Optional[str] = None,
    skip_editor_confirmation: bool = False,
) -> str:
    """Build confirmed config JSON from initial io_config.

    Flow: source io_config -> filler completion -> IO editor confirmation -> write *_confirmed.json

    Args:
        source_json_path: Path to source intent graph JSON
        confirmed_output_path: Optional output path for confirmed JSON
        skip_editor_confirmation: If True, skip GUI editor wait (CLI mode).
                                  Filler insertion still runs; confirmed JSON is auto-generated.
    """
    source_path = Path(source_json_path)
    if not source_path.exists():
        raise FileNotFoundError(f"Source config not found: {source_json_path}")
    if source_path.suffix.lower() != ".json":
        raise ValueError(f"Invalid JSON file: {source_json_path}")

    if confirmed_output_path:
        confirmed_path = Path(confirmed_output_path)
        if confirmed_path.suffix.lower() != ".json":
            confirmed_path = confirmed_path.with_suffix(".json")
    else:
        confirmed_path = source_path.with_name(f"{source_path.stem}_confirmed.json")

    output_stem = confirmed_path.stem
    if output_stem.endswith("_confirmed"):
        output_stem = output_stem[: -len("_confirmed")]
    intermediate_path = confirmed_path.with_name(f"{output_stem}_intermediate_editor.json")

    generator, _, _, _, ring_config, all_components_with_fillers = _prepare_t180_components(str(source_path))

    pipeline_result = run_t180_editor_confirmation_pipeline(
        json_file=str(source_path),
        ring_config=ring_config,
        all_components_with_fillers=all_components_with_fillers,
        generator=generator,
        editor_output_path=str(intermediate_path),
        skip_editor_confirmation=skip_editor_confirmation,
    )

    editor_payload = pipeline_result.get("editor_payload")
    if not isinstance(editor_payload, dict):
        raise RuntimeError("Editor confirmation payload not available")

    confirmed_path.parent.mkdir(parents=True, exist_ok=True)
    with open(confirmed_path, "w", encoding="utf-8") as f:
        json.dump(editor_payload, f, ensure_ascii=False, indent=2)

    return str(confirmed_path)


def build_draft_editor_session(
    draft_json_path: str,
    confirmed_output_path: Optional[str] = None,
    skip_editor_confirmation: bool = False,
) -> str:
    """Open the editor in draft mode with minimal instance data.

    Draft mode accepts instances with just name/position/type (and optionally
    device). No fillers, corners, or pin connections are required or generated.
    The confirmed output is a simple JSON carrying only what the user provided.

    Args:
        draft_json_path: Path to draft JSON with minimal instances.
        confirmed_output_path: Optional output path for confirmed JSON.
        skip_editor_confirmation: If True, skip GUI editor and auto-generate output.

    Returns:
        Path to the confirmed JSON file.
    """
    source_path = Path(draft_json_path)
    if not source_path.exists():
        raise FileNotFoundError(f"Draft config not found: {draft_json_path}")

    with open(source_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    raw_instances = config.get("instances")
    if not isinstance(raw_instances, list):
        raw_instances = config.get("layout_data", [])
    instances = raw_instances if isinstance(raw_instances, list) else []
    ring_config = config.get("ring_config", {})
    if not isinstance(ring_config, dict):
        ring_config = {}
    ring_config.setdefault("process_node", "T180")
    ring_config.setdefault("placement_order", "counterclockwise")

    if confirmed_output_path:
        confirmed_path = Path(confirmed_output_path)
        if confirmed_path.suffix.lower() != ".json":
            confirmed_path = confirmed_path.with_suffix(".json")
    else:
        confirmed_path = source_path.with_name(f"{source_path.stem}_confirmed.json")

    output_stem = confirmed_path.stem
    if output_stem.endswith("_confirmed"):
        output_stem = output_stem[: -len("_confirmed")]
    intermediate_path = confirmed_path.with_name(f"{output_stem}_intermediate_editor.json")

    try:
        from io_ring.editor.utils import draft_to_editor_json
        from .visualizer import DEVICE_COLORS_180NM as VISUAL_COLORS
    except ImportError:
        from io_ring.editor.utils import draft_to_editor_json
        VISUAL_COLORS = {}

    print(f"[draft_editor] Building draft editor JSON from {len(instances)} instances...")
    exported_path = draft_to_editor_json(
        draft_instances=instances,
        ring_config=ring_config,
        visual_colors=VISUAL_COLORS,
        output_path=str(intermediate_path),
    )

    if skip_editor_confirmation:
        print(f"[draft_editor] CLI mode: Auto-generating draft config (no GUI editor)...")
        editor_payload = {
            "ring_config": ring_config,
            "editor_mode": "draft",
            "instances": instances,
        }
        confirmed_path.parent.mkdir(parents=True, exist_ok=True)
        with open(confirmed_path, "w", encoding="utf-8") as f:
            json.dump(editor_payload, f, ensure_ascii=False, indent=2)
        print(f"[draft_editor] Done. Auto-generated draft config at {confirmed_path}")
        return str(confirmed_path)

    print(f"[draft_editor] Launching browser-based Draft Editor...")
    try:
        from io_ring.editor.launcher import launch_layout_editor
        launch_layout_editor(
            intermediate_json=str(exported_path),
            confirmed_json=str(confirmed_path),
            mode="draft",
        )
    except ImportError:
        import subprocess
        import sys
        launcher_script = Path(__file__).parent.parent / "editor" / "launcher.py"
        print(f"   (Using subprocess launcher: {launcher_script})")
        proc = subprocess.run(
            [sys.executable, str(launcher_script), str(exported_path), str(confirmed_path), "--mode", "draft"],
            capture_output=False,
            text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"Draft editor exited with code {proc.returncode}")

    print(f"[draft_editor] Done. Draft confirmed at {confirmed_path}")
    return str(confirmed_path)
