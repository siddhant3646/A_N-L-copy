"""
Browser Actions Module - Robust browser interaction helpers.

This module provides robust wrappers around Playwright actions with
retry logic, error handling, and human-like behavior simulation.
"""

import asyncio
import random
from typing import Optional, List, Any
from playwright.async_api import Page, Locator

from src.sentinel.human_behavior import human_click


async def robust_click(
    locator: Locator,
    description: str = "element",
    timeout: int = 5000,
    retries: int = 3,
    human_like: bool = True
) -> bool:
    """
    Robustly click an element with retry logic.
    
    Args:
        locator: Playwright locator
        description: Description for logging
        timeout: Timeout in milliseconds
        retries: Number of retry attempts
        human_like: Whether to use human-like clicking
        
    Returns:
        True if click was successful
    """
    for attempt in range(retries):
        try:
            # Check if visible
            is_visible = await locator.is_visible(timeout=timeout)
            if not is_visible:
                print(f"⚠️ {description} not visible (attempt {attempt + 1}/{retries})")
                await asyncio.sleep(0.5)
                continue
            
            # Click
            if human_like:
                element = await locator.element_handle()
                if element:
                    box = await element.bounding_box()
                    if box:
                        page = locator.page
                        x = int(box['x'] + box['width'] / 2)
                        y = int(box['y'] + box['height'] / 2)
                        await human_click(page, x=x, y=y)
                    else:
                        await locator.click(timeout=timeout)
                else:
                    await locator.click(timeout=timeout)
            else:
                await locator.click(timeout=timeout)
            
            return True
            
        except Exception as e:
            print(f"⚠️ Click failed for {description} (attempt {attempt + 1}/{retries}): {e}")
            if attempt < retries - 1:
                await asyncio.sleep(random.uniform(0.5, 1.5))
    
    return False


async def robust_js_click(
    page: Page,
    selector: str,
    description: str = "element",
    timeout: int = 5000
) -> bool:
    """
    Click an element using JavaScript as fallback.
    
    Args:
        page: Playwright page
        selector: CSS selector
        description: Description for logging
        timeout: Timeout in milliseconds
        
    Returns:
        True if successful
    """
    try:
        # Wait for element
        await page.wait_for_selector(selector, timeout=timeout)
        
        # Try JavaScript click
        result = await page.evaluate(f"""
            () => {{
                const el = document.querySelector('{selector}');
                if (el) {{
                    el.click();
                    el.scrollIntoView({{behavior: 'smooth', block: 'center'}});
                    return true;
                }}
                return false;
            }}
        """)
        
        if result:
            await asyncio.sleep(0.3)
            return True
        else:
            print(f"⚠️ Element not found for JS click: {description}")
            return False
            
    except Exception as e:
        print(f"⚠️ JS click failed for {description}: {e}")
        return False


async def robust_click_by_text(
    page: Page,
    text: str,
    tag: str = "button",
    exact: bool = False,
    timeout: int = 5000
) -> bool:
    """
    Click element by its text content.
    
    Args:
        page: Playwright page
        text: Text to search for
        tag: HTML tag to search within
        exact: Whether to match exact text
        timeout: Timeout in milliseconds
        
    Returns:
        True if successful
    """
    try:
        if exact:
            locator = page.locator(f"{tag}:has-text('{text}')")
        else:
            locator = page.get_by_text(text, exact=False)
        
        return await robust_click(locator, f"{tag} with text '{text}'", timeout)
    except Exception as e:
        print(f"⚠️ Click by text failed for '{text}': {e}")
        return False


async def robust_radio_click(
    page: Page,
    value_or_text: str,
    fallback_index: Optional[int] = None
) -> bool:
    """
    Click a radio button by value or text.
    
    Args:
        page: Playwright page
        value_or_text: Value or text of radio button
        fallback_index: Index to click if text/value not found
        
    Returns:
        True if successful
    """
    try:
        # Try by label text first
        labels = await page.query_selector_all(f"label:has-text('{value_or_text}')")
        for label in labels:
            # Try to find associated radio
            radio = await label.query_selector("input[type='radio']")
            if radio:
                await radio.click()
                return True
            # Try clicking the label itself
            await label.click()
            return True
        
        # Try by radio value
        radios = await page.query_selector_all(f"input[type='radio'][value='{value_or_text}']")
        if radios:
            await radios[0].click()
            return True
        
        # Fallback to index
        if fallback_index is not None:
            all_radios = await page.query_selector_all("input[type='radio']")
            if 0 <= fallback_index < len(all_radios):
                await all_radios[fallback_index].click()
                return True
        
        print(f"⚠️ Radio button not found: {value_or_text}")
        return False
        
    except Exception as e:
        print(f"⚠️ Radio click failed: {e}")
        return False


async def robust_checkbox_click(
    page: Page,
    value_or_text: str,
    select_all: bool = False
) -> bool:
    """
    Click a checkbox by value or text.
    
    Args:
        page: Playwright page
        value_or_text: Value or text of checkbox
        select_all: Whether to select all matching checkboxes
        
    Returns:
        True if successful
    """
    try:
        # Try by label text
        labels = await page.query_selector_all(f"label:has-text('{value_or_text}')")
        checkboxes = []
        
        for label in labels:
            checkbox = await label.query_selector("input[type='checkbox']")
            if checkbox:
                checkboxes.append(checkbox)
        
        # Try by checkbox value
        if not checkboxes:
            checkboxes = await page.query_selector_all(
                f"input[type='checkbox'][value='{value_or_text}']"
            )
        
        if not checkboxes:
            print(f"⚠️ Checkbox not found: {value_or_text}")
            return False
        
        # Click checkboxes
        if select_all:
            for checkbox in checkboxes:
                await checkbox.click()
                await asyncio.sleep(0.1)
        else:
            await checkboxes[0].click()
        
        return True
        
    except Exception as e:
        print(f"⚠️ Checkbox click failed: {e}")
        return False


async def robust_button_click(
    page: Page,
    text_patterns: List[str],
    fallback_selector: Optional[str] = None,
    timeout: int = 5000
) -> bool:
    """
    Click a button matching any of the text patterns.
    
    Args:
        page: Playwright page
        text_patterns: List of button texts to try
        fallback_selector: Fallback CSS selector
        timeout: Timeout in milliseconds
        
    Returns:
        True if successful
    """
    for pattern in text_patterns:
        try:
            # Try exact text match
            button = page.get_by_role("button", name=pattern, exact=True)
            if await button.is_visible(timeout=1000):
                await button.click(timeout=timeout)
                return True
            
            # Try partial text match
            button = page.get_by_role("button", name=pattern, exact=False)
            if await button.is_visible(timeout=1000):
                await button.click(timeout=timeout)
                return True
                
        except Exception:
            continue
    
    # Try fallback selector
    if fallback_selector:
        try:
            await page.click(fallback_selector, timeout=timeout)
            return True
        except Exception as e:
            print(f"⚠️ Fallback button click failed: {e}")
    
    print(f"⚠️ No button found matching patterns: {text_patterns}")
    return False


async def scroll_element_into_view(
    page: Page,
    selector_or_locator: Any,
    block: str = "center"
) -> bool:
    """
    Scroll element into view smoothly.
    
    Args:
        page: Playwright page
        selector_or_locator: CSS selector or Locator
        block: Scroll alignment ('start', 'center', 'end', 'nearest')
        
    Returns:
        True if successful
    """
    try:
        # Check if it's a string selector
        if isinstance(selector_or_locator, str):
            selector = selector_or_locator
            await page.evaluate(f"""
                document.querySelector('{selector}')?.scrollIntoView({{
                    behavior: 'smooth',
                    block: '{block}'
                }});
            """)
        else:
            # Assume it's a locator or element handle
            element = await selector_or_locator.element_handle()
            if element:
                await element.scroll_into_view_if_needed()
        
        await asyncio.sleep(0.5)
        return True
        
    except Exception as e:
        print(f"⚠️ Scroll into view failed: {e}")
        return False


async def dismiss_browser_dialogs(page: Page) -> bool:
    """
    Dismiss any browser dialogs (alerts, confirms, prompts).
    
    Args:
        page: Playwright page
        
    Returns:
        True if successful
    """
    try:
        # Set up dialog handler to auto-dismiss
        page.on("dialog", lambda dialog: asyncio.create_task(dialog.dismiss()))
        return True
    except Exception as e:
        print(f"⚠️ Dialog dismissal setup failed: {e}")
        return False


async def smart_wait_for_stable_dom(
    page: Page,
    selector: str,
    stability_ms: int = 500,
    timeout_ms: int = 10000
) -> bool:
    """
    Wait until a DOM element stops changing for a given duration.
    Polls element's outerHTML to detect stability.
    """
    start = asyncio.get_event_loop().time()
    last_html = None
    stable_since = None

    while True:
        try:
            html = await page.evaluate(
                """(sel) => {
                    const el = document.querySelector(sel);
                    return el ? el.outerHTML : null;
                }""",
                selector,
            )
        except Exception:
            html = None

        now = asyncio.get_event_loop().time()
        if html is None:
            stable_since = None
        elif html == last_html:
            if stable_since is None:
                stable_since = now
            elif (now - stable_since) * 1000 >= stability_ms:
                return True
        else:
            stable_since = None

        last_html = html
        if (now - start) * 1000 >= timeout_ms:
            return False
        await asyncio.sleep(0.2)


async def smart_wait_for_network_idle(
    page: Page,
    idle_ms: int = 500,
    timeout_ms: int = 10000
) -> bool:
    """
    Wait until no network requests have been initiated for idle_ms milliseconds.
    Uses Playwright's built-in wait_for_load_state('networkidle') if available.
    """
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout_ms)
        return True
    except Exception:
        return False
