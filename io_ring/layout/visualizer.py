#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Layout Visualizer for T180 - Generate visual diagram from SKILL layout code
Converts SKILL dbCreateParamInstByMasterName calls to visual representation
Optimized for T180 process node with different device sizes and types
"""

import re
import json
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from collections import defaultdict

# Get config directory path
# layout_visualizer.py is in src/app/layout/T180/
# config files are in src/app/layout/config/
_CONFIG_DIR = Path(__file__).parent / "config"

def _load_180nm_config() -> Dict:
    """Load 180nm device configuration from JSON file"""
    config_file = _CONFIG_DIR / "lydevices_180.json"
    if config_file.exists():
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

# Load 180nm configuration
_180NM_CONFIG = _load_180nm_config()

# Device type color mapping for 180nm
# Color scheme:
# - Blue shades: Analog IO and power/ground
# - Green shades: Digital IO and power/ground
DEVICE_COLORS_180NM = {
    # Pad devices (not drawn, but included for completeness)
    'PAD70LU_TRL': '#FFD700',  # Gold
    
    # Digital IO devices (Green shades)
    'PVDD1CDG': '#32CD32',  # Medium green - Digital power (VDD)
    'PVSS1CDG': '#228B22',  # Dark green - Digital ground (VSS)
    'PVDD2CDG': '#90EE90',  # Light green - Digital power (VDD)
    'PVSS2CDG': '#228B22',  # Dark green - Digital ground (VSS)
    'PDDW0412SCDG': '#32CD32',  # Medium green - Digital IO

    # Analog IO devices (Blue shades)
    'PVDD1ANA': '#4A90E2',  # Medium blue - Analog power (VDD)
    'PVSS1ANA': '#3A80D2',  # Dark blue - Analog ground (VSS)
    'PVDD2ANA': '#5BA0F2',  # Light blue - Analog power (VDD)
    'PVSS2ANA': '#3A80D2',  # Dark blue - Analog ground (VSS)
    
    # Corner devices (Red shades)
    'PCORNER': '#FF6B6B',  # Medium red - Corner
    
    # Filler devices (Light gray)
    'PFILLER10': '#C0C0C0',  # Light gray - Filler 10
    'PFILLER20': '#C0C0C0',  # Light gray - Filler 20
    
    # Blank (for domain mismatch)
    'blank': '#FF0000',  # Red - Blank space
    
    # Default
    'default': '#CCCCCC',  # Light gray
}

# Device dimensions for 180nm (in SKILL units)
# Load from config if available, otherwise use defaults from process_node_config
_layout_params = _180NM_CONFIG.get("layout_params", {})
if not _layout_params:
    # Fallback to process_node_config defaults
    try:
        from .process_config import get_process_node_config
        _180nm_base_config = get_process_node_config()
        _layout_params = {
            "pad_width": _180nm_base_config.get("pad_width", 80),
            "pad_height": _180nm_base_config.get("pad_height", 120),
            "corner_size": _180nm_base_config.get("corner_size", 130),
        }
    except ImportError:
        _layout_params = {}

PAD_WIDTH_180NM = _layout_params.get("pad_width", 80)
PAD_HEIGHT_180NM = _layout_params.get("pad_height", 120)
CORNER_SIZE_180NM = _layout_params.get("corner_size", 130)
FILLER_WIDTH_180NM = 80  # Filler width: 80×120 (same as IO devices)
FILLER_HEIGHT_180NM = 120  # Filler height: 80×120
FILLER10_WIDTH_180NM = 10  # 10×120 filler
FILLER10_HEIGHT_180NM = 120


def parse_skill_layout_180nm(il_file_path: str) -> List[Dict]:
    """
    Parse SKILL layout file and extract device information for 180nm
    
    Returns list of device dictionaries with:
    - inst_name: instance name
    - cell_name: cell/master name
    - lib_name: library name
    - x, y: position coordinates
    - rotation: orientation (R0, R90, R180, R270)
    - device_type: device type for color mapping
    - device_category: category (io, corner, filler)
    """
    with open(il_file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Pattern to match dbCreateParamInstByMasterName calls
    pattern = r'dbCreateParamInstByMasterName\s*\(\s*cv\s+"([^"]+)"\s+"([^"]+)"\s+"([^"]+)"\s+"([^"]+)"\s+list\s*\(\s*([-\d.]+)\s+([-\d.]+)\s*\)\s+"([^"]+)"\s*\)'
    
    devices = []
    matches = re.findall(pattern, content)
    
    for match in matches:
        lib_name, cell_name, view_name, inst_name, x_str, y_str, rotation = match
        
        # Extract device type from cell name
        # Skip PAD70LU_TRL (physical pad, not to be drawn for 180nm)
        if cell_name == 'PAD70LU_TRL' or cell_name.startswith('PAD70'):
            # Skip physical pad devices
            continue
        
        device_type = cell_name
        device_category = 'io'  # Default category for IO devices
        
        # Use configuration file to classify devices
        digital_devices = _180NM_CONFIG.get("digital_devices", [])
        analog_devices = _180NM_CONFIG.get("analog_devices", [])
        corner_devices = _180NM_CONFIG.get("corner_devices", [])
        filler_devices = _180NM_CONFIG.get("filler_devices", [])
        cut_devices = _180NM_CONFIG.get("cut_devices", [])
        
        # Check device type using config
        if any(dev in cell_name for dev in corner_devices):
            device_type = cell_name
            device_category = 'corner'
        elif any(dev in cell_name for dev in filler_devices) or any(dev in cell_name for dev in cut_devices):
            device_type = cell_name
            device_category = 'filler'
        elif any(dev in cell_name for dev in digital_devices) or any(dev in cell_name for dev in analog_devices):
            device_type = cell_name
            device_category = 'io'  # IO device category
        elif 'CORNER' in cell_name or 'PCORNER' in cell_name:
            # Fallback for corner devices
            device_type = 'PCORNER'
            device_category = 'corner'
        elif 'FILLER' in cell_name:
            # Fallback for filler devices
            device_type = cell_name  # PFILLER10, PFILLER20
            device_category = 'filler'
        elif 'RCUT' in cell_name:
            # Fallback for separator
            device_type = cell_name
            device_category = 'filler'  # Separator is also a filler type
        elif 'PVDD' in cell_name or 'PVSS' in cell_name or 'PDDW' in cell_name:
            # Fallback for power/ground/IO devices
            device_type = cell_name
            device_category = 'io'
        
        devices.append({
            'inst_name': inst_name,
            'cell_name': cell_name,
            'lib_name': lib_name,
            'x': float(x_str),
            'y': float(y_str),
            'rotation': rotation,
            'device_type': device_type,
            'device_category': device_category
        })
    
    return devices


def get_device_color_180nm(device_type: str) -> str:
    """Get color for device type based on 180nm configuration"""
    # Use configuration file for device classification
    digital_io = _180NM_CONFIG.get("digital_io", [])
    digital_vol = _180NM_CONFIG.get("digital_vol", [])
    analog_io = _180NM_CONFIG.get("analog_io", [])
    analog_vol = _180NM_CONFIG.get("analog_vol", [])
    corner_devices = _180NM_CONFIG.get("corner_devices", [])
    filler_devices = _180NM_CONFIG.get("filler_devices", [])
    
    # Check if device matches any in config lists
    if any(dev in device_type for dev in digital_io):
        return '#32CD32'  # Medium green - Digital IO
    elif any(dev in device_type for dev in digital_vol):
        if 'PVDD' in device_type:
            return '#90EE90'  # Light green - Digital power
        else:
            return '#228B22'  # Dark green - Digital ground
    elif any(dev in device_type for dev in analog_io):
        return '#4A90E2'  # Medium blue - Analog IO
    elif any(dev in device_type for dev in analog_vol):
        if 'PVDD' in device_type:
            return '#5BA0F2'  # Light blue - Analog power
        else:
            return '#3A80D2'  # Dark blue - Analog ground
    elif any(dev in device_type for dev in corner_devices):
        return '#FF6B6B'  # Medium red - Corner
    elif any(dev in device_type for dev in filler_devices):
        return '#C0C0C0'  # Light gray - Filler
    
    # Try prefix match
    for key, color in DEVICE_COLORS_180NM.items():
        if key != 'default' and device_type.startswith(key):
            return color
    
    return DEVICE_COLORS_180NM['default']


def get_rectangle_for_rotation_180nm(x: float, y: float, rotation: str, width: float, height: float) -> Tuple[float, float, float, float]:
    """
    Calculate rectangle coordinates based on rotation for 180nm
    Returns (x, y, width, height) for matplotlib Rectangle (bottom-left corner)
    
    All rectangles use R0 state's bottom-left corner as origin.
    In SKILL, the coordinate (x, y) needs to be converted to R0 state's bottom-left corner.
    
    For 180nm:
    - R0: horizontal, bottom-left at (x, y), width=80, height=120
    - R90: vertical up, SKILL coord (x,y) -> R0 bottom-left at (x-height, y), width=120, height=80
    - R180: horizontal left, SKILL coord (x,y) -> R0 bottom-left at (x-width, y-height), width=80, height=120
    - R270: vertical down, SKILL coord (x,y) -> R0 bottom-left at (x, y-height), width=120, height=80
    """
    is_square = (abs(width - height) < 0.1)  # Check if device is square (corner)
    
    if is_square:
        # Square device (corner): (x, y) is a specific corner position based on rotation
        # Need to convert to R0 state's bottom-left corner
        # Corner positions in SKILL:
        # - BL (bottom-left): (x, y) is bottom-left corner -> R0 bottom-left at (x, y)
        # - BR (bottom-right): (x, y) is bottom-right corner -> R0 bottom-left at (x - width, y)
        # - TL (top-left): (x, y) is top-left corner -> R0 bottom-left at (x, y - height)
        # - TR (top-right): (x, y) is top-right corner -> R0 bottom-left at (x - width, y - height)
        if rotation == 'R0':
            # BL corner: (x, y) is bottom-left
            return (x, y, width, height)
        elif rotation == 'R90':
            # BR corner: (x, y) is bottom-right, R0 bottom-left at (x - width, y)
            return (x - width, y, width, height)
        elif rotation == 'R180':
            # TR corner: (x, y) is top-right, R0 bottom-left at (x - width, y - height)
            return (x - width, y - height, width, height)
        elif rotation == 'R270':
            # TL corner: SKILL coord (x, y) is at top-left position
            # R0 bottom-left at (x, y - height)
            return (x, y - height, width, height)
        else:
            return (x, y, width, height)
    else:
        # Rectangular device (IO, filler): convert SKILL coord to R0 bottom-left
        # SKILL coordinate system: x increases RIGHT, y increases UP
        if rotation == 'R0':
            # R0: SKILL coord (x, y) is at bottom edge (y is minimum)
            # Rectangle: horizontal, 80 wide x 120 high
            # R0 bottom-left at (x, y)
            return (x, y, width, height)
        elif rotation == 'R90':
            # R90: SKILL coord (x, y) is at right edge (x is maximum)
            # Rectangle: vertical, 120 wide x 80 high (rotated)
            # R0 bottom-left at (x - height, y)
            return (x - height, y, height, width)  # Swap dimensions
        elif rotation == 'R180':
            # R180: SKILL coord (x, y) is at top edge (y is maximum)
            # Rectangle: horizontal, 80 wide x 120 high (flipped)
            # R0 bottom-left at (x - width, y - height)
            return (x - width, y - height, width, height)
        elif rotation == 'R270':
            # R270: SKILL coord (x, y) is at left edge center
            # Rotated rectangle: vertical, 120 wide x 80 high
            # In R0 state: 80 wide x 120 high, horizontal
            # For 180nm: pad_width=80, pad_height=120, corner_size=130
            # R0 bottom-left calculation for R270:
            # Based on 180nm layout analysis:
            # - Corner at (0, 0) R0 has top at y = 130
            # - First pad at (0, 220) R270 should have bottom at y = 130 in R0
            # - First filler at (0, 140) R270 should have bottom at y = 130 in R0
            # The coordinate (x, y) in R270 represents the left edge center
            # In R0, device is horizontal, so bottom-left y = y - height/2 + offset
            # For 80×120 pad: 130 = 220 - 60 + offset -> offset = -30
            # For 10×120 filler: 130 = 140 - 60 + offset -> offset = 50
            # But this doesn't match pattern. Let's use a different approach:
            # The offset should account for the difference between R270 center and R0 bottom
            # For 180nm, based on actual coordinates:
            # - (0, 220) R270 -> bottom at 130 in R0, so y_bl = 130
            # - Formula: y_bl = y - height/2 - (y - corner_top - height/2)
            # - Simplified: y_bl = corner_top = 130 (for first device after corner)
            # But this only works for first device. For general case:
            # - The spacing between devices in R270 is 90 (pad_spacing)
            # - So: y_bl = y - height/2 - (y - first_y + height/2 - corner_top)
            # Actually, let's use a simpler empirical formula:
            # For 80×120: y_bl = y - height/2 - 30
            # For 10×120: y_bl = y - height/2 + 50
            if abs(width - 10) < 0.1:  # Check if this is a 10×120 filler
                # For 10×120 filler: (0, 140) R270 -> bottom at 130 in R0
                # y_bl = 140 - 60 + offset = 130 -> offset = 50
                # Filler position is correct, keep original offset
                offset = 50
            else:
                # For 80×120 devices (pads): (0, 220) R270 -> bottom at 130 in R0
                # y_bl = 220 - 60 + offset = 130 -> offset = -30
                # Adjusted: move pad up by 10, so offset = -30 + 10 = -20
                offset = -20
            return (x, y - height/2 + offset, height, width)  # Swap dimensions
        else:
            # Default to R0
            return (x, y, width, height)


def visualize_layout_T180(il_file_path: str, output_path: Optional[str] = None) -> str:
    """
    Generate visual diagram from SKILL layout file for T180
    
    Args:
        il_file_path: Path to SKILL layout file
        output_path: Optional output path for image (default: same directory as input with .png extension)
    
    Returns:
        Path to generated image file
    """
    # Parse SKILL file
    devices = parse_skill_layout_180nm(il_file_path)
    
    if not devices:
        raise ValueError(f"No devices found in {il_file_path}")
    
    # Include all devices: pads, corners, and fillers
    all_devices = devices
    
    # Calculate bounds from all devices
    all_x = [d['x'] for d in all_devices]
    all_y = [d['y'] for d in all_devices]
    min_x, max_x = min(all_x), max(all_x)
    min_y, max_y = min(all_y), max(all_y)
    
    # Add padding for visualization
    padding = 50
    fig_width = max(max_x - min_x + 2 * padding, 400)
    fig_height = max(max_y - min_y + 2 * padding, 400)
    
    # Create figure
    fig, ax = plt.subplots(1, 1, figsize=(fig_width/50, fig_height/50))
    ax.set_xlim(min_x - padding, max_x + padding)
    ax.set_ylim(min_y - padding, max_y + padding)
    ax.set_aspect('equal')
    # SKILL coordinates: x increases RIGHT, y increases UP (no inversion needed)
    ax.axis('off')
    
    # Sort pad devices by position to ensure proper ordering
    # Sort by side first (left, bottom, right, top), then by position along that side
    def get_sort_key(device):
        x, y = device['x'], device['y']
        rotation = device['rotation']
        # Determine which side based on rotation and position
        if rotation == 'R270':  # Left side
            return (0, y)  # Sort by y coordinate
        elif rotation == 'R0':  # Bottom side
            return (1, x)  # Sort by x coordinate
        elif rotation == 'R90':  # Right side
            return (2, -y)  # Sort by y coordinate (descending)
        elif rotation == 'R180':  # Top side
            return (3, -x)  # Sort by x coordinate (descending)
        else:
            return (4, 0)
    
    all_devices_sorted = sorted(all_devices, key=get_sort_key)
    
    # Draw each device
    for device in all_devices_sorted:
        x, y = device['x'], device['y']
        rotation = device['rotation']
        device_type = device['device_type']
        device_category = device.get('device_category', 'io')
        inst_name = device['inst_name']
        
        # Get color
        color = get_device_color_180nm(device_type)
        
        # Get device dimensions based on category
        if device_category == 'corner':
            width = CORNER_SIZE_180NM
            height = CORNER_SIZE_180NM
        elif device_category == 'filler':
            # Filler size depends on type: PFILLER10 is 10×120, PFILLER20 is 20×120 (or 80×120)
            if 'PFILLER10' in device_type:
                width = FILLER10_WIDTH_180NM
                height = FILLER10_HEIGHT_180NM
            else:
                # PFILLER20 or default - for 180nm, fillers are typically 80×120
                width = FILLER_WIDTH_180NM
                height = FILLER_HEIGHT_180NM
        elif device_category == 'blank':
            # Blank: same size as filler10
            width = FILLER10_WIDTH_180NM
            height = FILLER10_HEIGHT_180NM
        else:  # io (IO devices)
            # IO devices: 80×120 for 180nm
            width = PAD_WIDTH_180NM
            height = PAD_HEIGHT_180NM
        
        # Calculate rectangle based on rotation
        rect_x, rect_y, rect_w, rect_h = get_rectangle_for_rotation_180nm(
            x, y, rotation, width, height
        )
        
        # Create rectangle with thicker border for better visibility
        if device_category == 'blank':
            # Blank: red color with dashed border
            rect = patches.Rectangle(
                (rect_x, rect_y), rect_w, rect_h,
                linewidth=2, edgecolor='black', facecolor='#FF0000', alpha=0.6,
                linestyle='--'  # Dashed border for blank
            )
        else:
            rect = patches.Rectangle(
                (rect_x, rect_y), rect_w, rect_h,
                linewidth=2, edgecolor='black', facecolor=color, alpha=0.8
            )
        ax.add_patch(rect)
        
        # Add text label in center
        if device_category == 'io':
            # Extract signal name from instance name
            signal_name = inst_name
            # Regular IO: remove _(left|right|top|bottom)_\d+$
            signal_name = re.sub(r'_(left|right|top|bottom)_\d+$', '', signal_name)
            
            # Get device type (cell_name)
            device_type_label = device['cell_name']
            
            # Format: "signal_name:device_type"
            label = f"{signal_name}:{device_type_label}"
        elif device_category == 'corner':
            label = device['cell_name']
        elif device_category == 'filler':
            label = device['cell_name']
        elif device_category == 'blank':
            label = 'Blank'
        else:
            label = inst_name
            label = re.sub(r'_(left|right|top|bottom)_\d+$', '', label)
        
        # Calculate center of rectangle
        center_x = rect_x + rect_w / 2
        center_y = rect_y + rect_h / 2
        
        # Adjust font size based on device size
        if device_category == 'corner':
            font_size = 8
        elif device_category == 'filler':
            font_size = 6
        elif device_category == 'blank':
            font_size = 6
        else:  # io (IO devices)
            font_size = 7
        
        # Determine text rotation to align with rectangle's long edge
        if rotation == 'R0' or rotation == 'R180':
            # Horizontal rectangle: long edge is vertical, text should be vertical
            text_rotation = 90
        elif rotation == 'R90' or rotation == 'R270':
            # Vertical rectangle: long edge is horizontal, text should be horizontal
            text_rotation = 0
        else:
            text_rotation = 0
        
        ax.text(center_x, center_y, label, 
                ha='center', va='center', 
                fontsize=font_size, 
                rotation=text_rotation,
                rotation_mode='anchor',
                weight='bold' if device_category == 'corner' else 'normal')
    
    ax.set_title('IO Ring Layout Visualization (T180)', fontsize=14, fontweight='bold', pad=20)
    
    # Add legend - separate digital and analog IO devices
    device_types_found = set(d['device_type'] for d in all_devices)
    
    # Categorize devices using config
    digital_io = _180NM_CONFIG.get("digital_io", [])
    analog_io = _180NM_CONFIG.get("analog_io", [])
    digital_vol = _180NM_CONFIG.get("digital_vol", [])
    analog_vol = _180NM_CONFIG.get("analog_vol", [])
    corner_devices = _180NM_CONFIG.get("corner_devices", [])
    filler_devices = _180NM_CONFIG.get("filler_devices", [])
    
    digital_io_types = []
    analog_io_types = []
    other_types = []
    
    for dev_type in sorted(device_types_found):
        # Check using config lists
        if any(dev in dev_type for dev in digital_io + digital_vol):
            digital_io_types.append(dev_type)
        elif any(dev in dev_type for dev in analog_io + analog_vol):
            analog_io_types.append(dev_type)
        elif any(dev in dev_type for dev in corner_devices + filler_devices):
            other_types.append(dev_type)
        else:
            # Fallback to pattern matching
            if 'CDG' in dev_type:
                digital_io_types.append(dev_type)
            elif 'ANA' in dev_type:
                analog_io_types.append(dev_type)
            else:
                other_types.append(dev_type)
    
    # Build legend elements with grouping
    legend_elements = []
    
    # Add header for digital IO (green shades)
    if digital_io_types:
        legend_elements.append(patches.Patch(facecolor='none', edgecolor='none', label='Digital IO (Green Shades)'))
        for dev_type in sorted(digital_io_types):
            color = get_device_color_180nm(dev_type)
            legend_elements.append(patches.Patch(facecolor=color, edgecolor='black', label=dev_type))
    
    # Add header for analog IO (blue shades)
    if analog_io_types:
        legend_elements.append(patches.Patch(facecolor='none', edgecolor='none', label='Analog IO (Blue Shades)'))
        for dev_type in sorted(analog_io_types):
            color = get_device_color_180nm(dev_type)
            legend_elements.append(patches.Patch(facecolor=color, edgecolor='black', label=dev_type))
    
    # Add other devices (corners, fillers, etc.) with header
    if other_types:
        legend_elements.append(patches.Patch(facecolor='none', edgecolor='none', label='Other Components'))
        for dev_type in sorted(other_types):
            color = get_device_color_180nm(dev_type)
            legend_elements.append(patches.Patch(facecolor=color, edgecolor='black', label=dev_type))
    
    # Add blank to legend if present
    if any(d.get('device_category') == 'blank' for d in all_devices):
        legend_elements.append(patches.Patch(facecolor='#FF0000', edgecolor='black', linestyle='--', label='Blank (Domain Mismatch)'))
    
    if legend_elements:
        # Position legend in upper right, but outside the plot area to avoid overlap
        ax.legend(handles=legend_elements, 
                 loc='upper left',
                 bbox_to_anchor=(1.02, 1.0),
                 fontsize=8,
                 frameon=True,
                 fancybox=True,
                 shadow=False,
                 handlelength=1.5)
    
    # Save figure
    if output_path is None:
        il_path = Path(il_file_path)
        output_path = il_path.parent / f"{il_path.stem}_visualization.png"
    else:
        output_path = Path(output_path)
    
    # Adjust layout to make room for legend
    plt.tight_layout(rect=[0, 0, 0.85, 1])  # Leave 15% space on the right for legend
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    return str(output_path)


def visualize_layout_from_components_T180(layout_components: List[Dict], output_path: str, ring_config: Dict) -> str:
    """
    Generate visual diagram from layout component data for T180
    Supports blank type visualization
    
    Args:
        layout_components: List of component dictionaries with position, type, device, etc.
        output_path: Output path for image
        ring_config: Ring configuration with chip dimensions
    
    Returns:
        Path to generated image file
    """
    if not layout_components:
        raise ValueError("No layout components provided")
    
    # Get chip dimensions
    chip_width = ring_config.get("chip_width", 2250)
    chip_height = ring_config.get("chip_height", 2160)
    
    # Add padding for visualization
    padding = 50
    fig_width = max(chip_width + 2 * padding, 400)
    fig_height = max(chip_height + 2 * padding, 400)
    
    # Create figure
    fig, ax = plt.subplots(1, 1, figsize=(fig_width/50, fig_height/50))
    ax.set_xlim(-padding, chip_width + padding)
    ax.set_ylim(-padding, chip_height + padding)
    ax.set_aspect('equal')
    ax.axis('off')
    
    # Draw each component
    for component in layout_components:
        comp_type = component.get("type", "pad")
        x, y = component.get("position", [0, 0])
        orientation = component.get("orientation", "R0")
        device = component.get("device", "")
        name = component.get("name", "")
        
        # Get color
        color = get_device_color_180nm(device if device else "default")
        
        # Get device dimensions based on type
        if comp_type == "corner":
            width = CORNER_SIZE_180NM
            height = CORNER_SIZE_180NM
        elif comp_type == "filler":
            if 'PFILLER10' in device:
                width = FILLER10_WIDTH_180NM
                height = FILLER10_HEIGHT_180NM
            else:
                width = FILLER_WIDTH_180NM
                height = FILLER_HEIGHT_180NM
        elif comp_type == "blank":
            width = FILLER10_WIDTH_180NM
            height = FILLER10_HEIGHT_180NM
            color = '#FF0000'  # Red for blank
        else:  # pad
            width = PAD_WIDTH_180NM
            height = PAD_HEIGHT_180NM
        
        # Calculate rectangle based on rotation
        rect_x, rect_y, rect_w, rect_h = get_rectangle_for_rotation_180nm(
            x, y, orientation, width, height
        )
        
        # Create rectangle
        if comp_type == "blank":
            rect = patches.Rectangle(
                (rect_x, rect_y), rect_w, rect_h,
                linewidth=2, edgecolor='black', facecolor='#FF0000', alpha=0.6,
                linestyle='--'  # Dashed border for blank
            )
        else:
            rect = patches.Rectangle(
                (rect_x, rect_y), rect_w, rect_h,
                linewidth=2, edgecolor='black', facecolor=color, alpha=0.8
            )
        ax.add_patch(rect)
        
        # Add text label
        if comp_type == "blank":
            label = "Blank"
        else:
            label = name or device
        
        center_x = rect_x + rect_w / 2
        center_y = rect_y + rect_h / 2
        
        font_size = 6 if comp_type in ["filler", "blank"] else 7
        ax.text(center_x, center_y, label, 
                ha='center', va='center', 
                fontsize=font_size, 
                weight='normal')
    
    ax.set_title('IO Ring Layout Visualization (T180)', fontsize=14, fontweight='bold', pad=20)
    
    # Add legend
    legend_elements = [
        patches.Patch(facecolor='#32CD32', edgecolor='black', label='Digital IO'),
        patches.Patch(facecolor='#4A90E2', edgecolor='black', label='Analog IO'),
        patches.Patch(facecolor='#FF6B6B', edgecolor='black', label='Corner'),
        patches.Patch(facecolor='#C0C0C0', edgecolor='black', label='Filler'),
        patches.Patch(facecolor='#FF0000', edgecolor='black', linestyle='--', label='Blank (Domain Mismatch)')
    ]
    ax.legend(handles=legend_elements, loc='upper left', bbox_to_anchor=(1.02, 1.0), fontsize=8)
    
    # Save figure
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout(rect=[0, 0, 0.85, 1])
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    return str(output_path)


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python layout_visualizer_T180.py <il_file_path> [output_path]")
        sys.exit(1)
    
    il_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    try:
        result_path = visualize_layout_T180(il_file, output_file)
        print(f"[OK] Visualization saved to: {result_path}")
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
