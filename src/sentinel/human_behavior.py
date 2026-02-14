"""
Human Behavior Module - Simulate human-like mouse and keyboard interactions.

This module provides functions to simulate realistic human behavior including
mouse movements, scrolling, and clicking with natural delays and patterns.
"""

import asyncio
import random
from typing import Optional, Tuple
from playwright.async_api import Page


async def human_mouse_move(
    page: Page,
    target_x: int,
    target_y: int,
    duration: Optional[float] = None
) -> bool:
    """
    Move mouse to target coordinates with human-like motion.
    
    Args:
        page: Playwright page object
        target_x: Target X coordinate
        target_y: Target Y coordinate
        duration: Optional duration for movement (seconds)
        
    Returns:
        True if successful
    """
    try:
        # Get current mouse position
        current_pos = await page.evaluate("""
            () => {
                return { x: window.lastMouseX || 0, y: window.lastMouseY || 0 };
            }
        """)
        
        start_x = current_pos.get('x', 0)
        start_y = current_pos.get('y', 0)
        
        # Calculate steps for smooth movement
        distance = ((target_x - start_x) ** 2 + (target_y - start_y) ** 2) ** 0.5
        steps = max(10, int(distance / 10))
        
        if duration is None:
            duration = random.uniform(0.2, 0.5)
        
        step_delay = duration / steps
        
        for i in range(steps + 1):
            # Add slight curve to movement (bezier-like)
            t = i / steps
            offset_x = random.randint(-2, 2)
            offset_y = random.randint(-2, 2)
            
            x = int(start_x + (target_x - start_x) * t + offset_x)
            y = int(start_y + (target_y - start_y) * t + offset_y)
            
            await page.mouse.move(x, y)
            await asyncio.sleep(step_delay)
        
        # Final position
        await page.mouse.move(target_x, target_y)
        
        # Update tracking
        await page.evaluate(f"""
            window.lastMouseX = {target_x};
            window.lastMouseY = {target_y};
        """)
        
        return True
    except Exception as e:
        print(f"⚠️ Mouse movement failed: {e}")
        return False


async def human_scroll(
    page: Page,
    direction: str = "down",
    amount: Optional[int] = None,
    smooth: bool = True
) -> bool:
    """
    Scroll the page with human-like behavior.
    
    Args:
        page: Playwright page object
        direction: 'up' or 'down'
        amount: Scroll amount in pixels (random if None)
        smooth: Whether to scroll smoothly in steps
        
    Returns:
        True if successful
    """
    try:
        if amount is None:
            amount = random.randint(300, 800)
        
        if direction == "up":
            amount = -amount
        
        if smooth:
            # Scroll in steps with random delays
            steps = random.randint(3, 6)
            step_amount = amount // steps
            
            for _ in range(steps):
                await page.evaluate(f"window.scrollBy(0, {step_amount})")
                await asyncio.sleep(random.uniform(0.1, 0.3))
        else:
            await page.evaluate(f"window.scrollBy(0, {amount})")
        
        # Small pause after scrolling
        await asyncio.sleep(random.uniform(0.2, 0.5))
        
        return True
    except Exception as e:
        print(f"⚠️ Scroll failed: {e}")
        return False


async def human_click(
    page: Page,
    selector: Optional[str] = None,
    x: Optional[int] = None,
    y: Optional[int] = None,
    double_click: bool = False
) -> bool:
    """
    Click on an element or coordinates with human-like behavior.
    
    Args:
        page: Playwright page object
        selector: CSS selector of element to click
        x: X coordinate to click (if no selector)
        y: Y coordinate to click (if no selector)
        double_click: Whether to double-click
        
    Returns:
        True if successful
    """
    try:
        # Small random delay before clicking
        await asyncio.sleep(random.uniform(0.1, 0.3))
        
        if selector:
            element = await page.query_selector(selector)
            if not element:
                print(f"⚠️ Element not found: {selector}")
                return False
            
            # Get element position
            box = await element.bounding_box()
            if not box:
                print(f"⚠️ Cannot get bounding box for: {selector}")
                return False
            
            # Click within element with slight random offset
            x = int(box['x'] + box['width'] / 2 + random.randint(-5, 5))
            y = int(box['y'] + box['height'] / 2 + random.randint(-5, 5))
        
        if x is None or y is None:
            print("⚠️ No position specified for click")
            return False
        
        # Move mouse to position
        await human_mouse_move(page, x, y)
        
        # Small pause at position
        await asyncio.sleep(random.uniform(0.05, 0.15))
        
        # Perform click
        if double_click:
            await page.mouse.dblclick(x, y)
        else:
            await page.mouse.click(x, y)
        
        # Small pause after click
        await asyncio.sleep(random.uniform(0.1, 0.3))
        
        return True
    except Exception as e:
        print(f"⚠️ Click failed: {e}")
        return False


async def human_type(
    page: Page,
    selector: str,
    text: str,
    clear_first: bool = True,
    typo_chance: float = 0.02
) -> bool:
    """
    Type text into an input field with human-like behavior.
    
    Args:
        page: Playwright page object
        selector: CSS selector of input field
        text: Text to type
        clear_first: Whether to clear field first
        typo_chance: Chance of making a typo (0-1)
        
    Returns:
        True if successful
    """
    try:
        element = await page.query_selector(selector)
        if not element:
            print(f"⚠️ Input field not found: {selector}")
            return False
        
        # Click on field first
        await element.click()
        await asyncio.sleep(random.uniform(0.1, 0.3))
        
        # Clear field if requested
        if clear_first:
            await element.fill("")
            await asyncio.sleep(random.uniform(0.1, 0.2))
        
        # Type text with random delays
        for char in text:
            # Random typo
            if random.random() < typo_chance and char.isalpha():
                # Type wrong character
                wrong_char = random.choice('abcdefghijklmnopqrstuvwxyz')
                await element.type(wrong_char, delay=random.uniform(50, 150))
                await asyncio.sleep(random.uniform(0.1, 0.2))
                # Backspace
                await element.press('Backspace')
                await asyncio.sleep(random.uniform(0.05, 0.1))
            
            # Type correct character
            await element.type(char, delay=random.uniform(50, 150))
            
            # Random pause between characters
            if random.random() < 0.1:  # 10% chance
                await asyncio.sleep(random.uniform(0.1, 0.3))
        
        # Small pause after typing
        await asyncio.sleep(random.uniform(0.2, 0.5))
        
        return True
    except Exception as e:
        print(f"⚠️ Typing failed: {e}")
        return False


async def random_delay(
    min_seconds: float = 1.0,
    max_seconds: float = 3.0
) -> None:
    """
    Wait for a random duration to simulate human thinking time.
    
    Args:
        min_seconds: Minimum delay
        max_seconds: Maximum delay
    """
    delay = random.uniform(min_seconds, max_seconds)
    await asyncio.sleep(delay)


async def human_hover(
    page: Page,
    selector: str,
    duration: Optional[float] = None
) -> bool:
    """
    Hover over an element with human-like behavior.
    
    Args:
        page: Playwright page object
        selector: CSS selector of element
        duration: How long to hover (random if None)
        
    Returns:
        True if successful
    """
    try:
        element = await page.query_selector(selector)
        if not element:
            return False
        
        box = await element.bounding_box()
        if not box:
            return False
        
        x = int(box['x'] + box['width'] / 2)
        y = int(box['y'] + box['height'] / 2)
        
        await human_mouse_move(page, x, y)
        
        if duration is None:
            duration = random.uniform(0.5, 2.0)
        
        await asyncio.sleep(duration)
        
        return True
    except Exception as e:
        print(f"⚠️ Hover failed: {e}")
        return False
