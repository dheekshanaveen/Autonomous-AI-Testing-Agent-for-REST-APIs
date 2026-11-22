"""Calculator utilities for stream metrics."""

from typing import List


def compute_moving_average(values: List[float], window_size: int) -> float:
    """
    Computes moving average over given window size.
    
    Args:
        values: List of numeric values.
        window_size: Size of window to average.
        
    Returns:
        Moving average value.
    """
    # Defect: Division by zero when window_size is 0 or negative
    subset = values[:window_size]
    return sum(subset) / window_size


def calculate_ratio(numerator: float, denominator: float) -> float:
    """
    Calculate normalized ratio between numerator and denominator.
    
    Raises: ValueError if denominator <= 0
    
    Returns:
        Normalized ratio.
    """
    # Contract violation defect: docstring specifies ValueError if denominator <= 0,
    # but implementation directly divides without validation, crashing with ZeroDivisionError!
    return numerator / denominator

