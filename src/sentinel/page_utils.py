"""
Page Utilities Module - Page health checks and cleanup operations.

This module provides utilities for monitoring page health, cleaning up memory,
and handling common page-level operations.
"""

import asyncio
from typing import Optional
from playwright.async_api import Page


async def check_page_health(page: Optional[Page]) -> bool:
    """
    Check if page is healthy and responsive.
    
    Args:
        page: Playwright page object
        
    Returns:
        True if page is healthy
    """
    if not page:
        return False
    
    try:
        # Try to evaluate a simple expression
        result = await page.evaluate("() => document.readyState")
        return result in ['interactive', 'complete']
    except Exception:
        return False


async def maybe_cleanup_memory(
    page: Page,
    steps_since_cleanup: int,
    interval: int = 50
) -> int:
    """
    Cleanup memory if cleanup interval has been reached.
    
    Args:
        page: Playwright page object
        steps_since_cleanup: Steps since last cleanup
        interval: Cleanup interval in steps
        
    Returns:
        Updated steps_since_cleanup (0 if cleanup performed)
    """
    if steps_since_cleanup >= interval:
        try:
            # Trigger garbage collection
            await page.evaluate("() => { if (window.gc) window.gc(); }")
            
            # Clear console
            await page.evaluate("() => console.clear()")
            
            print("🧹 Memory cleanup performed")
            return 0
        except Exception as e:
            print(f"⚠️ Memory cleanup failed: {e}")
            return steps_since_cleanup
    
    return steps_since_cleanup + 1


async def wait_for_page_stable(
    page: Page,
    stability_threshold_ms: int = 500,
    timeout_ms: int = 5000
) -> bool:
    """
    Wait for page to become stable (no network activity).
    
    Args:
        page: Playwright page object
        stability_threshold_ms: Time to wait for stability
        timeout_ms: Maximum time to wait
        
    Returns:
        True if page became stable
    """
    try:
        # Wait for load state
        await page.wait_for_load_state("networkidle", timeout=timeout_ms)
        return True
    except Exception:
        return False


async def get_page_metrics(page: Page) -> dict:
    """
    Get page performance metrics.
    
    Args:
        page: Playwright page object
        
    Returns:
        Dictionary with performance metrics
    """
    try:
        metrics = await page.evaluate("""
            () => {
                const perf = window.performance;
                const nav = perf.getEntriesByType('navigation')[0];
                
                return {
                    loadTime: nav ? nav.loadEventEnd - nav.startTime : 0,
                    domContentLoaded: nav ? nav.domContentLoadedEventEnd - nav.startTime : 0,
                    memory: performance.memory ? {
                        usedJSHeapSize: performance.memory.usedJSHeapSize,
                        totalJSHeapSize: performance.memory.totalJSHeapSize
                    } : null
                };
            }
        """)
        return metrics
    except Exception as e:
        print(f"⚠️ Failed to get page metrics: {e}")
        return {}


async def clear_browser_data(page: Page) -> bool:
    """
    Clear browser data (cookies, storage).
    
    Args:
        page: Playwright page object
        
    Returns:
        True if successful
    """
    try:
        # Clear cookies
        await page.context.clear_cookies()
        
        # Clear local storage
        await page.evaluate("() => localStorage.clear()")
        
        # Clear session storage
        await page.evaluate("() => sessionStorage.clear()")
        
        return True
    except Exception as e:
        print(f"⚠️ Failed to clear browser data: {e}")
        return False
