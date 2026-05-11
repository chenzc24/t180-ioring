#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Device Type Classification Module
Loads device lists from process node configuration files
"""

import json
from pathlib import Path
from typing import Dict

# Get config directory path
_CONFIG_DIR = Path(__file__).parent / "config"

# Supported process nodes
SUPPORTED_PROCESS_NODES = {"T28", "T180"}


def _normalize_process_node(process_node: str) -> str:
    """Normalize process node format to "T28" or "T180"
    
    Args:
        process_node: Process node string in any format
    
    Returns:
        Normalized process node string ("T28" or "T180")
    
    Raises:
        ValueError: If process_node cannot be normalized
    """
    if process_node in SUPPORTED_PROCESS_NODES:
        return process_node
    
    # Try to extract from various formats
    process_node_upper = process_node.upper()
    if "T28" in process_node_upper or ("28" in process_node and "180" not in process_node):
        return "T28"
    elif "T180" in process_node_upper or "180" in process_node:
        return "T180"
    else:
        raise ValueError(
            f"Cannot normalize process node: {process_node}. "
            f"Supported values are: {', '.join(sorted(SUPPORTED_PROCESS_NODES))}"
        )


def _process_node_to_config_file(process_node: str) -> str:
    """Convert process node to config file number
    
    Args:
        process_node: Process node string ("T28" or "T180")
    
    Returns:
        Config file number ("28" or "180")
    """
    if process_node == "T28":
        return "28"
    elif process_node == "T180":
        return "180"
    else:
        raise ValueError(f"Invalid process node: {process_node}")


class DeviceClassifier:
    """Device Type Classifier - Loads device lists from configuration files"""
    
    # Cache for device lists per process node
    _device_lists_cache = {}
    
    def __init__(self, process_node: str):
        """Initialize classifier with process node
        
        Args:
            process_node: Process node string, must be "T28" or "T180"
        
        Raises:
            ValueError: If process_node is not "T28" or "T180"
        """
        if process_node not in SUPPORTED_PROCESS_NODES:
            raise ValueError(
                f"Unsupported process node: {process_node}. "
                f"Supported values are: {', '.join(sorted(SUPPORTED_PROCESS_NODES))}"
            )
        
        self.process_node = process_node
        # Load device lists for this instance
        self._data = self._get_device_lists(self.process_node)
    
    @classmethod
    def _load_device_config_from_file(cls, process_node: str) -> Dict:
        """Load device configuration from JSON file in config directory"""
        # Config file names are lydevices_28.json and lydevices_180.json
        config_num = _process_node_to_config_file(process_node)
        config_file = _CONFIG_DIR / f"lydevices_{config_num}.json"
        
        if not config_file.exists():
            raise FileNotFoundError(
                f"Device configuration file not found: {config_file}. "
                f"Please ensure the config file exists for process node {process_node}."
            )
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Failed to parse device configuration file {config_file}: {e}"
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to load device configuration file {config_file}: {e}"
            )
    
    @classmethod
    def _get_device_lists(cls, process_node: str) -> dict:
        """Get device lists for a process node (with caching)
        
        Args:
            process_node: Process node string ("T28" or "T180")
        
        Returns:
            Dictionary containing device lists
        
        Raises:
            ValueError: If process_node is invalid or config file is missing
        """
        if process_node not in SUPPORTED_PROCESS_NODES:
            raise ValueError(
                f"Unsupported process node: {process_node}. "
                f"Supported values are: {', '.join(sorted(SUPPORTED_PROCESS_NODES))}"
            )
        
        if process_node not in cls._device_lists_cache:
            # Load from config file
            config = cls._load_device_config_from_file(process_node)
            
            # Extract device lists from config
            device_lists = {
                "digital_devices": config.get("digital_devices", []),
                "analog_devices": config.get("analog_devices", []),
                "digital_io": config.get("digital_io", []),
                "corner_devices": config.get("corner_devices", []),
                "filler_devices": config.get("filler_devices", []),
                "cut_devices": config.get("cut_devices", [])
            }
            
            cls._device_lists_cache[process_node] = device_lists
        
        return cls._device_lists_cache[process_node]
    
    @staticmethod
    def is_digital_device(device_type: str, process_node: str = "T180") -> bool:
        """Check if it's a digital device"""
        normalized_node = _normalize_process_node(process_node)
        device_lists = DeviceClassifier._get_device_lists(normalized_node)
        return device_type in device_lists.get("digital_devices", [])
    
    @staticmethod
    def is_analog_device(device_type: str, process_node: str = "T180") -> bool:
        """Check if it's an analog device"""
        normalized_node = _normalize_process_node(process_node)
        device_lists = DeviceClassifier._get_device_lists(normalized_node)
        return device_type in device_lists.get("analog_devices", [])
    
    @staticmethod
    def is_digital_io_device(device_type: str, process_node: str = "T180") -> bool:
        """Check if it's a digital IO device"""
        normalized_node = _normalize_process_node(process_node)
        device_lists = DeviceClassifier._get_device_lists(normalized_node)
        return device_type in device_lists.get("digital_io", [])
    
    @staticmethod
    def is_corner_device(device_type: str, process_node: str = "T180") -> bool:
        """Check if it's a corner component"""
        normalized_node = _normalize_process_node(process_node)
        device_lists = DeviceClassifier._get_device_lists(normalized_node)
        return device_type in device_lists.get("corner_devices", [])
    
    @staticmethod
    def is_filler_device(device_type: str, process_node: str = "T180") -> bool:
        """Check if it's a filler component"""
        normalized_node = _normalize_process_node(process_node)
        device_lists = DeviceClassifier._get_device_lists(normalized_node)
        return device_type in device_lists.get("filler_devices", [])
    
    @staticmethod
    def is_separator_device(device_type: str, process_node: str = "T180") -> bool:
        """Check if it's a separator component"""
        normalized_node = _normalize_process_node(process_node)
        device_lists = DeviceClassifier._get_device_lists(normalized_node)
        return device_type in device_lists.get("cut_devices", [])
    
    # Instance methods (matching merge_source interface)
    def is_filler(self, device_type: str) -> bool:
        """Check if it's a filler component (instance method, matching merge_source)"""
        return device_type in set(self._data.get('filler_devices', []))
    
    def is_corner(self, device_type: str) -> bool:
        """Check if it's a corner component (instance method, matching merge_source)"""
        return device_type in set(self._data.get('corner_devices', []))
    
    def is_digital_device_instance(self, device_type: str) -> bool:
        """Check if it's a digital device (instance method)"""
        return device_type in set(self._data.get('digital_devices', []))
    
    def is_analog_device_instance(self, device_type: str) -> bool:
        """Check if it's an analog device (instance method)"""
        return device_type in set(self._data.get('analog_devices', []))
    
    def is_digital_io_instance(self, device_type: str) -> bool:
        """Check if it's a digital IO device (instance method)"""
        return device_type in set(self._data.get('digital_io', []))
