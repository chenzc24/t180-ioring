#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Schematic Generator for 180nm process node - Specialized for generating SKILL code
"""

import math
import re
import sys
import os
from pathlib import Path
from typing import Dict, Any, Optional, Tuple


# Import device template parser from the correct location (180nm)
from io_ring.schematic.device_parser import DeviceTemplate, DeviceTemplateManager
from io_ring.validation.json_validator import validate_config, convert_config_to_list, get_config_statistics

class SchematicGenerator:
    def __init__(self, template_manager):
        self.template_manager = template_manager
    
    def sanitize_skill_instance_name(self, name: str) -> str:
        """
        Sanitize instance names for SKILL compatibility.
        Replace < > with _ (underscore) for instance names.
        
        Args:
            name: Original instance name
            
        Returns:
            Sanitized instance name safe for SKILL
        """
        # Replace < > with _ (underscore) for SKILL instance name compatibility
        sanitized = name.replace('<', '_').replace('>', '_')
        # Collapse multiple consecutive underscores into a single underscore
        while '__' in sanitized:
            sanitized = sanitized.replace('__', '_')
        return sanitized
    
    def format_skill_net_label(self, label: str) -> str:
        """
        Format net labels for SKILL compatibility.
        Convert format from D<0>_CORE to D_CORE<0> to avoid SKILL syntax errors.
        
        Args:
            label: Original net label (e.g., "D<0>_CORE", "SEL<0>_CORE")
            
        Returns:
            Formatted net label (e.g., "D_CORE<0>", "SEL_CORE<0>")
        """
        # Check if label contains < > pattern like D<0>_CORE
        # Pattern: word<characters>_suffix -> word_suffix<characters>
        pattern = r'(\w+)<([^>]+)>_(\w+)'
        match = re.match(pattern, label)
        if match:
            prefix = match.group(1)  # e.g., "D"
            index = match.group(2)   # e.g., "0"
            suffix = match.group(3)   # e.g., "CORE"
            return f"{prefix}_{suffix}<{index}>"  # e.g., "D_CORE<0>"
        # If pattern doesn't match, return as is (may already be in correct format or no brackets)
        return label

    def _parse_position_for_order(self, position_desc: Any) -> Tuple[Optional[str], int, int]:
        if not isinstance(position_desc, str):
            return None, 10**9, 10**9

        if position_desc in {"top_left", "top_right", "bottom_left", "bottom_right"}:
            return None, 10**9, 10**9

        parts = position_desc.split("_")
        if len(parts) >= 2 and parts[0] in {"top", "right", "bottom", "left"} and parts[1].isdigit():
            side = parts[0]
            idx1 = int(parts[1])
            idx2 = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else -1
            return side, idx1, idx2

        return None, 10**9, 10**9

    def _is_schematic_consumable_instance(self, inst: dict) -> bool:
        inst_type = str(inst.get("type", "")).strip().lower()
        if inst_type in {"pad"}:
            return True
        if inst_type in {"", "instance"}:
            return True
        return False

    def _sort_instances_for_schematic(self, instances: list, placement_order: str) -> list:
        """Sort instances for schematic and re-index positions to be compact.

        Only actual pads are counted for position indexing.
        Fillers and blanks are excluded from schematic generation.
        This ensures devices are placed with proper spacing.
        """
        side_order = ["top", "right", "bottom", "left"]
        if str(placement_order).lower() != "clockwise":
            side_order = ["left", "bottom", "right", "top"]

        side_items_map = {side: [] for side in ("left", "bottom", "right", "top")}
        unsorted_items = []

        for index, inst in enumerate(instances):
            side, idx1, idx2 = self._parse_position_for_order(inst.get("position"))
            if side in side_items_map:
                side_items_map[side].append((idx1, idx2, index, inst))
            else:
                unsorted_items.append((index, inst))

        # Rebuild with compact indexing - only count pads (not fillers/blanks)
        rebuilt_by_side = {side: [] for side in side_items_map}
        for side, items in side_items_map.items():
            # Keep side order from original numeric position
            items.sort(key=lambda item: (item[0], item[2], item[1]))

            outer_count = 0
            for _, _, _, inst in items:
                inst_out = inst.copy()
                inst_out["position"] = f"{side}_{outer_count}"
                outer_count += 1

                rebuilt_by_side[side].append(inst_out)

        ordered_instances = []
        for side in side_order:
            ordered_instances.extend(rebuilt_by_side[side])

        # Keep non-side items at the tail in their original relative order
        if unsorted_items:
            unsorted_items.sort(key=lambda item: item[0])
            ordered_instances.extend([item[1] for item in unsorted_items])

        return ordered_instances
    
    def get_device_offset(self, device_type: str) -> float:
        """Get offset based on device type and orientation (180nm process node)
        
        Note: For 180nm, device offset is not needed, always returns 0.
        """
        # 180nm does not require device offset
        return 0.0
    
    def normalize_device_config(self, config: dict) -> dict:
        """Standardize device configuration, handle field compatibility"""
        if 'position' not in config:
            return config

        # Normalize direction value to lowercase for robust matching
        if 'direction' in config and isinstance(config['direction'], str):
            config['direction'] = config['direction'].strip().lower()

        position_desc = config['position']

        # If user didn't specify device, need to provide base type
        if 'device' not in config:
            raise ValueError("device must be specified")
        
        base_device = config['device']
        
        # Corner points don't need suffix added
        if config.get('type') == 'corner':
            # Corner points keep original device, don't add suffix
            if 'orientation' not in config:
                # Set orientation based on corner position
                if position_desc == 'top_left':
                    config['orientation'] = 'R0'
                elif position_desc == 'top_right':
                    config['orientation'] = 'R90'
                elif position_desc == 'bottom_right':
                    config['orientation'] = 'R180'
                elif position_desc == 'bottom_left':
                    config['orientation'] = 'R270'
            return config
        
        # For 180nm, devices don't have _H_G or _V_G suffix
        # Just set orientation based on position, keep device name as is
        # Orientation mapping for 180nm (different from 28nm):
        # left -> R180, right -> R0, top -> R90, bottom -> R270
        if 'orientation' not in config:
            # Determine orientation based on position description
            if '_' in position_desc:
                side = position_desc.split('_')[0]
            else:
                side = 'left'  # Default value
            
            if side == 'left':
                config['orientation'] = 'R180'
            elif side == 'right':
                config['orientation'] = 'R0'
            elif side == 'top':
                config['orientation'] = 'R90'
            elif side == 'bottom':
                config['orientation'] = 'R270'
            else:
                config['orientation'] = 'R0'  # Default
        
        return config
    
    def calculate_position_from_description(self, position_desc, ring_config=None, device=None, orientation=None, clockwise=False):
        """Convert position description to specific coordinates"""
        if isinstance(position_desc, tuple):
            # If already a coordinate tuple, return directly
            return position_desc

        if not ring_config:
            # Default configuration
            ring_config = {
                'width': 12,
                'height': 12
            }
        # Parse position description
        if '_' in position_desc:
            parts = position_desc.split('_')
            if len(parts) == 2:
                # Pad format: left_0, bottom_1, etc.
                side, index_str = parts
                index = int(index_str)
            else:
                raise ValueError(f"Cannot parse position description: {position_desc}")
        else:
            # If not a relative position description, try to parse as coordinates
            try:
                # Try to parse as "x,y" format
                if ',' in position_desc:
                    x, y = position_desc.split(',')
                    return (float(x), float(y))
                else:
                    raise ValueError(f"Cannot parse position description: {position_desc}")
            except:
                raise ValueError(f"Cannot parse position description: {position_desc}")
        
        # Calculate ring parameters based on scale configuration
        # Support both top_count/bottom_count/left_count/right_count and width/height formats
        if 'top_count' in ring_config or 'bottom_count' in ring_config:
            top_count = ring_config.get('top_count', 12)
            bottom_count = ring_config.get('bottom_count', 12)
            left_count = ring_config.get('left_count', 12)
            right_count = ring_config.get('right_count', 12)
            width_pads = max(top_count, bottom_count)   # Pads along top/bottom
            height_pads = max(left_count, right_count)  # Pads along left/right
        else:
            width_pads = ring_config.get('width', 12)   # Number of pads on top and bottom sides
            height_pads = ring_config.get('height', 12) # Number of pads on left and right sides
        
        # Calculate spacing and dimensions
        spacing = 2.0  # Default spacing
        corner_spacing = 3.0  # Corner spacing
        
        # Calculate ring dimensions (considering corner spacing)
        width = (width_pads - 1) * spacing + 2 * corner_spacing
        height = (height_pads - 1) * spacing + 2 * corner_spacing
        
        # Calculate base position based on side and index
        if side == 'left':
            if clockwise:
                # Clockwise: left side from bottom to top, index 0 is bottommost
                x = 0
                y = corner_spacing + index * spacing
            else:
                # Counterclockwise: left side from top to bottom, index 0 is topmost
                x = 0
                y = height - corner_spacing - index * spacing
        elif side == 'bottom':
            if clockwise:
                # Clockwise: bottom side from right to left, index 0 is rightmost
                x = width - corner_spacing - index * spacing
                y = 0
            else:
                # Counterclockwise: bottom side from left to right, index 0 is leftmost
                x = corner_spacing + index * spacing
                y = 0
        elif side == 'right':
            if clockwise:
                # Clockwise: right side from top to bottom, index 0 is topmost
                x = width
                y = height - corner_spacing - index * spacing
            else:
                # Counterclockwise: right side from bottom to top, index 0 is bottommost
                x = width
                y = corner_spacing + index * spacing
        elif side == 'top':
            if clockwise:
                # Clockwise: top side from left to right, index 0 is leftmost
                x = corner_spacing + index * spacing
                y = height
            else:
                # Counterclockwise: top side from right to left, index 0 is rightmost
                x = width - corner_spacing - index * spacing
                y = height
        else:
            raise ValueError(f"Unknown side description: {side}")
        
        # For 180nm, device offset is not applied
        return (x, y)
    
    def rotate_point(self, x, y, orientation):
        """Rotate coordinate point"""
        if orientation == 'R0':
            return x, y
        elif orientation == 'R90':
            return -y, x
        elif orientation == 'R180':
            return -x, -y
        elif orientation == 'R270':
            return y, -x
        else:
            return x, y
    
    def get_pin_side_from_center(self, pin_x, pin_y, center_x, center_y, orientation):
        """Determine pin position based on rotation direction (180nm specific logic)"""
        # For 180nm, orientation mapping is different:
        # left->R180, right->R0, top->R90, bottom->R270
        # So the judgment logic is reversed compared to 28nm
        if orientation in ['R270', 'R90']:
            # Only judge up and down direction
            return 'top' if pin_y > center_y else 'bottom'
        elif orientation in ['R0', 'R180']:
            # Only judge left and right direction
            return 'right' if pin_x > center_x else 'left'
        else:
            # Compatible with other cases, default to original logic
            delta_x = pin_x - center_x
            delta_y = pin_y - center_y
            if abs(delta_x) > abs(delta_y):
                return 'right' if delta_x > 0 else 'left'
            else:
                return 'top' if delta_y > 0 else 'bottom'
    
    def generate_pin_commands(self, pin_name, label_text, pin_x, pin_y, side,
                             create_wire=True, create_label=True, create_pin=True):
        """Generate pin-related SKILL commands"""
        # Do not sanitize pin_name - keep original pin name format (e.g., SEL_CORE<0>)
        # pin_name = self.sanitize_skill_instance_name(pin_name)
        # Format label_text for SKILL net label compatibility (convert D<0>_CORE to D_CORE<0>)
        label_text = self.format_skill_net_label(label_text)
        
        side_pin_style = {
            'right': {
                'extend_x': 0.750, 'extend_y': 0.0,
                'label_offset_x': 0.25, 'label_offset_y': 0.0,
                'label_align': 'lowerLeft', 'label_rotation': 'R0',
                'pin_orientation': 'R180'
            },
            'left': {
                'extend_x': -0.750, 'extend_y': 0.0,
                'label_offset_x': -0.25, 'label_offset_y': 0.0,
                'label_align': 'lowerRight', 'label_rotation': 'R0',
                'pin_orientation': 'R0'
            },
            'top': {
                'extend_x': 0.0, 'extend_y': 0.750,
                'label_offset_x': 0.0, 'label_offset_y': 0.25,
                'label_align': 'lowerLeft', 'label_rotation': 'R90',
                'pin_orientation': 'R270'
            },
            'bottom': {
                'extend_x': 0.0, 'extend_y': -0.750,
                'label_offset_x': 0.0, 'label_offset_y': -0.25,
                'label_align': 'lowerRight', 'label_rotation': 'R90',
                'pin_orientation': 'R90'
            }
        }
        
        config = side_pin_style[side]
        end_x = pin_x + config['extend_x']
        end_y = pin_y + config['extend_y']
        label_x = pin_x + config['label_offset_x']
        label_y = pin_y + config['label_offset_y']
        
        commands = []
        if create_wire:
            commands.append(f'schCreateWire(cv "route" "full" \'(({pin_x:.3f} {pin_y:.3f}) ({end_x:.3f} {end_y:.3f})) 0 0 0 nil nil)')
        if create_label:
            commands.append(f'schCreateWireLabel(cv nil \'({label_x:.3f} {label_y:.3f}) "{label_text}" "{config["label_align"]}" "{config["label_rotation"]}" "stick" 0.0625 nil)')
        if create_pin:
            commands.append(f'schCreatePin(cv nil "{pin_name}" "inputOutput" nil \'({end_x:.3f} {end_y:.3f}) "{config["pin_orientation"]}")')
        
        return commands
    
    def get_default_pin_connection(self, device, pin_name, pad_name, direction='input'):
        """Get default pin connection configuration"""
        return self.template_manager.get_pin_connection(device, pin_name, pad_name, direction)
    
    def get_noconn_orientation(self, device_orientation):
        """Get corresponding orientation for noConn component"""
        orientation_map = {
            'R0': 'R270',
            'R90': 'R0', 
            'R180': 'R90',
            'R270': 'R180'
        }
        return orientation_map.get(device_orientation, 'R0')
    
    def generate_noconn_commands(self, pin_x, pin_y, orientation):
        """Generate SKILL commands for noConn component"""
        commands = []
        # Load noConn component (if not loaded yet)
        commands.append('noConnMaster = dbOpenCellView("basic" "noConn" "symbol")')
        # Create noConn instance
        commands.append(f'dbCreateInst(cv noConnMaster "noConn_{pin_x:.3f}_{pin_y:.3f}" \'({pin_x:.3f} {pin_y:.3f}) "{orientation}")')
        return commands
    
    def generate_schematic(self, config_list, output_file="generated_schematic.il", clockwise=False):
        """Generate schematic SKILL code - handle unified configuration list"""
        
        # Ensure output directory exists
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        
        # If output file path is not absolute and not in output directory, save to output directory
        output_path = Path(output_file)
        if not output_path.is_absolute() and "output" not in output_path.parts:
            output_file = output_dir / output_file
        
        # Separate ring configuration and instance configuration
        ring_config = None
        instances = []
        
        for item in config_list:
            if item.get('type') == 'ring_config':
                ring_config = item
            elif item.get('type') == 'instance':
                # Keep original type field, don't override
                instances.append(item)
            else:
                # Compatible with old format: if no type field, assume it's an instance
                if 'type' not in item:
                    item['type'] = 'instance'
                instances.append(item)
        
        # If no ring configuration found, use default configuration
        if not ring_config:
            ring_config = {
                'left_pads': 12,
                'bottom_pads': 12,
                'right_pads': 12,
                'top_pads': 12
            }
        
        # Read placement_order parameter from ring_config, if not available use clockwise parameter default value
        placement_order = ring_config.get('placement_order', 'counterclockwise')
        clockwise = (placement_order == 'clockwise')
        
        # Standardize all device configurations
        normalized_instances = []
        for inst in instances:
            normalized_inst = self.normalize_device_config(inst.copy())
            normalized_instances.append(normalized_inst)

        schematic_instances = [
            inst for inst in normalized_instances if self._is_schematic_consumable_instance(inst)
        ]
        schematic_instances = self._sort_instances_for_schematic(
            schematic_instances,
            placement_order,
        )

        commands = []
        commands.append("cv = geGetEditCellView()")
        
        loaded_devices = set()
        noConn_loaded = False  # Mark whether noConn component has been loaded
        
        for inst in schematic_instances:
                
            device = inst['device']
            template = self.template_manager.get_template(device)
            
            if not template:
                print(f"[WARN]  Warning: Template not found for device type {device}, skipping {inst['name']}")
                continue
            
            # Load device library (if not loaded yet)
            if device not in loaded_devices:
                commands.append(f'{device.lower()}Master = dbOpenCellView("{template.device_lib}" "{template.device_cell}" "{template.device_view}")')
                loaded_devices.add(device)
            
            # Calculate position coordinates
            position_desc = inst['position']
            x_pos, y_pos = self.calculate_position_from_description(
                position_desc, ring_config, device, inst['orientation'], clockwise
            )
            orientation = inst['orientation']

            # Create device instance
            # Combine name and position to ensure instance name uniqueness
            if isinstance(position_desc, tuple):
                # If it's a coordinate tuple, use coordinate values
                instance_name = f"{inst['name']}_{position_desc[0]}_{position_desc[1]}"
            else:
                # Normal format: left_0 -> left0
                instance_name = f"{inst['name']}_{position_desc.replace('_', '')}"
            # Sanitize instance name for SKILL compatibility (replace < > with _)
            instance_name = self.sanitize_skill_instance_name(instance_name)
            commands.append(f'dbCreateInst(cv {device.lower()}Master "{instance_name}" \'({x_pos} {y_pos}) "{orientation}")')
            
            # Calculate rotated center point
            rotated_center_x, rotated_center_y = self.rotate_point(template.center_x, template.center_y, orientation)
            final_center_x = x_pos + rotated_center_x
            final_center_y = y_pos + rotated_center_y
            
            # Generate pin connections
            # First collect main power/ground labels
            pin_connection_dict = inst.get('pin_connection', {})
            vdd_label = pin_connection_dict.get('VDD', {}).get('label')
            vss_label = pin_connection_dict.get('VSS', {}).get('label')
            vddpst_label = pin_connection_dict.get('VDDPST', {}).get('label')
            vsspst_label = pin_connection_dict.get('VSSPST', {}).get('label')

            for pin in template.pins:
                rotated_pin_x, rotated_pin_y = self.rotate_point(pin['x'], pin['y'], orientation)
                final_pin_x = x_pos + rotated_pin_x
                final_pin_y = y_pos + rotated_pin_y
                side = self.get_pin_side_from_center(final_pin_x, final_pin_y, final_center_x, final_center_y, orientation)
                
                # Get default configuration, pass main power/ground labels
                direction = inst.get('direction', 'input')  # Default to input IO
                pin_cfg = pin_connection_dict.get(pin['name'], {})
                pin_label = pin_cfg.get('label')
                default_config = self.template_manager.get_pin_connection(
                    device, pin['name'], inst['name'], direction,
                    pin_label=pin_label,
                    vdd_label=vdd_label,
                    vss_label=vss_label,
                    vddpst_label=vddpst_label,
                    vsspst_label=vsspst_label
                )
                
                # Mixed configuration: user-provided configuration takes priority, use default configuration for unspecified ones
                label = pin_label if pin_label is not None else default_config['label']
                # Format label for SKILL net label compatibility (convert D<0>_CORE to D_CORE<0>)
                # Note: label formatting is done in generate_pin_commands, but we also format here for consistency
                label = self.format_skill_net_label(label)
                create_wire = pin_cfg.get('create_wire', default_config['create_wire'])
                create_label = pin_cfg.get('create_label', default_config['create_label'])
                create_pin = pin_cfg.get('create_pin', default_config['create_pin'])
                
                if not (create_wire or create_label or create_pin):
                    continue
                
                # Check if it's a digital IO device and label is noConn
                if (device in ['PDDW0412SCDG'] and 
                    label == 'noConn'):
                    # Create noConn component
                    if not noConn_loaded:
                        commands.append('noConnMaster = dbOpenCellView("basic" "noConn" "symbol")')
                        noConn_loaded = True
                    # Get noConn orientation
                    noConn_orientation = self.get_noconn_orientation(orientation)
                    # Calculate wire end position
                    side_pin_style = {
                        'right': {'extend_x': 0.750, 'extend_y': 0.0},
                        'left': {'extend_x': -0.750, 'extend_y': 0.0},
                        'top': {'extend_x': 0.0, 'extend_y': 0.750},
                        'bottom': {'extend_x': 0.0, 'extend_y': -0.750}
                    }
                    config = side_pin_style[side]
                    end_x = final_pin_x + config['extend_x']
                    end_y = final_pin_y + config['extend_y']
                    # Generate wire command (don't generate label and pin)
                    pin_cmds = self.generate_pin_commands(label, label, final_pin_x, final_pin_y, side,
                                                         create_wire=True, create_label=False, create_pin=False)
                    commands.extend(pin_cmds)
                    # Place noConn component at wire end
                    commands.append(f'dbCreateInst(cv noConnMaster "noConn_{instance_name}_{pin["name"]}" ' +
                                     f'\'({end_x:.3f} {end_y:.3f}) "{noConn_orientation}")')
                    continue  # Skip normal pin generation
                
                pin_cmds = self.generate_pin_commands(label, label, final_pin_x, final_pin_y, side,
                                                     create_wire, create_label, create_pin)
                commands.extend(pin_cmds)
        commands.append('schCheck(cv)')
        commands.append('dbSave(cv)')
        commands.append('t')  # End command
        
        # Write to file
        with open(output_file, 'w') as f:
            for cmd in commands:
                f.write(cmd + '\n')
        
        print(f"[OK] Successfully generated schematic file: {output_file}")
        print(f"[STATS] Statistics:")
        print(f"  - Device instance count: {len(schematic_instances)}")
        print(f"  - Device types used: {', '.join(loaded_devices)}")
        print(f"  - SKILL command count: {len(commands)}")
        
        return commands

def load_templates_from_json(json_file=None):
    """Load device templates from JSON file for 180nm process node
    
    Args:
        json_file: Optional specific JSON file path. If None, will search for 180nm template files
    """
    # If json_file is provided, use it directly
    if json_file:
        possible_files = [
            json_file,  # Original filename
            os.path.join("src", "schematic", json_file),  # src/schematic directory
            os.path.join("src", "scripts", "devices", json_file),  # src/scripts/devices directory
        ]
    else:
        # Search for 180nm template files
        possible_files = [
            "device_templates_180.json",
            os.path.join("src", "app", "schematic", "device_templates_180.json"),
            os.path.join("src", "schematic", "device_templates_180.json"),
            os.path.join("src", "scripts", "devices", "device_templates_180.json"),
            "IO_device_info_T180.json",
            os.path.join("src", "app", "schematic", "IO_device_info_T180.json"),
            os.path.join("src", "schematic", "IO_device_info_T180.json"),
            os.path.join("src", "scripts", "devices", "IO_device_info_T180.json"),
        ]
    
    json_file = None
    for file_path in possible_files:
        if os.path.exists(file_path):
            json_file = file_path
            break
    
    if json_file is None:
        raise FileNotFoundError(
            f"Device template file not found for 180nm process node. Tried: {', '.join(possible_files)}"
        )
    
    template_manager = DeviceTemplateManager()
    template_manager.load_templates_from_json(json_file)
    return template_manager

def generate_multi_device_schematic(config_list, output_file="multi_device_schematic.il", voltage_config=None, clockwise=False):
    """Main function for generating multi-device schematic for 180nm process node - supports unified configuration list and old format
    
    Args:
        config_list: Configuration list (unified format or old format)
        output_file: Output file path
        voltage_config: Voltage configuration (deprecated, kept for compatibility)
        clockwise: Whether to place devices clockwise
    """
    
    # Ensure output directory exists
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    
    # If output file path is not absolute and not in output directory, save to output directory
    output_path = Path(output_file)
    if not output_path.is_absolute() and "output" not in output_path.parts:
        output_file = output_dir / output_file
    
    # Load device templates for 180nm
    template_manager = load_templates_from_json()
    
    # Create generator and generate schematic
    generator = SchematicGenerator(template_manager)
    
    # Check if it's old format (instances list)
    if config_list and isinstance(config_list[0], dict) and 'device' in config_list[0]:
        # Old format: directly pass instances list
        return generator.generate_schematic(config_list, output_file, clockwise)
    else:
        # New format: unified configuration list
        # Extract ring_config from configuration to get clockwise parameter
        ring_config = None
        for item in config_list:
            if item.get('type') == 'ring_config':
                ring_config = item
                break
        
        # If ring_config is found, read clockwise parameter from it
        if ring_config and 'clockwise' in ring_config:
            clockwise = ring_config['clockwise']
        
        return generator.generate_schematic(config_list, output_file, clockwise)
