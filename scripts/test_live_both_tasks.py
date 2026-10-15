import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright
from src.sentinel.agent import SentinelAgent

async def run_live_tests():
    print("=" * 60)
    print("🚀 LIVE TEST: HIRIST & INDEED APPLICATION TASKS")
    print("=" * 60)

    # Set application caps for live test: 1 application each to verify end-to-end
    os.environ['HIRIST_MAX_APPLICATIONS'] = '1'
    os.environ['INDEED_MAX_APPLICATIONS'] = '1'

    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    await browser.start()
    page = await browser.get_current_page() or await browser.new_page()

    agent = SentinelAgent()
    agent._page = page
    agent.browser = browser

    # ----------------------------------------------------
    # TEST 1: HIRIST TASK
    # ----------------------------------------------------
    print("\n" + "#" * 50)
    print("🟧 RUNNING HIRIST APPLY TASK")
    print("#" * 50)
    try:
        hirist_success = await agent._handle_hirist_apply_task()
        print(f"\nHirist Task Return: {hirist_success}")
        print(f"Hirist Submitted: {agent.metrics.get('applications_submitted', 0)}")
        print(f"Hirist Questions: {agent.metrics.get('questions_answered', 0)}")
    except Exception as e:
        print(f"❌ Hirist Task Error: {e}")
        import traceback
        traceback.print_exc()

    # Reset metrics for next task
    agent.reset_per_task_state()
    agent._page = page
    agent.browser = browser

    # ----------------------------------------------------
    # TEST 2: INDEED TASK
    # ----------------------------------------------------
    print("\n" + "#" * 50)
    print("🟦 RUNNING INDEED APPLY TASK")
    print("#" * 50)
    try:
        indeed_success = await agent._handle_indeed_apply_task()
        print(f"\nIndeed Task Return: {indeed_success}")
        print(f"Indeed Submitted: {agent.metrics.get('applications_submitted', 0)}")
        print(f"Indeed Questions: {agent.metrics.get('questions_answered', 0)}")
    except Exception as e:
        print(f"❌ Indeed Task Error: {e}")
        import traceback
        traceback.print_exc()

    print("\n🏁 LIVE TASKS TEST COMPLETE.")
    await browser.stop(fast=True)
    await reset_shared_playwright()

if __name__ == "__main__":
    asyncio.run(run_live_tests())
