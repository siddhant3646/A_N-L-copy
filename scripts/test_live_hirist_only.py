"""Run ONLY the real Hirist apply handler (used for live end-to-end debugging).

Environment:
  HIRIST_FEED_URL          seed feed override (default https://www.hirist.tech/jobfeed)
  HIRIST_MAX_APPLICATIONS  hard cap on apply ATTEMPTS (default 1)

Usage:
    HIRIST_MAX_APPLICATIONS=1 .venv/bin/python -u scripts/test_live_hirist_only.py
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright
from src.sentinel.agent import SentinelAgent


async def main():
    os.environ.setdefault("HIRIST_MAX_APPLICATIONS", "1")

    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    await browser.start()
    page = await browser.get_current_page() or await browser.new_page()

    agent = SentinelAgent()
    agent._page = page
    agent.browser = browser

    print("=" * 60)
    print("🟧 LIVE HIRIST-ONLY TEST")
    print("   feed:", os.environ.get("HIRIST_FEED_URL", "<handler default>"))
    print("   cap :", os.environ.get("HIRIST_MAX_APPLICATIONS"))
    print("=" * 60)

    try:
        success = await agent._handle_hirist_apply_task()
        print(f"\nHirist Task Return: {success}")
        print(f"Hirist Submitted:   {agent.metrics.get('applications_submitted', 0)}")
        print(f"Hirist Questions:   {agent.metrics.get('questions_answered', 0)}")
    except Exception as e:
        print(f"❌ Hirist Task Error: {e}")
        import traceback
        traceback.print_exc()

    print("\n🏁 LIVE HIRIST TEST COMPLETE.")
    await browser.stop(fast=True)
    await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())