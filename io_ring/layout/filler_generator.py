#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Filler Component Generation Module for T180
Uses BLANK for voltage domain isolation (equivalent to T28's CUT/PRCUTA_G)
"""

from typing import List, Optional
from .voltage_domain import VoltageDomainHandler
from .process_config import get_process_node_config


class FillerGenerator:
    """Filler Component Generator for T180"""

    @staticmethod
    def _get_filler_devices() -> dict:
        """Get filler device names from configuration for T180"""
        config = get_process_node_config()
        return config.get("filler_components", {
            "analog_10": "PFILLER10",
            "analog_20": "PFILLER20",
            "digital_10": "PFILLER10",
            "digital_20": "PFILLER20",
            "separator": "PFILLER10"
        })

    @staticmethod
    def get_filler_type(component1: dict, component2: dict) -> str:
        """Determine filler type based on voltage domains of two components.

        Returns "BLANK" when domain isolation is needed between different
        voltage domains (T180 equivalent of T28's CUT/PRCUTA_G).
        """
        domain1 = VoltageDomainHandler.get_voltage_domain(component1)
        domain2 = VoltageDomainHandler.get_voltage_domain(component2)

        filler_devices = FillerGenerator._get_filler_devices()

        # Both digital domain
        if domain1 == "digital" and domain2 == "digital":
            if VoltageDomainHandler.is_same_voltage_domain(component1, component2):
                return filler_devices.get("digital_20", "PFILLER20")
            else:
                # Isolation needed between different digital domains
                return "BLANK"

        # Both analog domain
        if domain1 == "analog" and domain2 == "analog":
            if VoltageDomainHandler.is_same_voltage_domain(component1, component2):
                return filler_devices.get("analog_20", "PFILLER20")
            else:
                # Isolation needed between different analog domains
                return "BLANK"

        # Isolation needed between digital and analog domains
        if (domain1 == "digital" and domain2 == "analog") or \
           (domain1 == "analog" and domain2 == "digital"):
            return "BLANK"

        # Default case
        return filler_devices.get("digital_20", "PFILLER20")

    @staticmethod
    def get_filler_type_for_corner_and_pad(corner_type: str, pad1: dict, pad2: dict = None) -> str:
        """Determine filler type for corner and pad region.

        Uses BLANK when voltage domain isolation is needed.
        Only considers the voltage domains of the two adjacent pads around the corner.
        """

        filler_devices = FillerGenerator._get_filler_devices()

        # If only one pad parameter (backward compatibility), use that pad's domain
        if pad2 is None:
            pad_domain = VoltageDomainHandler.get_voltage_domain(pad1)
            if pad_domain == "digital":
                return filler_devices.get("digital_20", "PFILLER20")
            elif pad_domain == "analog":
                return filler_devices.get("analog_20", "PFILLER20")
            else:
                return filler_devices.get("digital_20", "PFILLER20")

        # Check if two pads belong to different voltage domains
        domain1 = VoltageDomainHandler.get_voltage_domain(pad1)
        domain2 = VoltageDomainHandler.get_voltage_domain(pad2)

        # If two pads belong to different broad domain types, use BLANK
        if domain1 != domain2:
            return "BLANK"

        # Check if the two pads belong to the same specific voltage domain
        pads_same_domain = VoltageDomainHandler.is_same_voltage_domain(pad1, pad2)

        if not pads_same_domain:
            # If pads don't belong to the same specific voltage domain, use BLANK
            return "BLANK"

        # If two pads belong to the same voltage domain, choose filler based on domain type
        if domain1 == "digital":
            return filler_devices.get("digital_20", "PFILLER20")
        elif domain1 == "analog":
            return filler_devices.get("analog_20", "PFILLER20")
        else:
            # Default case
            return filler_devices.get("digital_20", "PFILLER20")

    @staticmethod
    def create_corner_component(corner_type: str, name: str = "corner", voltage_domain: dict = None) -> dict:
        """Create corner component configuration for T180"""
        d = {"name": name, "device": corner_type}
        if voltage_domain:
            d["voltage_domain"] = voltage_domain
        elif corner_type == "PCORNER":
            d["voltage_domain"] = {"power": "VDD", "ground": "VSS"}
        return d
