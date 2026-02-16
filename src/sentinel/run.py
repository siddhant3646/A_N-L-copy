import asyncio
import random
import sys
import datetime
import os
from pathlib import Path

# Add workspace root to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from playwright.async_api import async_playwright

class Browser:
    def __init__(self, executable_path=None, headless=False, user_data_dir=None, **kwargs):
        self.executable_path = executable_path
        self.headless = headless
        self.user_data_dir = user_data_dir
        self.playwright = None
        self.context = None
        self.browser = None

    async def start(self):
        # Fix EPERM/Socket issues by forcing a unique system-standard TMPDIR
        import os
        import tempfile
        local_tmp = tempfile.mkdtemp(prefix="sentinel_")
        os.environ["TMPDIR"] = local_tmp
        print(f"🔧 Set TMPDIR to: {local_tmp}")

        self.playwright = await async_playwright().start()
        args = [
            '--no-sandbox',
            '--disable-blink-features=AutomationControlled',
            '--start-maximized',
            '--disable-session-crashed-bubble',
            '--no-restore-session-state',
            '--ignore-certificate-errors',  # Fixes ERR_SSL_VERSION_OR_CIPHER_MISMATCH on some sites
            '--ignore-ssl-errors'  # Additional SSL error suppression
        ]
        
        final_user_data_dir = self.user_data_dir
        
        final_user_data_dir = self.user_data_dir
        
        # Profile Seeding (Copying) Logic
        if self.user_data_dir:
            import shutil
            import os
            
            # Create a local profiles dir to minimize path length and avoid EPERM
            # Use a very short absolute path to avoid macOS socket length limits (104 chars)
            temp_dir = os.path.abspath(os.path.join(os.getcwd(), "p"))
            os.makedirs(temp_dir, exist_ok=True)
            
            # CLEANUP LOCKS in the destination to prevent ProcessSingleton errors
            import glob
            for pattern in ["Singleton*", "lock", ".parentlock"]:
                for stale_file in glob.glob(os.path.join(temp_dir, pattern)):
                    try:
                        if os.path.exists(stale_file):
                            os.unlink(stale_file)
                    except:
                        pass
            
            # FORCE FRESH COPY FROM SOURCE EVERY TIME
            # This ensures we pick up the latest login session from the seeded profile
            print(f"🔄 Refreshing profile copy at: {temp_dir}")
            
            # Source paths
            src_default = os.path.join(self.user_data_dir, "Default")
            dst_default = os.path.join(temp_dir, "Default")
            
            if os.path.exists(src_default):
                try:
                    # Remove existing copy if present
                    if os.path.exists(dst_default):
                         # Force delete, ignoring errors (like .DS_Store permissions)
                         shutil.rmtree(dst_default, ignore_errors=True)
                    
                    # Create destination (if rmtree failed to fully delete, this might be no-op or partial)
                    os.makedirs(dst_default, exist_ok=True)
                    print(f"  ⚡ Mirroring full profile (excluding Cache)...")
                    
                    # Use rsync-like logic or just shutil.copytree with ignore
                    def ignore_cache(path, names):
                        # Cache files and locks often cause EPERM/IO issues.
                        ignored_patterns = ['Cache', 'Code Cache', 'GPUCache', 'VideoDecodeStats', 'Crashpad', '.DS_Store', 'Singleton', 'lock', '.parentlock']
                        return [n for n in names if any(p in n for p in ignored_patterns)]
                    
                    shutil.copytree(src_default, dst_default, dirs_exist_ok=True, ignore=ignore_cache)
                    
                    # Also copy 'Local State' from root
                    local_state_src = os.path.join(self.user_data_dir, "Local State")
                    if os.path.exists(local_state_src):
                        shutil.copy2(local_state_src, os.path.join(temp_dir, "Local State"))
                        print("  📁 Copied: Local State")
                        
                    final_user_data_dir = temp_dir
                    print("✅ Profile refreshed successfully")
                except Exception as e:
                    print(f"❌ Profile Mirror Failure: {e}")
                    final_user_data_dir = self.user_data_dir
            else:
                 print(f"⚠️ Source profile not found at {src_default}")
                 final_user_data_dir = None

        else:
             # Force fresh profile if copying is disabled
             final_user_data_dir = None
             
        # FORCE CLEANUP OF crashpad settings if they exist in destination (fixes EPERM)
        # Actually this is hard because EPERM was on SOURCE. But let's leave it.
        
        if final_user_data_dir:
            print(f"🚀 Launching with User Data: {final_user_data_dir}")
            try:
                self.context = await self.playwright.chromium.launch_persistent_context(
                    user_data_dir=final_user_data_dir,
                    executable_path=self.executable_path,
                    headless=self.headless,
                    args=args,
                    ignore_default_args=["--use-mock-keychain", "--password-store=basic"],
                    viewport=None 
                )
            except Exception as e:
                print(f"⚠️ Failed to launch persistent context: {e}")
                print("🔄 Falling back to standard launch (WITHOUT profile)...")
                self.browser = await self.playwright.chromium.launch(
                    executable_path=self.executable_path,
                    headless=self.headless,
                    args=args
                )
                self.context = await self.browser.new_context()
        else:
             self.browser = await self.playwright.chromium.launch(
                executable_path=self.executable_path,
                headless=self.headless,
                args=args
             )
             self.context = await self.browser.new_context()

    async def get_current_page(self):
        if self.context and self.context.pages:
            return self.context.pages[0]
        return None
        
    async def new_page(self):
        if self.context:
            return await self.context.new_page()
        return None

    async def stop(self):
        # 1. Close all pages first
        if self.context:
            try:
                for page in self.context.pages:
                    await page.close()
            except Exception as e:
                print(f"⚠️ Error closing pages: {e}")

        # 2. Close context
        if self.context: 
            try:
                await self.context.close()
            except Exception as e:
                print(f"⚠️ Error closing context: {e}")

        # 3. Close browser
        if self.browser: 
            try:
                await self.browser.close()
            except Exception as e:
                print(f"⚠️ Error closing browser: {e}")

        # 4. Stop Playwright
        if self.playwright: 
            try:
                await self.playwright.stop()
            except Exception as e:
                print(f"⚠️ Error stopping Playwright: {e}")
from src.core.config import CHROME_USER_DATA, CHROME_EXECUTABLE_PATH
from src.sentinel.agent import create_agent
from src.sentinel import prompts

async def main():
    print(f"🛡️  SENTINEL REBORN - Infinite Loop Mode")
    
    # Define Tasks: (Task Name, Start URL, Prompt)
    tasks = [
        # Priority 1 & 2: Job Applications (LinkedIn first)
        ("LinkedIn Application", "https://www.linkedin.com/jobs/search-results/?f_AL=true&f_TPR=r18000&keywords=%22hiring%22%20AND%20(%22Java%22%20OR%20%22JAVA%20FULL%20STACK%22%20OR%20%22React.js%22%20OR%20%22Software%20Engineer%22)%20AND%20India&f_CS=F,G,H,I,J", prompts.LINKEDIN_JOB_APPLY_TASK),
        ("Naukri Application", "https://www.naukri.com/mnjuser/recommendedjobs", prompts.NAUKRI_JOB_APPLY_TASK),
        # Other tasks
        ("Instahyre Search", "https://www.instahyre.com/candidate/opportunities/?matching=true", prompts.INSTAHYRE_SEARCH_TASK),
        ("Naukri Employment LWD +31", "https://www.naukri.com/mnjuser/profile?id=&altresid", prompts.NAUKRI_EMPLOYMENT_LWD_31_TASK),
        ("Naukri Employment LWD +30", "https://www.naukri.com/mnjuser/profile?id=&altresid", prompts.NAUKRI_EMPLOYMENT_LWD_30_TASK),
        ("Naukri Profile Update", "https://www.naukri.com/mnjuser/profile?id=&altresid", prompts.NAUKRI_PROFILE_UPDATE_TASK),
        ("Naukri Early Access", "https://www.naukri.com/mnjuser/recommended-earjobs", prompts.NAUKRI_EARLY_ACCESS_TASK),
    ]
    
    cycle_count = 0
    linkedin_rate_limit_until = None  # Track rate limit at runner level
    naukri_rate_limit_until = None  # Track Naukri rate limit
    
    while True:  # INFINITE LOOP
        cycle_count += 1
        print(f"\n\n{'#'*60}")
        print(f"🔄 CYCLE {cycle_count} STARTED")
        print(f"{'#'*60}")
        
        for i, (task_name, start_url, task_prompt) in enumerate(tasks):
            # Check LinkedIn rate limit
            if task_name == "LinkedIn Application" and linkedin_rate_limit_until:
                if datetime.datetime.now() < linkedin_rate_limit_until:
                    remaining = (linkedin_rate_limit_until - datetime.datetime.now()).seconds // 60
                    print(f"\n⏸️  Skipping LinkedIn (Rate Limited) - {remaining} mins remaining")
                    continue
                else:
                    print(f"✅ LinkedIn rate limit expired, resuming...")
                    linkedin_rate_limit_until = None
            
            # Check Naukri rate limit
            if task_name == "Naukri Application" and naukri_rate_limit_until:
                if datetime.datetime.now() < naukri_rate_limit_until:
                    remaining = (naukri_rate_limit_until - datetime.datetime.now()).seconds // 60
                    print(f"\n⏸️  Skipping Naukri (Rate Limited) - {remaining} mins remaining")
                    continue
                else:
                    print(f"✅ Naukri rate limit expired, resuming...")
                    naukri_rate_limit_until = None
            
            print(f"\n\n{'='*50}")
            print(f"📜 [{cycle_count}] TASK {i+1}/{len(tasks)}: {task_name}")
            print(f"{'='*50}")
            
            # Init Browser for THIS task (Fresh instance)
            browser = Browser(
                executable_path=CHROME_EXECUTABLE_PATH,
                headless=False,
                disable_security=True,
                user_data_dir=CHROME_USER_DATA,
                keep_alive=True
            )
            
            # Create Agent for THIS task
            agent = create_agent()
            
            try:
                print("🌐 Launching Browser...")
                await browser.start()
                
                page = await browser.get_current_page()
                if not page:
                    page = await browser.new_page()
                    
                print(f"🔗 Navigating to {start_url}...")
                navigation_success = False
                for nav_attempt in range(3):
                    try:
                        await page.goto(start_url, wait_until='domcontentloaded', timeout=30000)
                        await asyncio.sleep(5)
                        try:
                            title = await page.title()
                            print(f"📄 [{title}] at {page.url}")
                        except:
                            pass
                        navigation_success = True
                        break
                    except Exception as e:
                        wait_time = 5 * (nav_attempt + 1)  # 5s, 10s, 15s
                        if nav_attempt < 2:
                            print(f"⚠️ Navigation error (attempt {nav_attempt + 1}/3): {e}")
                            print(f"   Retrying in {wait_time}s...")
                            await asyncio.sleep(wait_time)
                        else:
                            print(f"❌ Navigation failed after 3 attempts: {e}")
                
                if not navigation_success:
                    print(f"⏭️ Skipping task '{task_name}' due to navigation failure")
                    continue
                    
                agent._page = page
                agent.browser = browser
                
                print(f"▶️  Running Agent Task: {task_name}...")
                success = await agent.run(task_description=task_prompt)
                
                # Check if agent detected rate limit
                if hasattr(agent, 'linkedin_rate_limit_until') and agent.linkedin_rate_limit_until:
                    linkedin_rate_limit_until = agent.linkedin_rate_limit_until
                    print(f"⏸️  LinkedIn paused until {linkedin_rate_limit_until.strftime('%H:%M')}")
                
                # Check if agent detected Naukri rate limit
                if hasattr(agent, 'naukri_rate_limit_until') and agent.naukri_rate_limit_until:
                    naukri_rate_limit_until = agent.naukri_rate_limit_until
                    print(f"⏸️  Naukri paused until {naukri_rate_limit_until.strftime('%H:%M')}")
                
                if success:
                    print(f"\n🎉 Task '{task_name}' Completed Successfully!")
                else:
                    print(f"\n⚠️  Task '{task_name}' Incomplete.")
                    
            except KeyboardInterrupt:
                print("\n🛑 Stopped by User (Ctrl+C)")
                await browser.stop()
                return  # Exit the entire program
            except Exception as e:
                print(f"\n❌ Fatal Error in '{task_name}': {e}")
            finally:
                print(f"🔒 Closing Session for '{task_name}'...")
                await browser.stop()
                await asyncio.sleep(2)  # Cooldown between tasks
        
        # Cycle complete - run INTERSESSION task during wait period
        wait_mins = random.uniform(15, 20)  # Random 15-20 minutes total wait
        print(f"\n\n{'#'*60}")
        print(f"✅ CYCLE {cycle_count} COMPLETE - All {len(tasks)} tasks done!")
        print(f"⏳ INTERSESSION: Running Instahyre (20 jobs) during {wait_mins:.1f} min wait...")
        print(f"{'#'*60}")
        
        # Track intersession start time
        import time
        intersession_start = time.time()
        
        # Run Instahyre INTERSESSION task
        intersession_browser = Browser(
            executable_path=CHROME_EXECUTABLE_PATH,
            headless=False,
            disable_security=True,
            user_data_dir=CHROME_USER_DATA,
            keep_alive=True
        )
        intersession_agent = create_agent()
        
        try:
            print("🌐 [INTERSESSION] Launching Browser...")
            await intersession_browser.start()
            
            page = await intersession_browser.get_current_page()
            if not page:
                page = await intersession_browser.new_page()
                
            print("🔗 [INTERSESSION] Navigating to Instahyre...")
            await page.goto("https://www.instahyre.com/candidate/opportunities/?matching=true", 
                          wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(5)
            
            intersession_agent._page = page
            intersession_agent.browser = intersession_browser
            
            print("▶️  [INTERSESSION] Running Instahyre (20 jobs)...")
            await intersession_agent.run(task_description=prompts.INSTAHYRE_INTERSESSION_TASK)
            print("🎉 [INTERSESSION] Instahyre task completed!")
            
        except KeyboardInterrupt:
            print("\n🛑 Stopped by User (Ctrl+C)")
            await intersession_browser.stop()
            return
        except Exception as e:
            print(f"⚠️  [INTERSESSION] Error: {e}")
        finally:
            await intersession_browser.stop()
        
        # Wait for remaining time (if any)
        elapsed = time.time() - intersession_start
        remaining_wait = (wait_mins * 60) - elapsed
        if remaining_wait > 0:
            print(f"⏳ Waiting {remaining_wait/60:.1f} more minutes...")
            await asyncio.sleep(remaining_wait)
        else:
            print(f"⏩ Intersession took longer than wait time, starting next cycle immediately")
        
        print(f"\n🔄 Starting Cycle {cycle_count + 1}...")

if __name__ == "__main__":
    asyncio.run(main())
