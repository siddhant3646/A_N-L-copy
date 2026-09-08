import asyncio
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright, stop_shared_playwright, cleanup_tmp_root
from src.sentinel.agent import SentinelAgent
from src.sentinel import prompts

OUTPUT_DIR = Path("live_test_output")
SCREENSHOT_DIR = OUTPUT_DIR / "screenshots"
DOM_DIR = OUTPUT_DIR / "dom"

SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
DOM_DIR.mkdir(parents=True, exist_ok=True)

LINKEDIN_START_URL = "https://www.linkedin.com/jobs/search-results/?currentJobId=4325424519&keywords=%22hiring%22%20AND%20%28%22Java%22%20OR%20%22JAVA%20FULL%20STACK%22%20OR%20%22React.js%22%20OR%20%22Software%20Engineer%22%29%20AND%20India&origin=JOB_SEARCH_PAGE_JOB_FILTER&referralSearchId=Qwth1ndwtouG0vtFGj%2Bpsg%3D%3D&geoId=102713980&distance=0.0&f_TPR=r86400&f_AL=true"

async def capture_state(page, step_label: str):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe_label = step_label.replace(" ", "_").replace("/", "_").replace(":", "_")
    
    shot_path = SCREENSHOT_DIR / f"{timestamp}_{safe_label}.png"
    dom_path = DOM_DIR / f"{timestamp}_{safe_label}.html"
    
    try:
        await page.screenshot(path=str(shot_path), full_page=False)
        print(f"   📸 Screenshot captured: {shot_path.name}")
    except Exception as e:
        print(f"   ⚠️ Screenshot capture failed: {e}")
        
    try:
        dom_content = await page.content()
        with open(dom_path, "w", encoding="utf-8") as f:
            f.write(dom_content)
        print(f"   📄 DOM captured: {dom_path.name} ({len(dom_content)} bytes)")
    except Exception as e:
        print(f"   ⚠️ DOM capture failed: {e}")

async def main():
    print("🚀 Starting Live LinkedIn Test with Screen & DOM Capture...")
    
    browser = Browser(
        headless=False,
        user_data_dir=CHROME_USER_DATA,
    )
    
    agent = SentinelAgent()
    
    # Wrap agent's step logging to capture screenshots and DOM
    orig_handle_fallback = agent._handle_scripted_fallback
    step_num = 0
    
    async def wrapped_handle_fallback():
        nonlocal step_num
        step_num += 1
        res = await orig_handle_fallback()
        if agent._page:
            await capture_state(agent._page, f"step_{step_num}_{res[:30]}")
        return res
        
    agent._handle_scripted_fallback = wrapped_handle_fallback
    
    try:
        print("🌐 Launching Browser (Chrome)...")
        await browser.start()
        
        page = await browser.get_current_page()
        if not page:
            page = await browser.new_page()
            
        print(f"🔗 Navigating to LinkedIn Search: {LINKEDIN_START_URL}...")
        await page.goto(LINKEDIN_START_URL, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(5)
        
        await capture_state(page, "initial_search_loaded")
        
        agent._page = page
        agent.browser = browser
        
        print("▶️ Running LinkedIn Job Apply Task...")
        success = await agent.run(task_description=prompts.LINKEDIN_JOB_APPLY_TASK)
        
        await capture_state(page, "final_state")
        
        print(f"\n📊 Final Results: Success={success}, Apps Submitted={agent.metrics['applications_submitted']}, Q&A={agent.metrics['questions_answered']}")
        
    except Exception as e:
        print(f"❌ Error during live test: {e}")
        import traceback
        traceback.print_exc()
        if agent._page:
            await capture_state(agent._page, "error_state")
    finally:
        print("🔒 Closing browser...")
        await browser.stop(fast=False)
        await stop_shared_playwright()
        cleanup_tmp_root()
        print("🏁 Live test finished.")

if __name__ == "__main__":
    asyncio.run(main())
