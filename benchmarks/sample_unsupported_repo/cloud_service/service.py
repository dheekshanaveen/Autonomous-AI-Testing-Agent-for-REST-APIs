"""Service requiring an unavailable native cloud driver."""

# Deliberately missing external dependency to test setup gap handling
import nonexistent_super_database_driver


def connect_cloud(endpoint: str) -> bool:
    """Connect to external cloud endpoint."""
    return nonexistent_super_database_driver.connect(endpoint)

