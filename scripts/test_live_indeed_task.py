import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright
from src.sentinel.agent import SentinelAgent

async def test_indeed():
    print("=" * 60)
    print("🚀 LIVE TEST: INDEED TASK")
    print("=" * 60)

    os.environ['INDEED_MAX_APPLICATIONS'] = '1'

    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    await browser.start()
    page = await browser.get_current_page() or await browser.new_page()

    agent = SentinelAgent()
    agent._page = page
    agent.browser = browser

    success = await agent._handle_indeed_apply_task()
    print(f"\nIndeed Task Finished: Success = {success}")
    print(f"Applications submitted: {agent.metrics.get('applications_submitted', 0)}")
    print(f"Questions answered: {agent.metrics.get('questions_answered', 0)}")

    await browser.stop(fast=True)
    await reset_shared_playwright()

if __name__ == "__main__":
    asyncio.run(test_indeed())
