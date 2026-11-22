"""Record processor for stream data (Fixed revision)."""

from typing import Any, Dict, List, Optional


def transform_records(records: List[Dict[str, Any]]) -> List[str]:
    """
    Transforms stream records and extracts normalized IDs.
    
    Args:
        records: List of record dictionaries.
        
    Returns:
        List of formatted IDs.
    """
    if not records:
        return []
    first = records[0]
    if not isinstance(first, dict) or "id" not in first:
        return []
    primary_id = first["id"]
    output = []
    for r in records:
        if isinstance(r, dict) and "name" in r:
            output.append(f"{primary_id}_{r['name']}")
    return output

