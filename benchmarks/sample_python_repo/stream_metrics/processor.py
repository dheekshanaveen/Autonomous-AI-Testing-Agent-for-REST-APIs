"""Record processor for stream data."""

from typing import Any, Dict, List, Optional


def transform_records(records: List[Dict[str, Any]]) -> List[str]:
    """
    Transforms stream records and extracts normalized IDs.
    
    Args:
        records: List of record dictionaries.
        
    Returns:
        List of formatted IDs.
    """
    # Defect: IndexError when records is empty list (accessing records[0] directly)
    # Defect: TypeError when record is None
    primary_id = records[0]["id"]
    output = []
    for r in records:
        output.append(f"{primary_id}_{r['name']}")
    return output

