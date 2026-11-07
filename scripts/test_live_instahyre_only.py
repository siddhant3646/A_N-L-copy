"""Run ONLY the real Instahyre opportunities apply handler (live end-to-end debugging).

Usage:
    python3 scripts/test_live_instahyre_only.py
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright
from src.sentinel.agent import SentinelAgent
from src.sentinel import prompts

OUTPUT_DIR = Path("live_test_output_instahyre")
SCREENSHOT_DIR = OUTPUT_DIR / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

INSTAHYRE_START_URL = "https://www.instahyre.com/candidate/opportunities/?matching=true"


async def capture_state(page, step_label: str):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_label = step_label.replace(" ", "_").replace("/", "_").replace(":", "_")[:50]
    shot_path = SCREENSHOT_DIR / f"{timestamp}_{safe_label}.png"
    try:
        await page.screenshot(path=str(shot_path), full_page=False)
        print(f"   📸 Screenshot captured: {shot_path.name}")
    except Exception as e:
        print(f"   ⚠️ Screenshot capture failed: {e}")


async def main():
    max_apps = os.environ.get("INSTAHYRE_MAX_APPLICATIONS", "2")
    os.environ["INSTAHYRE_MAX_APPLICATIONS"] = max_apps

    print("=" * 60)
    print("🚀 LIVE INSTAHYRE APPLICATION TASK TEST")
    print(f"   Target URL: {INSTAHYRE_START_URL}")
    print(f"   Max Applications Target: {max_apps}")
    print("=" * 60)

    browser = Browser(
        headless=False,
        user_data_dir=CHROME_USER_DATA,
    )

    agent = SentinelAgent()

    try:
        print("🌐 Launching Browser (Chrome)...")
        await browser.start()

        page = await browser.get_current_page()
        if not page:
            page = await browser.new_page()

        print(f"🔗 Navigating to Instahyre: {INSTAHYRE_START_URL}...")
        await page.goto(INSTAHYRE_START_URL, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(5)

        try:
            title = await page.title()
            print(f"📄 Page Title: [{title}] at {page.url}")
        except Exception:
            pass

        await capture_state(page, "initial_load")

        agent._page = page
        agent.browser = browser

        # Diagnostic: listen to console
        page.on("console", lambda msg: print(f"   🖥️ BROWSER CONSOLE: {msg.text}"))

        print("▶️ Running Agent Task: Instahyre Search / Opportunities...")
        success = await agent.run(task_description=prompts.INSTAHYRE_SEARCH_TASK)

        await capture_state(page, "final_state")

        print("=" * 60)
        print(f"📊 LIVE INSTAHYRE TEST RESULTS:")
        print(f"   Success:               {success}")
        print(f"   Submitted Apps:        {agent.metrics.get('applications_submitted', 0)}")
        print(f"   Questions Answered:    {agent.metrics.get('questions_answered', 0)}")
        print(f"   Errors Encountered:    {agent.metrics.get('errors_encountered', 0)}")
        print("=" * 60)

    except Exception as e:
        print(f"❌ Error during live Instahyre test: {e}")
        import traceback
        traceback.print_exc()
        if agent._page:
            await capture_state(agent._page, "error_state")
    finally:
        print("🔒 Closing browser...")
        try:
            await browser.stop(fast=True)
        except Exception:
            pass
        await reset_shared_playwright()
        print("🏁 Test run finished.")


if __name__ == "__main__":
    asyncio.run(main())
