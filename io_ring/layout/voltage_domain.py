#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Voltage Domain Processing Module for T180 (180nm)

Key differences from T28:
- Cannot judge analog/digital from pins (VDD/VSS and VDDPST/VSSPST are the same
  for both analog and digital devices)
- Uses "domain" field from JSON to determine analog/digital
- Uses VDDPST/VSSPST pin labels to identify specific voltage domains
- Uses BLANK (not CUT) to divide different voltage domains
"""

from .device_classifier import DeviceClassifier


class VoltageDomainHandler:
    """Voltage Domain Handler for T180 (180nm) process node"""

    @staticmethod
    def get_voltage_domain(component: dict) -> str:
        """Get the voltage domain type of the component (digital or analog).

        For T180: primarily uses "domain" field from JSON, since pins cannot
        distinguish analog/digital (VDD/VSS and VDDPST/VSSPST are the same).
        """
        # Primary: check "domain" field from JSON
        domain = component.get("domain", "")
        if domain in ("digital", "analog"):
            return domain

        # Secondary: check voltage_domain config (backward compatibility)
        if "voltage_domain" in component:
            voltage_domain = component["voltage_domain"]
            if "digital_domain" in voltage_domain:
                return "digital"
            power = voltage_domain.get("power", "")
            ground = voltage_domain.get("ground", "")
            if "DIG" in power or "DIG" in ground:
                return "digital"
            elif "ANA" in power or "ANA" in ground or "A" in power or "A" in ground:
                return "analog"

        # Tertiary: device-based fallback
        device = component.get("device", "")
        if device:
            if DeviceClassifier.is_digital_device(device, "T180"):
                return "digital"
            if DeviceClassifier.is_analog_device(device, "T180"):
                return "analog"

        return "unknown"

    @staticmethod
    def get_voltage_domain_key(component: dict) -> str:
        """Get the voltage domain key based on VDDPST/VSSPST labels.

        For T180, VDDPST and VSSPST are the voltage judge pins.
        The domain key uniquely identifies a specific voltage domain.
        """
        # Primary: check pin_connection for VDDPST/VSSPST labels
        if "pin_connection" in component:
            pin_connection = component["pin_connection"]
            vddpst = pin_connection.get("VDDPST", {}).get("label", "")
            vsspst = pin_connection.get("VSSPST", {}).get("label", "")
            if vddpst and vsspst:
                domain_type = VoltageDomainHandler.get_voltage_domain(component)
                return f"{domain_type.upper()}_{vddpst}_{vsspst}"

        # Secondary: check voltage_domain config
        if "voltage_domain" in component:
            vd = component["voltage_domain"]
            if "digital_domain" in vd:
                return vd["digital_domain"]
            if "power" in vd and "ground" in vd:
                return f"{vd['power']}_{vd['ground']}"

        # Fallback: domain field based
        domain = component.get("domain", "")
        if domain in ("digital", "analog"):
            return f"{domain.upper()}_DEFAULT"

        return "unknown"

    @staticmethod
    def is_same_digital_domain(component1: dict, component2: dict) -> bool:
        """Determine if two components belong to the same digital domain"""
        domain_key1 = VoltageDomainHandler.get_voltage_domain_key(component1)
        domain_key2 = VoltageDomainHandler.get_voltage_domain_key(component2)

        if domain_key1.startswith("DIGITAL_") and domain_key2.startswith("DIGITAL_"):
            return domain_key1 == domain_key2

        return False

    @staticmethod
    def is_same_voltage_domain(component1: dict, component2: dict) -> bool:
        """Determine if two components belong to the same voltage domain.

        Compares both the broad domain type (analog/digital) and the specific
        voltage domain key (based on VDDPST/VSSPST labels).
        """
        # First check broad domain type
        domain1 = VoltageDomainHandler.get_voltage_domain(component1)
        domain2 = VoltageDomainHandler.get_voltage_domain(component2)

        if domain1 != domain2:
            return False

        # Both in same broad category, check specific domain key
        key1 = VoltageDomainHandler.get_voltage_domain_key(component1)
        key2 = VoltageDomainHandler.get_voltage_domain_key(component2)

        if key1 == key2 and key1 != "unknown":
            return True

        # If both keys are unknown but same domain type, treat as same domain
        if key1 == "unknown" and key2 == "unknown" and domain1 == domain2:
            return True

        return False

    @staticmethod
    def is_voltage_domain_provider(component: dict) -> bool:
        """Determine if the component is a voltage domain provider"""
        device = component.get("device", "")
        provider_devices = [
            "PVDD1CDG", "PVSS1CDG",
            "PVDD2CDG", "PVSS2CDG",
            "PVDD1ANA", "PVSS1ANA",
        ]
        return device in provider_devices

    @staticmethod
    def is_voltage_domain_user(component: dict) -> bool:
        """Determine if the component is a voltage domain user"""
        device = component.get("device", "")
        user_devices = [
            "PDDW0412SCDG",
        ]
        return device in user_devices
