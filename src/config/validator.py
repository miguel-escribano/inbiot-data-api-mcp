"""Configuration validation utilities."""

from typing import Dict, List
from src.models.schemas import DeviceConfig


def validate_devices(devices: Dict[str, DeviceConfig]) -> List[str]:
    """
    Validate device configurations and return warnings/issues.

    Args:
        devices: Dictionary of device configurations

    Returns:
        List of warning messages (empty if all valid)
    """
    warnings = []

    if not devices:
        warnings.append("No devices configured")
        return warnings

    # Track for duplicate detection
    seen_system_ids = {}
    seen_api_keys = {}

    for device_id, config in devices.items():
        # Check for (0, 0) coordinates (likely default/unset)
        if config.coordinates == (0, 0):
            warnings.append(
                f"Device '{device_id}' has default coordinates (0, 0). "
                "Outdoor weather data may be inaccurate."
            )

        # Check for duplicate system IDs
        if config.system_id in seen_system_ids:
            warnings.append(
                f"Device '{device_id}' has the same system_id as '{seen_system_ids[config.system_id]}'. "
                "This may cause data conflicts."
            )
        else:
            seen_system_ids[config.system_id] = device_id

        # Check for duplicate API keys
        if config.api_key in seen_api_keys:
            warnings.append(
                f"Device '{device_id}' has the same api_key as '{seen_api_keys[config.api_key]}'. "
                "Consider using unique API keys per device if available."
            )
        else:
            seen_api_keys[config.api_key] = device_id

        # Validate API key format (basic check for UUID-like format)
        if len(config.api_key) < 8:
            warnings.append(
                f"Device '{device_id}' has a very short API key ('{config.api_key[:8]}...'). "
                "Verify this is correct."
            )

        # Validate system ID format
        if len(config.system_id) < 8:
            warnings.append(
                f"Device '{device_id}' has a very short system ID ('{config.system_id[:8]}...'). "
                "Verify this is correct."
            )

    return warnings


def print_validation_warnings(warnings: List[str]) -> None:
    """
    Print validation warnings to console.

    Args:
        warnings: List of warning messages
    """
    if warnings:
        print("\n⚠️  Configuration Warnings:")
        for warning in warnings:
            print(f"  - {warning}")
        print()
