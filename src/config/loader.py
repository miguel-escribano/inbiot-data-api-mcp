"""Configuration loader supporting YAML, JSON, and environment variables."""

import os
import json
from pathlib import Path
from typing import Dict, Optional
from pydantic import BaseModel, Field, field_validator
import yaml

from src.models.schemas import DeviceConfig


class DeviceConfigInput(BaseModel):
    """User-friendly device configuration input format."""

    name: str
    api_key: str
    system_id: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

    @field_validator("latitude")
    @classmethod
    def validate_latitude(cls, v):
        """Validate latitude is in valid range."""
        if not -90 <= v <= 90:
            raise ValueError(f"Latitude must be between -90 and 90, got {v}")
        return v

    @field_validator("longitude")
    @classmethod
    def validate_longitude(cls, v):
        """Validate longitude is in valid range."""
        if not -180 <= v <= 180:
            raise ValueError(f"Longitude must be between -180 and 180, got {v}")
        return v


class ConfigFile(BaseModel):
    """Root configuration file structure."""

    devices: Dict[str, DeviceConfigInput]
    openweather_api_key: Optional[str] = None


class ConfigLoader:
    """Unified configuration loader supporting multiple sources."""

    @staticmethod
    def load_from_yaml(path: Path) -> Dict[str, DeviceConfig]:
        """
        Load device configurations from YAML file.

        Args:
            path: Path to YAML configuration file

        Returns:
            Dictionary mapping device IDs to DeviceConfig objects

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file is invalid
        """
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        try:
            with open(path, "r", encoding="utf-8") as f:
                raw_config = yaml.safe_load(f)

            config = ConfigFile.model_validate(raw_config)

            # Set OpenWeather API key if provided
            if config.openweather_api_key:
                os.environ["OPENWEATHER_API_KEY"] = config.openweather_api_key

            # Convert to DeviceConfig format
            devices = {}
            for device_id, device_input in config.devices.items():
                devices[device_id] = DeviceConfig(
                    name=device_input.name,
                    api_key=device_input.api_key,
                    system_id=device_input.system_id,
                    coordinates=(device_input.latitude, device_input.longitude),
                )

            return devices

        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in configuration file: {e}")
        except Exception as e:
            raise ValueError(f"Error loading YAML configuration: {e}")

    @staticmethod
    def load_from_json(path: Path) -> Dict[str, DeviceConfig]:
        """
        Load device configurations from JSON file.

        Args:
            path: Path to JSON configuration file

        Returns:
            Dictionary mapping device IDs to DeviceConfig objects

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file is invalid
        """
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        try:
            with open(path, "r", encoding="utf-8") as f:
                raw_config = json.load(f)

            config = ConfigFile.model_validate(raw_config)

            # Set OpenWeather API key if provided
            if config.openweather_api_key:
                os.environ["OPENWEATHER_API_KEY"] = config.openweather_api_key

            # Convert to DeviceConfig format
            devices = {}
            for device_id, device_input in config.devices.items():
                devices[device_id] = DeviceConfig(
                    name=device_input.name,
                    api_key=device_input.api_key,
                    system_id=device_input.system_id,
                    coordinates=(device_input.latitude, device_input.longitude),
                )

            return devices

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in configuration file: {e}")
        except Exception as e:
            raise ValueError(f"Error loading JSON configuration: {e}")

    @staticmethod
    def load_from_env() -> Dict[str, DeviceConfig]:
        """
        Load device configurations from environment variables.

        This is the original loading mechanism for backward compatibility.

        Returns:
            Dictionary mapping device IDs to DeviceConfig objects
        """
        devices = {}

        # Find all device IDs by looking for INBIOT_*_API_KEY patterns
        device_ids = set()
        for key in os.environ:
            if key.startswith("INBIOT_") and key.endswith("_API_KEY"):
                # Extract device ID: INBIOT_{DEVICE_ID}_API_KEY
                device_id = key[7:-8]  # Remove "INBIOT_" prefix and "_API_KEY" suffix
                device_ids.add(device_id)

        for device_id in device_ids:
            api_key = os.environ.get(f"INBIOT_{device_id}_API_KEY")
            system_id = os.environ.get(f"INBIOT_{device_id}_SYSTEM_ID")

            if not api_key or not system_id:
                continue

            # Get optional metadata with defaults
            name = os.environ.get(
                f"INBIOT_{device_id}_NAME", device_id.replace("_", " ").title()
            )
            lat = float(os.environ.get(f"INBIOT_{device_id}_LAT", "0"))
            lon = float(os.environ.get(f"INBIOT_{device_id}_LON", "0"))

            devices[device_id] = DeviceConfig(
                name=name,
                api_key=api_key,
                system_id=system_id,
                coordinates=(lat, lon),
            )

        return devices

    @staticmethod
    def load() -> Dict[str, DeviceConfig]:
        """
        Auto-detect and load configuration from available sources.

        Priority order:
        1. ./inbiot-config.yaml
        2. ./inbiot-config.json
        3. Environment variables (fallback)

        Returns:
            Dictionary mapping device IDs to DeviceConfig objects

        Raises:
            RuntimeError: If no configuration source is found or no devices configured
        """
        # Try YAML first
        yaml_path = Path("inbiot-config.yaml")
        if yaml_path.exists():
            try:
                devices = ConfigLoader.load_from_yaml(yaml_path)
                if devices:
                    return devices
            except Exception as e:
                print(f"Warning: Failed to load {yaml_path}: {e}")

        # Try JSON second
        json_path = Path("inbiot-config.json")
        if json_path.exists():
            try:
                devices = ConfigLoader.load_from_json(json_path)
                if devices:
                    return devices
            except Exception as e:
                print(f"Warning: Failed to load {json_path}: {e}")

        # Fall back to environment variables
        devices = ConfigLoader.load_from_env()
        if devices:
            return devices

        # No configuration found
        raise RuntimeError(
            "No device configuration found. Please create inbiot-config.yaml, "
            "inbiot-config.json, or set environment variables."
        )
