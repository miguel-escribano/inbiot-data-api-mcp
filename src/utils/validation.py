"""Device validation utilities."""

from src.models.schemas import DeviceConfig


def validate_device(devices: dict[str, DeviceConfig], device_id: str) -> DeviceConfig:
    """Look up a device by ID, raising ValueError if unknown.

    Args:
        devices: Device registry.
        device_id: ID to look up.

    Returns:
        The matching DeviceConfig.

    Raises:
        ValueError: If device_id is not in devices.
    """
    if device_id not in devices:
        raise ValueError(f"Unknown device: {device_id}. Use list_devices to see available options.")
    return devices[device_id]
