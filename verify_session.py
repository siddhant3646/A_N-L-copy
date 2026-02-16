import asyncio
import os
import sys
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent))

from src.sentinel.run import Browser
from src.core.config import CHROME_USER_DATA, CHROME_EXECUTABLE_PATH

async def verify():
    print(f"🔍 Starting Session Verification...")
    
    browser = Browser(
        executable_path=CHROME_EXECUTABLE_PATH,
        headless=False,
        user_data_dir=CHROME_USER_DATA
    )
    
    try:
        await browser.start()
        page = await browser.get_current_page()
        if not page:
            page = await browser.new_page()
            
        url = "https://www.linkedin.com/jobs/search-results/?f_AL=true&f_TPR=r18000&keywords=%22hiring%22%20AND%20(%22Java%22%20OR%20%22JAVA%20FULL%20STACK%22%20OR%20%22React.js%22%20OR%20%22Software%20Engineer%22)%20AND%20India&f_CS=F,G,H,I,J"
        print(f"🔗 Navigating to {url}...")
        await page.goto(url, wait_until='domcontentloaded', timeout=60000)
        await asyncio.sleep(5)
        
        # Check login status using the same indicators as agent.py
        is_logged_in = await page.evaluate("""() => {
            return !!(
                document.querySelector('.global-nav__me-photo') || 
                document.querySelector('#ember14') || 
                document.querySelector('.feed-identity-module') ||
                document.querySelector('.global-nav__secondary-items') ||
                !document.querySelector('.nav__cta-container')
            );
        }""")
        
        title = await page.title()
        print(f"📄 Page Title: {title}")
        print(f"✅ Login Status: {'LOGGED IN' if is_logged_in else 'GUEST VIEW'}")
        
        if not is_logged_in:
            print("❌ Verification FAILED: Still in Guest View.")
        else:
            print("🎉 Verification SUCCESS: Session persistent!")
            
    except Exception as e:
        print(f"❌ Error during verification: {e}")
    finally:
        print("🔒 Stopping browser...")
        await browser.stop()

if __name__ == "__main__":
    asyncio.run(verify())
