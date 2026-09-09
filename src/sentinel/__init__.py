"""
Sentinel module - Browser automation utilities.

This module provides browser automation helpers.
"""

from .human_behavior import (
    human_mouse_move,
    human_scroll,
    human_click,
    human_type,
    random_delay,
    human_hover,
)

__all__ = [
    # Human behavior
    'human_mouse_move',
    'human_scroll',
    'human_click',
    'human_type',
    'random_delay',
    'human_hover',
]
