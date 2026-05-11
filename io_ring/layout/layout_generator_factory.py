#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Layout Generator Factory - T180 (180nm) specific
"""

from .generator import LayoutGeneratorT180, generate_layout_from_json as generate_T180


def create_layout_generator():
    """Create T180 layout generator instance"""
    return LayoutGeneratorT180()


def generate_layout_from_json(json_file: str, output_file: str = "generated_layout.il", process_node: str = "T180"):
    """Generate layout from JSON file using T180 generator

    Args:
        json_file: Path to intent graph JSON file
        output_file: Path to output SKILL file
        process_node: Process node (kept for API compatibility, always T180)
    """
    return generate_T180(json_file, output_file)


def validate_layout_config(json_file: str, process_node: str = "T180") -> dict:
    """Validate intent graph file

    Args:
        json_file: Path to intent graph JSON file
        process_node: Process node (kept for API compatibility, always T180)

    Returns:
        Validation result dictionary with 'valid' and 'message' keys
    """
    import json

    print(f"Validating intent graph file: {json_file}")

    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
    except FileNotFoundError:
        return {"valid": False, "message": f"Intent graph file not found: {json_file}"}
    except json.JSONDecodeError as e:
        return {"valid": False, "message": f"JSON format error - {e}"}

    generator = create_layout_generator()

    # Check if it's the new relative position format
    if "ring_config" in config_data and "instances" in config_data:
        print("Detected relative position format, converting for validation...")

        instances = config_data["instances"]
        ring_config = config_data["ring_config"]
        layout_components = generator.convert_relative_to_absolute(instances, ring_config)

        print(f"Conversion completed: {len(instances)} relative positions -> {len(layout_components)} absolute positions")

    else:
        if "layout_components" not in config_data:
            return {"valid": False, "message": "Missing 'layout_components' or 'instances' field"}

        layout_components = config_data["layout_components"]

    validation_result = generator.layout_validator.validate_layout_rules(layout_components, "T180")

    return validation_result
