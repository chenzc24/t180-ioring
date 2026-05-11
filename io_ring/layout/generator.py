#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
T180 Layout Generator - Complete independent implementation for T180 process node
No inheritance, completely standalone
Includes PSUB2 generation specific to T180
"""

import os
import json
import re
from typing import Dict, Tuple, List, Optional

from .device_classifier import DeviceClassifier
from .voltage_domain import VoltageDomainHandler
from .position_calculator import PositionCalculator
from .filler_generator import FillerGenerator
from .validator import LayoutValidator
from .skill_generator import SkillGeneratorT180
from .auto_filler import AutoFillerGeneratorT180
from .confirmed_config import build_confirmed_config_from_io_config
from .process_config import get_process_node_config
from .visualizer import visualize_layout_T180, visualize_layout_from_components_T180



class LayoutGeneratorT180:
    """T180 Layout Generator - Standalone implementation"""
    
    def __init__(self):
        # Get 180nm configuration
        node_config = get_process_node_config()
        
        # Default configuration for 180nm
        self.config = {
            "library_name": node_config["library_name"],
            "view_name": "layout",
            "pad_width": node_config["pad_width"],
            "pad_height": node_config["pad_height"],
            "corner_size": node_config["corner_size"],
            "pad_spacing": node_config["pad_spacing"],
            "placement_order": "counterclockwise",
            "filler_components": node_config["filler_components"],
            "process_node": "T180"
        }
        
        # Store device_masters from config
        if "device_masters" in node_config:
            self.config["device_masters"] = node_config["device_masters"]
        
        # Initialize modules
        self.position_calculator = PositionCalculator(self.config)
        self.voltage_domain_handler = VoltageDomainHandler()
        self.filler_generator = FillerGenerator()
        self.layout_validator = LayoutValidator()
        self.skill_generator = SkillGeneratorT180(self.config)
        self.auto_filler_generator = AutoFillerGeneratorT180(self.config)
        # Instantiate classifier for instance-based queries (matching merge_source)
        self.classifier = DeviceClassifier(process_node="T180")
    
    def sanitize_skill_instance_name(self, name: str) -> str:
        """Sanitize instance names for SKILL compatibility"""
        sanitized = name.replace('<', '_').replace('>', '_')
        while '__' in sanitized:
            sanitized = sanitized.replace('__', '_')
        return sanitized
    
    def set_config(self, config: dict):
        """Set configuration parameters"""
        self.config.update(config)
        self.position_calculator.config = self.config
        self.position_calculator.current_ring_config = self.config
        self.skill_generator.config = self.config
        self.auto_filler_generator.config = self.config
    
    def calculate_chip_size(self, layout_components: List[dict]) -> Tuple[int, int]:
        """Calculate chip size based on layout components"""
        return self.position_calculator.calculate_chip_size(layout_components)

    def _extract_relative_position(self, instance: dict) -> str:
        """Extract relative position string from instance fields."""
        raw_position = instance.get("position", "")
        if isinstance(raw_position, str):
            return raw_position
        return ""

    def _parse_side_index(self, relative_position: str) -> Tuple[Optional[str], Optional[int]]:
        """Parse side-index format: top_0/right_2/bottom_5/left_1."""
        if not isinstance(relative_position, str):
            return None, None
        parts = relative_position.split("_")
        if len(parts) == 2 and parts[0] in {"top", "right", "bottom", "left"} and parts[1].isdigit():
            return parts[0], int(parts[1])
        return None, None

    def _get_component_type(self, instance: dict) -> str:
        """Resolve component type using explicit type first, then device."""
        comp_type = instance.get("type")
        if isinstance(comp_type, str) and comp_type:
            return comp_type

        device = str(instance.get("device", ""))
        if DeviceClassifier.is_corner_device(device, "T180"):
            return "corner"
        if DeviceClassifier.is_filler_device(device, "T180"):
            return "filler"
        if device.upper() == "BLANK":
            return "blank"
        return "pad"

    def _resolve_component_geometry(self, instance: dict, component_type: str, ring_config: dict) -> Tuple[float, float]:
        """Resolve geometry by component type for T180.

        - pad/corner: use pad_width/pad_height defaults
        - filler/blank: use pad_width/pad_height; infer PFILLERxx width; blank defaults to 10
        """
        default_pad_width = float(ring_config.get("pad_width", self.config.get("pad_width", 80)))
        default_pad_height = float(ring_config.get("pad_height", self.config.get("pad_height", 120)))

        if component_type not in {"filler", "blank"}:
            width = instance.get("pad_width", default_pad_width)
            height = instance.get("pad_height", default_pad_height)
            width = float(width) if isinstance(width, (int, float)) else default_pad_width
            height = float(height) if isinstance(height, (int, float)) else default_pad_height
            return width, height

        width = instance.get("pad_width")
        height = instance.get("pad_height")

        if not isinstance(width, (int, float)):
            match = re.search(r"PFILLER(\d+)", str(instance.get("device", "")).upper())
            if match:
                width = int(match.group(1))
            elif component_type == "blank":
                width = 10
            else:
                pad_like = instance.get("pad_width")
                width = pad_like if isinstance(pad_like, (int, float)) and float(pad_like) <= 20 else 10

        if not isinstance(height, (int, float)):
            pad_like_h = instance.get("pad_height")
            height = pad_like_h if isinstance(pad_like_h, (int, float)) else default_pad_height

        return float(width), float(height)

    def _build_t180_side_sequences(self, instances: List[dict], ring_config: dict) -> Dict[str, dict]:
        """Build per-side cumulative width map for side-indexed components."""
        placement_order = ring_config.get("placement_order", "counterclockwise")
        side_index_widths: Dict[str, Dict[int, float]] = {
            "top": {},
            "right": {},
            "bottom": {},
            "left": {},
        }

        for instance in instances:
            side, index = self._parse_side_index(self._extract_relative_position(instance))
            if side is None or index is None:
                continue
            if index not in side_index_widths[side]:
                comp_type = self._get_component_type(instance)
                width, _ = self._resolve_component_geometry(instance, comp_type, ring_config)
                side_index_widths[side][index] = width

        sequence_map: Dict[str, dict] = {}
        for side, idx_map in side_index_widths.items():
            if not idx_map:
                sequence_map[side] = {"max_index": -1, "prefix_sum": {}}
                continue

            max_index = max(idx_map.keys())
            ranked = []
            for logical_index, width in idx_map.items():
                real_index = logical_index if placement_order == "clockwise" else (max_index - logical_index)
                ranked.append((real_index, logical_index, width))
            ranked.sort(key=lambda item: item[0])

            cumulative = 0.0
            prefix_sum: Dict[int, float] = {}
            for _, logical_index, width in ranked:
                cumulative += width
                prefix_sum[logical_index] = cumulative

            sequence_map[side] = {"max_index": max_index, "prefix_sum": prefix_sum}

        return sequence_map

    def _calculate_t180_cumulative_position(
        self,
        relative_position: str,
        ring_config: dict,
        side_sequences: Dict[str, dict],
    ) -> Optional[Tuple[List[float], str]]:
        """Calculate T180 side component position by cumulative sequence width."""
        chip_width = ring_config.get("chip_width")
        chip_height = ring_config.get("chip_height")
        if not isinstance(chip_width, (int, float)):
            chip_width = 2250
        if not isinstance(chip_height, (int, float)):
            chip_height = 2160
        corner_size = ring_config.get("corner_size", self.config.get("corner_size", 130))

        if relative_position == "top_left":
            return [0, chip_height], "R270"
        if relative_position == "top_right":
            return [chip_width, chip_height], "R180"
        if relative_position == "bottom_left":
            return [0, 0], "R0"
        if relative_position == "bottom_right":
            return [chip_width, 0], "R90"

        side, logical_index = self._parse_side_index(relative_position)
        if side is None or logical_index is None:
            return None

        side_info = side_sequences.get(side, {})
        prefix_sum = side_info.get("prefix_sum", {})
        if logical_index not in prefix_sum:
            return None

        cumulative_distance = prefix_sum[logical_index]
        if side == "top":
            return [corner_size + cumulative_distance, chip_height], "R180"
        if side == "bottom":
            return [chip_width - corner_size - cumulative_distance, 0], "R0"
        if side == "left":
            return [0, corner_size + cumulative_distance], "R270"
        if side == "right":
            return [chip_width, chip_height - corner_size - cumulative_distance], "R90"
        return None
    
    def convert_relative_to_absolute(self, instances: List[dict], ring_config: dict, require_corners: bool = True) -> List[dict]:
        """Convert relative positions to absolute positions for 180nm format.

        Supports mixed inputs:
        - relative position strings (converted)
        - absolute [x, y] positions (kept, orientation preserved if present)
        """
        converted_components = []
        side_sequences = self._build_t180_side_sequences(instances, ring_config)
        
        for instance in instances:
            raw_position = instance.get("position", "")
            name = instance.get("name", "")
            relative_pos = self._extract_relative_position(instance)
            # Use device field
            device = instance.get("device", "")
            if not device:
                raise ValueError(f"[ERROR] Error: Instance '{name}' must have 'device' field")
            
            component_type = self._get_component_type(instance)
            
            direction = instance.get("direction", "")
            voltage_domain = instance.get("voltage_domain", {})
            pin_connection = instance.get("pin_connection", {})
            domain = instance.get("domain", "")
            view_name = instance.get("view_name", "layout")
            geom_width, geom_height = self._resolve_component_geometry(instance, component_type, ring_config)
            
            has_relative_semantics = isinstance(relative_pos, str) and bool(relative_pos)
            if isinstance(raw_position, (list, tuple)) and len(raw_position) == 2 and not has_relative_semantics:
                position = [raw_position[0], raw_position[1]]
                orientation = instance.get("orientation", "R0")
            else:
                cumulative_result = self._calculate_t180_cumulative_position(relative_pos, ring_config, side_sequences)
                if cumulative_result is not None:
                    position, orientation = cumulative_result
                else:
                    # Fallback to shared legacy calculator for non side-index formats.
                    if component_type in {"filler", "blank"}:
                        position, orientation = self.position_calculator.calculate_filler_position_from_relative(relative_pos, ring_config, instance)
                    else:
                        position, orientation = self.position_calculator.calculate_position_from_relative(relative_pos, ring_config, instance)
            
            # Build component configuration - use device field
            component = {
                "view_name": view_name,
                "type": component_type,
                "name": name,
                "device": device,  # Use device field
                "domain": domain,
                "position": position,
                "orientation": orientation,
            }
            # Geometry is resolved internally for position calculation.
            # pad_width/pad_height are NOT added to the component dict.
            # Downstream consumers (skill_generator, visualizer) derive
            # dimensions from ring_config defaults or device name patterns.
            
            if has_relative_semantics:
                component["position_str"] = relative_pos
            
            if direction:
                component["direction"] = direction
            
            if voltage_domain:
                component["voltage_domain"] = voltage_domain
            if pin_connection:
                component["pin_connection"] = pin_connection
            
            converted_components.append(component)
        
        # Check corners
        has_corners = any(comp.get("type") == "corner" for comp in converted_components)
        if not has_corners:
            raise ValueError("[ERROR] Error: Corner components are missing in the intent graph!")

        return converted_components


def generate_layout_skill_from_components(
    generator: LayoutGeneratorT180,
    ring_config: dict,
    all_components_with_fillers: List[dict],
    output_file: str,
):
    """Generate 180nm layout SKILL script from finalized components only."""
    print("[>>] Starting Layout Skill script generation...")

    def ensure_unique_nonfunctional_names(components: List[dict]) -> List[dict]:
        used_names = set()
        for component in components:
            if not isinstance(component, dict):
                continue

            comp_type = component.get("type")
            device = str(component.get("device", ""))
            is_nonfunctional = comp_type in {"filler", "blank"} or generator.classifier.is_filler(device)

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

    final_components_input = list(all_components_with_fillers)

    final_components = generator.convert_relative_to_absolute(
        final_components_input,
        ring_config,
        require_corners=False,
    )
    final_components = ensure_unique_nonfunctional_names(final_components)

    outer_pads = [comp for comp in final_components if comp.get("type") == "pad"]
    corners = [comp for comp in final_components if comp.get("type") == "corner"]
    all_instances = final_components
    all_components_with_fillers = final_components
    filler_components = [
        comp
        for comp in all_instances
        if comp.get("type") != "blank"
        and (comp.get("type") == "filler" or generator.classifier.is_filler(comp.get("device", "")))
    ]

    skill_commands = []
    
    skill_commands.append("cv = geGetEditCellView()")
    # File header
    skill_commands.append("; Generated Layout Script for T180")
    skill_commands.append("")
    
    # Sort components
    placement_order = ring_config.get("placement_order", "counterclockwise")
    all_components = outer_pads + corners
    sorted_components = generator.position_calculator.sort_components_by_position(all_components, placement_order)
    
    # 1. Generate all components (matching merge_source format)
    skill_commands.append("; ==================== All Components (Sorted by Placement Order) ====================")
    for i, component in enumerate(sorted_components):
        x, y = component["position"]
        orientation = component["orientation"]
        device = component["device"]  # Use device field
        name = component["name"]
        component_type = component["type"]
        position_str = component.get('position_str', 'abs')
        lib = ring_config.get("library_name", generator.config.get("library_name", "tpd018bcdnv5"))
        view = component.get("view_name", ring_config.get("view_name", "layout"))
        
        # Use name_position_str format (matching merge_source, no sanitization)
        skill_commands.append(f'dbCreateParamInstByMasterName(cv "{lib}" "{device}" "{view}" "{name}_{position_str}" list({x} {y}) "{orientation}")')
        
        # Add PAD70 for pad components with adjusted orientation/position (matching merge_source)
        if component_type == "pad":
            orient_map = {"R0": "R180", "R90": "R270", "R180": "R0", "R270": "R90"}
            pad70_orient = orient_map.get(orientation, "R0")
            
            # Centering along tangent using |pad_width - 70| correction (half for centering)
            pad_w = component.get("pad_width")
            if not isinstance(pad_w, (int, float)):
                pad_w = ring_config.get("pad_width")
            if not isinstance(pad_w, (int, float)):
                pad_w = generator.config.get("pad_width", 80)
            PAD_width = 70
            center_correction = abs(pad_w - PAD_width) / 2
            
            # Initialize defaults to current pad origin if not set by branch
            x70 = x
            y70 = y
            if orientation == "R0":          # bottom edge, tangent: +X
                x70 = x + pad_w - center_correction
            elif orientation == "R180":      # top edge, tangent: +X
                x70 = x + center_correction - pad_w
            elif orientation == "R90":       # right edge, tangent: +Y
                y70 = y + pad_w - center_correction
            elif orientation == "R270":      # left edge, tangent: +Y
                y70 = y + center_correction - pad_w
            # Get pad library and master from config
            device_masters = ring_config.get("device_masters", {})
            pad_library = device_masters.get("pad_library", "tpb018v_cup_6lm")
            pad_master = device_masters.get("pad_master", "PAD70LU_TRL")
            skill_commands.append(
                f'dbCreateParamInstByMasterName(cv "{pad_library}" "{pad_master}" "layout" "pad70lu_{name}_{position_str}" list({x70} {y70}) "{pad70_orient}")'
            )
    
    skill_commands.append("")
    
    # 2. PSUB2_layer Drawing (matching merge_source)
    skill_commands.append("; ==================== PSUB2 Layer ====================")
    PSUB2_commands = generator.skill_generator.generate_psub2(all_components_with_fillers, corners, ring_config)
    skill_commands.extend(PSUB2_commands)
    skill_commands.append("")
    
    # 3. Filler components (matching merge_source)
    skill_commands.append("; ==================== Filler Components ====================")
    
    for filler in filler_components:
        position = filler.get("position", [0, 0])
        orientation = filler.get("orientation", "R0")
        device = filler.get("device", "PFILLER10")
        name = str(filler.get("name", "")).strip()
        position_str = filler.get("position_str")
        if not isinstance(position_str, str) or not position_str:
            pos_field = filler.get("position")
            position_str = pos_field if isinstance(pos_field, str) and pos_field else "abs"
        skill_inst_name = f"{name}_{position_str}" if name else f"filler_{position_str}"
        x, y = position
        lib = ring_config.get("library_name", generator.config.get("library_name", "tpd018bcdnv5"))
        view = filler.get("view_name", ring_config.get("view_name", "layout"))
        skill_commands.append(f'dbCreateParamInstByMasterName(cv "{lib}" "{device}" "{view}" "{skill_inst_name}" list({x} {y}) "{orientation}")')
  
    skill_commands.append("")
    
    # 5. Digital IO features
    skill_commands.append("; ==================== Digital IO Features ====================")
    digital_io_commands = generator.skill_generator.generate_digital_io_features(outer_pads, ring_config)
    skill_commands.extend(digital_io_commands)
    skill_commands.append("")

    # 6. Pin labels
    skill_commands.append("; ==================== Pin Labels ====================")
    pin_label_commands = generator.skill_generator.generate_pin_labels(outer_pads, ring_config)
    skill_commands.extend(pin_label_commands)
    skill_commands.append("")
    skill_commands.append("dbSave(cv)")

    # Write to file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(skill_commands))
    
    # Generate visualization (T180 uses layout_visualizer_T180)
    try:
        output_dir = os.path.dirname(output_file) or "output"
        vis_name = os.path.splitext(os.path.basename(output_file))[0] + "_visualization.png"
        visualization_path = os.path.join(output_dir, vis_name)
        os.makedirs(output_dir, exist_ok=True)
        # Use component-based visualization to support blank types
        visualize_layout_from_components_T180(all_components_with_fillers, visualization_path, ring_config)
        print(f"[STATS] Visualization generated: {visualization_path}")
    except Exception as e:
        print(f"[WARN]  Visualization generation failed: {e}")
    
    # Calculate chip size (matching merge_source)
    chip_width, chip_height = ring_config.get("chip_width", 2250), ring_config.get("chip_height", 2160)
    total_components = len(all_components_with_fillers)

    print(f"[DIM] Chip size: {chip_width} x {chip_height}")
    print(f"[STATS] Total components: {total_components}")
    print(f"[OK] Layout Skill script generated: {output_file}")
    
    return output_file


def generate_layout_from_json(json_file: str, output_file: str = "generated_layout.il"):
    """Generate 180nm layout from JSON by consuming confirmed config and then generating SKILL."""

    confirmed_json_path = json_file
    with open(confirmed_json_path, 'r', encoding='utf-8') as f:
        confirmed_config = json.load(f)

    ring_config = confirmed_config.get("ring_config", {})
    instances = confirmed_config.get("instances", [])

    generator = LayoutGeneratorT180()
    generator.set_config(ring_config)

    all_components_with_fillers = [inst for inst in instances if isinstance(inst, dict)]

    return generate_layout_skill_from_components(
        generator=generator,
        ring_config=ring_config,
        all_components_with_fillers=all_components_with_fillers,
        output_file=output_file,
    )

