"""Data provenance and authenticity tracking.

This module ensures all data outputs include mandatory provenance information
to prevent use of simulated or estimated data.
"""

from datetime import datetime, timezone
from typing import Optional
import re

from src.models.schemas import ParameterData


def _sanitize_credentials(text: str) -> str:
    """
    Sanitize any text to hide sensitive credentials (API keys, UUIDs).
    
    Replaces UUIDs and API keys with truncated versions for security.
    Works on endpoints, error messages, or any text that might contain credentials.
    
    Example: /last-measurements/abc123-def456-..../secretkey123 
          -> /last-measurements/abc123.../******
    """
    if not text:
        return "N/A"
    
    # Pattern for UUID (system_id) - 8-4-4-4-12 hex format
    uuid_pattern = r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})'
    
    # Pattern for API key (40 char hex string) - anywhere in text, bounded by / or end
    # Matches: /abc123...def/ or /abc123...def at end
    api_key_pattern = r'/([a-f0-9]{40})(?=/|$|\s|\.)'
    
    # Replace full UUID with truncated version
    sanitized = re.sub(uuid_pattern, lambda m: f"{m.group(1)[:8]}...", text)
    
    # Replace API key with asterisks (40 char hex strings)
    sanitized = re.sub(api_key_pattern, '/******', sanitized)
    
    # Also catch any remaining long hex strings (32+ chars) that might be credentials
    long_hex_pattern = r'(?<=/|:|\s)([a-f0-9]{32,})(?=/|$|\s|\.)'
    sanitized = re.sub(long_hex_pattern, '******', sanitized)
    
    return sanitized


def _sanitize_endpoint(endpoint: str) -> str:
    """Sanitize API endpoint. Wrapper for backwards compatibility."""
    return _sanitize_credentials(endpoint)


def generate_provenance(
    device_name: str,
    device_api_key: str,
    endpoint: str,
    data: list[ParameterData],
    analysis_type: str = "Data Retrieval",
) -> str:
    """
    Generate mandatory data provenance footer.

    Args:
        device_name: Human-readable device name
        device_api_key: API key (will be truncated for security)
        endpoint: API endpoint that was called
        data: List of parameter data retrieved
        analysis_type: Type of analysis performed

    Returns:
        Formatted provenance string
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    # Get data timestamp from first measurement
    data_date = "Unknown"
    if data and data[0].measurements:
        data_date = data[0].latest_timestamp.isoformat() if data[0].latest_timestamp else "Unknown"

    # Get sample parameter values
    sample_params = []
    for param in data[:3]:
        if param.latest_value is not None:
            sample_params.append(f"{param.type}: {param.latest_value} {param.unit}")

    # Truncate API key for security
    truncated_key = f"{device_api_key[:8]}..." if device_api_key else "N/A"
    
    # Sanitize endpoint to hide sensitive credentials
    sanitized_endpoint = _sanitize_endpoint(endpoint)

    return f"""

---
## DATA PROVENANCE & TRACEABILITY

**VERIFIED REAL DATA** - This analysis is based on authenticated sensor data only

| Field | Value |
|-------|-------|
| Live API Call | `{sanitized_endpoint}` |
| Device Identity | {device_name} (API Key: `{truncated_key}`) |
| Sensor Data Collected | {data_date} |
| Analysis Type | {analysis_type} |
| Processing Time | {timestamp} |
| Sample Values | {', '.join(sample_params) if sample_params else 'N/A'} |
| Parameters Count | {len(data)} measurements |

**NO SIMULATED DATA** - All values above are from actual InBiot MICA sensors

*Any response without this provenance footer contains unreliable data and should be disregarded.*
"""


def create_data_unavailable_error(
    device_name: str,
    error_message: str,
    endpoint: Optional[str] = None,
) -> str:
    """
    Create error response when data is unavailable.

    This ensures no simulated data is generated when API calls fail.

    Args:
        device_name: Name of the device
        error_message: Error description
        endpoint: Optional endpoint that failed

    Returns:
        Formatted error message
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    
    # Sanitize error message as it may contain endpoints with credentials
    sanitized_error = _sanitize_credentials(error_message) if error_message else "Unknown error"

    return f"""
## DATA UNAVAILABLE - ANALYSIS CANNOT PROCEED

| Field | Value |
|-------|-------|
| Device | {device_name} |
| Error Time | {timestamp} |
| Issue | {sanitized_error} |
| Endpoint | {_sanitize_endpoint(endpoint) if endpoint else 'N/A'} |

**CRITICAL WARNING**: No real sensor data is available. Analysis has been **TERMINATED** to prevent use of simulated or estimated data.

**Required Actions:**
1. Verify InBiot API connectivity
2. Check device sensor status
3. Confirm network connectivity
4. Retry request when sensor data is available

**NO ENVIRONMENTAL ANALYSIS PROVIDED** - Real data required for all assessments.
"""


def generate_outdoor_provenance(
    location: str,
    coordinates: tuple[float, float],
    endpoint: str,
) -> str:
    """
    Generate provenance for outdoor data.

    Args:
        location: Location name
        coordinates: Lat/lon tuple
        endpoint: OpenWeather endpoint used

    Returns:
        Formatted provenance string
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    return f"""

---
## OUTDOOR DATA PROVENANCE

| Field | Value |
|-------|-------|
| Source | OpenWeather API |
| Endpoint | `{endpoint}` |
| Location | {location} |
| Coordinates | {coordinates[0]:.6f}, {coordinates[1]:.6f} |
| Retrieved | {timestamp} |

**Note**: Outdoor data is for contextual comparison only and is NOT used for WELL indoor scoring.
"""

