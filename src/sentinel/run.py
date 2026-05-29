import asyncio
import random
import sys
import datetime
import os
from pathlib import Path

# Add workspace root to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from playwright.async_api import async_playwright

_browser_counter = 0
_shared_playwright = None

async def get_shared_playwright():
    global _shared_playwright
    if _shared_playwright is None:
        _shared_playwright = await async_playwright().start()
        print("🔧 Shared Playwright instance started")
    return _shared_playwright

async def reset_shared_playwright():
    """Tear down and recreate the Playwright singleton.
    
    Called before a launch retry when the shared pipe may have gone stale
    (symptom: Chrome exits immediately with exitCode=0).
    """
    global _shared_playwright
    if _shared_playwright is not None:
        try:
            await _shared_playwright.stop()
        except Exception:
            pass
        _shared_playwright = None
    _shared_playwright = await async_playwright().start()
    print("🔧 Playwright singleton reset (fresh pipe)")
    return _shared_playwright

async def stop_shared_playwright():
    global _shared_playwright
    if _shared_playwright is not None:
        try:
            await _shared_playwright.stop()
        except Exception as e:
            print(f"⚠️ Error stopping shared Playwright: {e}")
        _shared_playwright = None
        print("🔧 Shared Playwright instance stopped")

class Browser:
    def __init__(self, executable_path=None, headless=False, user_data_dir=None, **kwargs):
        global _browser_counter
        _browser_counter += 1
        self._task_id = _browser_counter
        self.executable_path = executable_path
        self.headless = headless
        self.user_data_dir = user_data_dir
        self.playwright = None
        self.context = None
        self.browser = None

    # Resource types to block for noise reduction
    BLOCKED_RESOURCE_TYPES = [
        'image', 'stylesheet', 'font', 'media', 'other'
    ]
    
    # URL patterns to block (tracking, analytics, ads)
    BLOCKED_URL_PATTERNS = [
        'ads.linkedin.com',
        'analytics',
        'tracking',
        'doubleclick',
        'google-analytics',
        'facebook.com/tr',
        'googleadservices',
        'googletagmanager',
        'hotjar',
        'segment.io',
        'mixpanel',
        'amplitude',
        'sentry.io',
        '*.gif',
        '*.png',
        '*.jpg',
        '*.jpeg',
        '*.svg',
        '*.woff',
        '*.woff2',
        '*.ttf',
        '*.eot',
        '*.css',
    ]
    
    async def start(self):
        import os
        import tempfile
        
        local_tmp = tempfile.mkdtemp(prefix="sentinel_")
        os.environ["TMPDIR"] = local_tmp
        print(f"🔧 Set TMPDIR to: {local_tmp}")

        self.playwright = await get_shared_playwright()
        
        self.executable_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        
        args = [
            '--disable-blink-features=AutomationControlled',
            '--start-maximized',
            '--disable-session-crashed-bubble',
            '--no-restore-session-state',
            '--ignore-certificate-errors',
            '--ignore-ssl-errors',
            '--disable-gpu',
            '--disable-extensions',
            '--no-first-run',
        ]
        
        final_user_data_dir = self.user_data_dir
        
        if self.user_data_dir:
            import shutil
            import glob
            
            temp_dir = os.path.join(tempfile.gettempdir(), f"sentinel_profile_{os.getpid()}_{self._task_id}")
            self._temp_dir = temp_dir
            os.makedirs(temp_dir, exist_ok=True)
            
            def clean_lock_files(base_dir):
                for sub in ["", "Default"]:
                    target = os.path.join(base_dir, sub)
                    for pattern in ["Singleton*", "lock", ".parentlock"]:
                        for stale_file in glob.glob(os.path.join(target, pattern)):
                            try:
                                if os.path.exists(stale_file):
                                    os.unlink(stale_file)
                            except:
                                pass
            
            clean_lock_files(temp_dir)
            
            print(f"🔄 Refreshing profile copy at: {temp_dir}")
            
            src_default = os.path.join(self.user_data_dir, "Default")
            dst_default = os.path.join(temp_dir, "Default")
            
            if os.path.exists(src_default):
                try:
                    # Don't try to delete — macOS locks some files. Just overwrite with dirs_exist_ok
                    if not os.path.exists(dst_default):
                        os.makedirs(dst_default, exist_ok=True)
                    print(f"  ⚡ Mirroring full profile (excluding Cache)...")
                    
                    def ignore_cache(path, names):
                        ignored_patterns = ['Cache', 'Code Cache', 'GPUCache', 'VideoDecodeStats', 'Crashpad', '.DS_Store', 'Singleton', 'lock', '.parentlock']
                        return [n for n in names if any(p in n for p in ignored_patterns)]
                    
                    try:
                        shutil.copytree(src_default, dst_default, dirs_exist_ok=True, ignore=ignore_cache)
                    except Exception as copy_err:
                        print(f"  ⚠️ Copytree error (using existing profile): {copy_err}")
                        # Profile copy dir exists with prior data — reuse it as-is
                    
                    local_state_src = os.path.join(self.user_data_dir, "Local State")
                    if os.path.exists(local_state_src):
                        shutil.copy2(local_state_src, os.path.join(temp_dir, "Local State"))
                        print("  📁 Copied: Local State")
                    
                    clean_lock_files(temp_dir)
                    
                    final_user_data_dir = temp_dir
                    print("✅ Profile refreshed successfully")
                except Exception as e:
                    print(f"❌ Profile Mirror Failure: {e}")
                    final_user_data_dir = self.user_data_dir
            else:
                print(f"⚠️ Source profile not found at {src_default}")
                final_user_data_dir = None
        else:
            final_user_data_dir = None
            
        if final_user_data_dir:
            print(f"🚀 Launching with User Data: {final_user_data_dir}")

            async def _attempt_launch():
                """Single launch attempt: kill ALL sentinel Chrome procs, clean locks, then launch."""
                # Kill any Chrome still running from a PREVIOUS task (different temp dir
                # but same PID marker) — macOS holds GPU/display handles even after
                # context.close(), causing 'Browser window not found' for the next launch.
                self._kill_all_sentinel_chrome()
                await asyncio.sleep(4)  # Let macOS release GPU/display resources
                clean_lock_files(final_user_data_dir)
                return await self.playwright.chromium.launch_persistent_context(
                    user_data_dir=final_user_data_dir,
                    executable_path=self.executable_path,
                    headless=self.headless,
                    args=args,
                    ignore_default_args=["--use-mock-keychain", "--password-store=basic", "--enable-unsafe-swiftshader"],
                    viewport=None,
                    handle_sigterm=False,
                    handle_sigint=False,
                )

            try:
                self.context = await _attempt_launch()
            except Exception as e:
                print(f"⚠️ Failed to launch persistent context with Chrome: {e}")
                print("🔄 Retry 1/3: killing stale Chrome, resetting Playwright pipe...")
                await asyncio.sleep(8)
                self.playwright = await reset_shared_playwright()
                try:
                    self.context = await _attempt_launch()
                    print("✅ Retry 1 succeeded with Chrome persistent context!")
                except Exception as e2:
                    print(f"⚠️ Retry 1 failed: {e2}")
                    print("🔄 Retry 2/3: waiting 15s, force-killing Chrome, full Playwright reset...")
                    await asyncio.sleep(15)
                    self.playwright = await reset_shared_playwright()
                    try:
                        self.context = await _attempt_launch()
                        print("✅ Retry 2 succeeded with Chrome persistent context!")
                    except Exception as e3:
                        print(f"⚠️ Retry 2 failed: {e3}")
                        print("🔄 Retry 3/3: waiting 25s, full reset...")
                        await asyncio.sleep(25)
                        self.playwright = await reset_shared_playwright()
                        try:
                            self.context = await _attempt_launch()
                            print("✅ Retry 3 succeeded with Chrome persistent context!")
                        except Exception as e4:
                            raise RuntimeError(
                                f"Chrome persistent context failed after 3 retries. Error: {e4}"
                            )
        else:
            self.browser = await self.playwright.chromium.launch(
                executable_path=self.executable_path,
                headless=self.headless,
                args=args,
                ignore_default_args=["--enable-unsafe-swiftshader"]
            )
            self.context = await self.browser.new_context()

    async def get_current_page(self):
        if self.context and self.context.pages:
            return self.context.pages[0]
        return None
        
    async def new_page(self):
        if self.context:
            page = await self.context.new_page()
            # Apply resource blocking to reduce console noise
            await self._setup_resource_blocking(page)
            return page
        return None
    
    async def _setup_resource_blocking(self, page):
        """Setup resource blocking to reduce console noise and improve performance."""
        async def handle_route(route, request):
            # Check if resource type should be blocked
            if request.resource_type in self.BLOCKED_RESOURCE_TYPES:
                await route.abort()
                return
            
            # Check if URL matches blocked patterns
            url = request.url.lower()
            for pattern in self.BLOCKED_URL_PATTERNS:
                pattern_lower = pattern.lower()
                if pattern_lower.startswith('*.'):
                    # Handle wildcard patterns like *.png
                    suffix = pattern_lower[1:]  # Remove the *
                    if url.endswith(suffix):
                        await route.abort()
                        return
                elif pattern_lower in url:
                    await route.abort()
                    return
            
            # Allow the request
            await route.continue_()
        
        # Apply the route handler to all requests
        await page.route("**/*", handle_route)
        print("   🔇 Resource blocking enabled (images, stylesheets, fonts, trackers)")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _kill_pids(pids: list, label: str, timeout: float = 5.0) -> None:
        """SIGTERM then SIGKILL a list of PIDs."""
        import signal, time, subprocess as sp
        if not pids:
            return
        print(f"   🔪 Killing {len(pids)} Chrome process(es): {label}")
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + timeout / 2
        while time.monotonic() < deadline:
            time.sleep(0.2)
            still = [p for p in pids if sp.run(
                ['kill', '-0', str(p)], capture_output=True
            ).returncode == 0]
            if not still:
                return
            pids = still
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
                print(f"   💀 SIGKILL sent to pid {pid}")
            except ProcessLookupError:
                pass

    @staticmethod
    def _kill_chrome_holding_dir(path: str, timeout: float = 5.0) -> None:
        """Forcibly terminate any Chrome process whose cmdline contains *path*."""
        import subprocess
        if not path:
            return
        try:
            result = subprocess.run(['pgrep', '-f', path], capture_output=True, text=True)
            pids = [int(p) for p in result.stdout.split() if p.strip().isdigit()]
            if pids:
                Browser._kill_pids(pids, path, timeout)
        except Exception as e:
            print(f"   ⚠️ _kill_chrome_holding_dir error: {e}")

    @staticmethod
    def _kill_all_sentinel_chrome(timeout: float = 5.0) -> None:
        """Kill ALL Chrome processes spawned by this Python process.

        Searches for any Chrome whose cmdline contains 'sentinel_profile_<our_pid>'.
        This catches Chrome from ANY task (not just the current temp dir), which is
        critical because macOS holds GPU/display handles across profile directories.
        """
        import subprocess
        marker = f"sentinel_profile_{os.getpid()}"
        try:
            result = subprocess.run(['pgrep', '-f', marker], capture_output=True, text=True)
            pids = [int(p) for p in result.stdout.split() if p.strip().isdigit()]
            if pids:
                Browser._kill_pids(pids, f"all sentinel ({marker})", timeout)
        except Exception as e:
            print(f"   ⚠️ _kill_all_sentinel_chrome error: {e}")

        # Also kill any lingering Chrome automation processes from previous runs
        # that may hold GPU/display handles even though they don't match our marker.
        try:
            result = subprocess.run(
                ['pgrep', '-f', 'Google Chrome.*--enable-automation'],
                capture_output=True, text=True
            )
            pids = [int(p) for p in result.stdout.split() if p.strip().isdigit()]
            if pids:
                Browser._kill_pids(pids, "stale automation Chrome", timeout)
        except Exception:
            pass

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

        # 4. Do NOT stop Playwright here — it's a shared singleton managed separately
        
        # 5. Wait for Chrome processes with our temp profile to fully exit
        import subprocess
        profile_marker = f"sentinel_profile_{os.getpid()}"
        for attempt in range(20):
            try:
                result = subprocess.run(
                    ['pgrep', '-f', profile_marker],
                    capture_output=True, text=True
                )
                if not result.stdout.strip():
                    if attempt > 0:
                        print(f"   ⏳ Chrome fully exited after {attempt * 0.5:.1f}s")
                    break
                await asyncio.sleep(0.5)
            except:
                await asyncio.sleep(0.5)
                break
        else:
            # Processes didn't exit cleanly — forcibly kill them so the next
            # task's launch_persistent_context is not blocked by a profile lock.
            print(f"⚠️ Chrome still alive after 10s — force-killing...")
            temp_dir = getattr(self, '_temp_dir', None)
            if temp_dir:
                self._kill_chrome_holding_dir(temp_dir)
            else:
                self._kill_chrome_holding_dir(profile_marker)
from src.core.config import CHROME_USER_DATA, CHROME_EXECUTABLE_PATH
from src.sentinel.agent import create_agent
from src.sentinel import prompts

async def main():
    print(f"🛡️  SENTINEL REBORN - Infinite Loop Mode")
    
    # Define Tasks: (Task Name, Start URL, Prompt)
    tasks = [
        # Priority 1 & 2: Job Applications (Naukri first)
        ("Naukri Application", "https://www.naukri.com/mnjuser/recommendedjobs", prompts.NAUKRI_JOB_APPLY_TASK),
        ("LinkedIn Application", "https://www.linkedin.com/jobs/search-results/?f_AL=true&f_TPR=r18000&keywords=%22hiring%22%20AND%20(%22Java%22%20OR%20%22JAVA%20FULL%20STACK%22%20OR%20%22React.js%22%20OR%20%22Software%20Engineer%22)%20AND%20India&f_CS=F,G,H,I,J", prompts.LINKEDIN_JOB_APPLY_TASK),
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
    
    async def _warmup_playwright_pipe():
        """Launch and immediately close a disposable NON-persistent Chrome to
        warm up the Playwright→Chrome connection on macOS. Using browser.launch()
        (not launch_persistent_context) exercises a different internal code path
        that is immune to the --remote-debugging-pipe race condition."""
        import subprocess
        pw = await get_shared_playwright()
        args = [
            '--disable-blink-features=AutomationControlled',
            '--disable-gpu', '--disable-extensions', '--no-first-run',
            '--start-maximized', '--ignore-certificate-errors',
        ]
        try:
            br = await pw.chromium.launch(
                executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                headless=False, args=args,
                ignore_default_args=["--enable-unsafe-swiftshader"],
            )
            await br.close()
            print("🔥 Playwright warm-up complete (non-persistent)")
        except Exception:
            await reset_shared_playwright()
            print("🔥 Playwright warm-up done (reset)")
        # Kill any Chrome that may linger after warm-up
        try:
            subprocess.run(['pkill', '-f', 'Google Chrome.*--enable-automation'],
                           capture_output=True, timeout=5)
        except Exception:
            pass
        await asyncio.sleep(3)
    
    print("🔥 Warming up Playwright pipe...")
    await _warmup_playwright_pipe()
    
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
                headless=False,
                user_data_dir=CHROME_USER_DATA,
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
                await stop_shared_playwright()
                return  # Exit the entire program
            except RuntimeError as e:
                # Browser launch failures (profile locked, Playwright pipe stale, etc.)
                # are recoverable — just skip this task and move on to the next one.
                print(f"\n⚠️  Browser launch failed for '{task_name}': {e}")
                print("   ⏭️  Skipping task and continuing to next...")
            except Exception as e:
                print(f"\n❌ Unexpected error in '{task_name}': {e}")
                import traceback
                traceback.print_exc()
                # Don't stop Playwright — let subsequent tasks attempt with the same instance.
                # Only pause briefly so we don't spin-loop on a persistent error.
                print("   ⏳ Pausing 60s before next task...")
                await asyncio.sleep(60)
            finally:
                print(f"🔒 Closing browser for '{task_name}'...")
                await browser.stop()
                # Reset the Playwright pipe after every task — a stale pipe is the
                # primary cause of 'Browser window not found' on the NEXT launch.
                self_pw = await reset_shared_playwright()  # noqa: F841 — side-effect only
                print("   🔄 Playwright pipe refreshed for next task")
                await asyncio.sleep(10)  # Cooldown — let macOS release GPU/display handles
        
        # Cycle complete - run INTERSESSION task during wait period
        wait_mins = random.uniform(15, 20)  # Random 15-20 minutes total wait
        print(f"\n\n{'#'*60}")
        print(f"✅ CYCLE {cycle_count} COMPLETE - All {len(tasks)} tasks done!")
        print(f"⏳ INTERSESSION: Running Instahyre (20 jobs) during {wait_mins:.1f} min wait...")
        print(f"{'#'*60}")
        
        # Track intersession start time
        import time
        intersession_start = time.time()
        
        # Give Chrome time to fully exit from the last task before starting a fresh
        # persistent context — macOS can hold profile locks for several seconds after
        # context.close(), causing 'Browser window not found' / exitCode=0 crashes.
        print("⏳ [INTERSESSION] Waiting 15s for Chrome processes to fully exit...")
        await asyncio.sleep(15)
        
        # Run Instahyre INTERSESSION task
        intersession_browser = Browser(
            headless=False,
            user_data_dir=CHROME_USER_DATA,
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
            await stop_shared_playwright()
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
