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

from .browser_actions import (
    robust_click,
    robust_js_click,
    robust_click_by_text,
    robust_radio_click,
    robust_checkbox_click,
    robust_button_click,
    scroll_element_into_view,
    dismiss_browser_dialogs,
)

from .page_utils import (
    check_page_health,
    maybe_cleanup_memory,
    wait_for_page_stable,
    get_page_metrics,
    clear_browser_data,
)

from .profile_manager import ProfileManager
from .js_loader import JSLoader, load_js

__all__ = [
    # Human behavior
    'human_mouse_move',
    'human_scroll',
    'human_click',
    'human_type',
    'random_delay',
    'human_hover',
    
    # Browser actions
    'robust_click',
    'robust_js_click',
    'robust_click_by_text',
    'robust_radio_click',
    'robust_checkbox_click',
    'robust_button_click',
    'scroll_element_into_view',
    'dismiss_browser_dialogs',
    
    # Page utilities
    'check_page_health',
    'maybe_cleanup_memory',
    'wait_for_page_stable',
    'get_page_metrics',
    'clear_browser_data',
    
    # Profile management
    'ProfileManager',
    
    # JS loading
    'JSLoader',
    'load_js',
]
