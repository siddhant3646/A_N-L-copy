"""Run ONLY the real Indeed apply handler (used for live end-to-end debugging).

Environment:
  INDEED_SEARCH_URL       seed search override
  INDEED_MAX_APPLICATIONS hard cap (default 1)
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright
from src.sentinel.agent import SentinelAgent


async def main():
    os.environ.setdefault("INDEED_MAX_APPLICATIONS", "1")

    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    await browser.start()
    page = await browser.get_current_page() or await browser.new_page()

    agent = SentinelAgent()
    agent._page = page
    agent.browser = browser

    print("=" * 60)
    print("🟦 LIVE INDEED-ONLY TEST")
    print("   seed :", os.environ.get("INDEED_SEARCH_URL", "<handler default>"))
    print("   cap  :", os.environ.get("INDEED_MAX_APPLICATIONS"))
    print("=" * 60)

    try:
        ok = await agent._handle_indeed_apply_task()
        print(f"\nIndeed Task Return: {ok}")
        print(f"Applications Submitted: {agent.metrics.get('applications_submitted', 0)}")
        print(f"Questions Answered: {agent.metrics.get('questions_answered', 0)}")
    except Exception as e:
        print(f"❌ Indeed Task Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            await browser.stop(fast=True)
        except Exception:
            pass
        await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
