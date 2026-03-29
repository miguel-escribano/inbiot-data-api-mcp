"""Shared test configuration."""

import os

# Set up test device env vars before server import
os.environ.setdefault("INBIOT_TEST_API_KEY", "0000000000000000000000000000000000000000")
os.environ.setdefault("INBIOT_TEST_SYSTEM_ID", "00000000-0000-0000-0000-000000000000")
os.environ.setdefault("INBIOT_TEST_NAME", "Test Device")
os.environ.setdefault("INBIOT_TEST_LAT", "42.0")
os.environ.setdefault("INBIOT_TEST_LON", "-1.6")
