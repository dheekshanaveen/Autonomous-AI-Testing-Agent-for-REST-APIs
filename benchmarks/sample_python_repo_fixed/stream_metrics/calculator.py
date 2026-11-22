"""Calculator utilities for stream metrics (Fixed revision)."""

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
    if not isinstance(values, list):
        return 0.0
    if not isinstance(window_size, int) or window_size <= 0:
        return 0.0
    if not values:
        return 0.0
    subset = values[:window_size]
    return sum(subset) / window_size


def calculate_ratio(numerator: float, denominator: float) -> float:
    """
    Calculate normalized ratio between numerator and denominator.
    
    Raises: ValueError if denominator <= 0
    
    Returns:
        Normalized ratio.
    """
    if not isinstance(numerator, (int, float)) or not isinstance(denominator, (int, float)):
        raise TypeError("numerator and denominator must be numeric.")
    if denominator <= 0:
        raise ValueError("denominator must be greater than zero.")
    return numerator / denominator

