import asyncio
import atexit
import random
import sys
import datetime
import os
import shutil
import tempfile
from pathlib import Path

# Add workspace root to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from playwright.async_api import async_playwright

_browser_counter = 0
_shared_playwright = None

# Capture the REAL system temp dir BEFORE we override TMPDIR below.
# Chrome's own temp files (.com.google.Chrome.*, chrome_chrome_url_fetcher_*)
# land here regardless of TMPDIR (it uses confstr/NSTemporaryDirectory on macOS),
# so we need the original path to sweep them.
_SYSTEM_TEMP = tempfile.gettempdir()

# Shared temp management — ONE wrapper dir per process run, reused across all
# tasks/cycles. Previously every Browser.start() created a fresh sentinel_<rand>
# wrapper + a sentinel_profile_<pid>_<taskid> dir (copying ~200MB of Chrome
# profile data) and never cleaned them up, leaking GBs across the infinite loop.
_shared_tmp_root = None      # e.g. /var/folders/.../T/sentinel_<rand>
_shared_profile_dir = None   # <_shared_tmp_root>/sentinel_profile_<pid> (user_data_dir)


def _sweep_chrome_temp():
    """Remove stale Chrome temp artifacts from the system temp dir.

    Cleans up three categories of leaked files that Chrome leaves behind when
    force-killed (which our stop() does via SIGTERM/SIGKILL):
      - sentinel_*                         our wrapper dirs (from past runs)
      - com.google.Chrome.chrome_chrome_url_fetcher_*   download temp (AI model etc)
      - .com.google.Chrome.*               per-session temp files (~458 MB each)

    Called at startup and after every Browser.stop() to keep temp bounded.
    """
    import glob
    patterns = [
        "sentinel_*",
        "com.google.Chrome.chrome_chrome_url_fetcher_*",
        ".com.google.Chrome.*",
    ]
    swept = 0
    for pattern in patterns:
        for path in glob.glob(os.path.join(_SYSTEM_TEMP, pattern)):
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    os.unlink(path)
                swept += 1
            except OSError:
                pass
    if swept:
        print(f"🧹 Swept {swept} stale Chrome temp item(s) from {_SYSTEM_TEMP}")


def _ensure_tmp_root():
    """Lazily create the single shared temp wrapper + profile dir.

    Sets TMPDIR once so subsequent tempfile calls stay under our wrapper.
    Returns the shared profile directory path.
    """
    global _shared_tmp_root, _shared_profile_dir
    if _shared_tmp_root is None:
        # Sweep stale Chrome temp from past force-killed runs first
        _sweep_chrome_temp()
        _shared_tmp_root = tempfile.mkdtemp(prefix="sentinel_")
        os.environ["TMPDIR"] = _shared_tmp_root
        # Name includes PID so the existing pgrep-based Chrome kill logic
        # (which matches `sentinel_profile_<pid>`) keeps working.
        _shared_profile_dir = os.path.join(
            _shared_tmp_root, f"sentinel_profile_{os.getpid()}"
        )
        os.makedirs(_shared_profile_dir, exist_ok=True)
        print(f"🔧 Shared TMPDIR: {_shared_tmp_root}")
    return _shared_profile_dir


def cleanup_tmp_root():
    """Delete the shared temp wrapper + sweep Chrome temp. Safe to call multiple times."""
    global _shared_tmp_root, _shared_profile_dir
    if _shared_tmp_root is not None:
        shutil.rmtree(_shared_tmp_root, ignore_errors=True)
        print(f"🧹 Cleaned up shared temp: {_shared_tmp_root}")
        _shared_tmp_root = None
        _shared_profile_dir = None
    # Also sweep Chrome's own temp artifacts (session files, download dirs)
    _sweep_chrome_temp()


atexit.register(cleanup_tmp_root)

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

    # Resource types to block for noise reduction.
    # NOTE: 'stylesheet' is intentionally NOT blocked — LinkedIn/Naukri use CSS
    # to toggle visibility of dropdowns/modals/hidden inputs; blocking CSS breaks
    # form UI. 'other' is NOT blocked — it can catch XHR/fetch form submissions.
    BLOCKED_RESOURCE_TYPES = [
        'image', 'font', 'media'
    ]
    
    # URL patterns to block (tracking, analytics, ads, heavy CDN media)
    BLOCKED_URL_PATTERNS = [
        # Ads, Trackers, Telemetry
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
        'tealium',
        'tiqcdn.com',
        # Media CDNs (Naukri & LinkedIn)
        '*.gif',
        '*.png',
        '*.jpg',
        '*.jpeg',
        '*.svg',
        '*.woff',
        '*.woff2',
        '*.ttf',
        '*.eot',
    ]
    
    async def start(self):
        import os
        import glob

        # Reuse ONE shared temp wrapper per process run (created lazily).
        _ensure_tmp_root()

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
            # Prevent Chrome from downloading on-device AI/ML models (Gemini Nano, Prompt API, OptGuide)
            '--disable-features=OptimizationGuideModelDownloading,OptimizationGuide,OptimizationGuideOnDeviceModel,PromptAPIForGeminiNano,LanguageDetectionModelDownloading,OptimizationHints,OptimizationHintsFetching,OptimizationTargetPrediction,Translate,MediaRouter,DialMediaRouteProvider,CalculateNativeWinOcclusion,InterestFeedContentSuggestions,PrivacySandboxSettings4',
            # --- NETWORK DATA SAVERS ---
            '--disable-background-networking',          # All background networking
            '--disable-component-update',               # Chrome component downloads
            '--disable-sync',                           # Google account sync
            '--disable-default-apps',                   # Default app installs
            '--no-default-browser-check',               # Default browser checks
            '--disable-domain-reliability',             # Domain reliability beacons
            '--disable-client-side-phishing-detection', # Phishing list updates
            '--disable-component-extensions-with-background-pages',
            '--metrics-recording-only',                 # Telemetry
            '--no-pings',
        ]
        
        final_user_data_dir = self.user_data_dir
        
        if self.user_data_dir:
            import shutil
            import glob
            
            # Reuse the single shared profile dir for the whole process run
            # instead of sentinel_profile_<pid>_<taskid> per task (which leaked).
            temp_dir = _shared_profile_dir
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
                    # Wipe any previous task's Default so each task starts from a
                    # clean mirror of the source profile (no stale session data),
                    # without allocating a new wrapper dir each time.
                    shutil.rmtree(dst_default, ignore_errors=True)
                    os.makedirs(dst_default, exist_ok=True)
                    print("  ⚡ Mirroring full profile (excluding Cache)...")
                    
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
            # Context-level route blocking (set in start()) covers all pages,
            # so no per-page handler is needed here.
            return page
        return None
    
    async def _setup_context_resource_blocking(self, context):
        """Setup resource blocking across the entire browser context (all tabs).

        This is the primary network saver: it aborts requests for images,
        fonts, and media before they hit the network, and blocks known
        tracking/analytics URLs. Attached at the context level so it covers
        the persistent-context default page (which new_page() never sees)
        as well as any pages opened later.

        Also tracks request counts by resource type for diagnostics — call
        print_route_stats() at task end to see what was blocked vs allowed.
        """
        # Per-task counters for diagnostics
        self._route_stats = {
            'blocked_type': {},   # by resource_type (image/font/media)
            'blocked_url': 0,     # by URL pattern
            'allowed': {},        # by resource_type
            'total_blocked': 0,
            'total_allowed': 0,
        }

        async def handle_route(route, request):
            rtype = request.resource_type

            # Check if resource type should be blocked
            if rtype in self.BLOCKED_RESOURCE_TYPES:
                self._route_stats['blocked_type'][rtype] = self._route_stats['blocked_type'].get(rtype, 0) + 1
                self._route_stats['total_blocked'] += 1
                await route.abort()
                return

            # Check if URL matches blocked patterns (stripping query parameters for extension matching)
            url = request.url.lower()
            url_path = url.split('?')[0]
            for pattern in self.BLOCKED_URL_PATTERNS:
                pattern_lower = pattern.lower()
                if pattern_lower.startswith('*.'):
                    # Handle wildcard patterns like *.png (matching stripped path)
                    suffix = pattern_lower[1:]  # Remove the *
                    if url_path.endswith(suffix):
                        self._route_stats['blocked_url'] += 1
                        self._route_stats['total_blocked'] += 1
                        await route.abort()
                        return
                elif pattern_lower in url:
                    self._route_stats['blocked_url'] += 1
                    self._route_stats['total_blocked'] += 1
                    await route.abort()
                    return

            # Allow the request
            self._route_stats['allowed'][rtype] = self._route_stats['allowed'].get(rtype, 0) + 1
            self._route_stats['total_allowed'] += 1
            await route.continue_()

        # Apply the route handler to all requests across the whole context
        await context.route("**/*", handle_route)
        print("   🔇 Context-wide resource blocking enabled (images, fonts, media, trackers)")

    def print_route_stats(self):
        """Print a summary of blocked vs allowed requests for this task."""
        stats = getattr(self, '_route_stats', None)
        if not stats:
            return
        print(f"\n📊 Route stats: {stats['total_blocked']} blocked, {stats['total_allowed']} allowed")
        if stats['blocked_type']:
            print(f"   Blocked by type: {stats['blocked_type']}")
        if stats['blocked_url']:
            print(f"   Blocked by URL pattern: {stats['blocked_url']}")
        if stats['allowed']:
            # Sort by count descending for readability
            allowed_sorted = sorted(stats['allowed'].items(), key=lambda x: -x[1])
            print(f"   Allowed by type: {dict(allowed_sorted)}")

    async def _setup_resource_blocking(self, page):
        """Setup resource blocking on a single page (legacy, kept for compatibility).

        Prefer _setup_context_resource_blocking() which covers all tabs.
        """
        async def handle_route(route, request):
            # Check if resource type should be blocked
            if request.resource_type in self.BLOCKED_RESOURCE_TYPES:
                await route.abort()
                return
            
            # Check if URL matches blocked patterns (stripping query params)
            url = request.url.lower()
            url_path = url.split('?')[0]
            for pattern in self.BLOCKED_URL_PATTERNS:
                pattern_lower = pattern.lower()
                if pattern_lower.startswith('*.'):
                    suffix = pattern_lower[1:]
                    if url_path.endswith(suffix):
                        await route.abort()
                        return
                elif pattern_lower in url:
                    await route.abort()
                    return
            
            # Allow the request
            await route.continue_()
        
        # Apply the route handler to all requests
        await page.route("**/*", handle_route)
        print("   🔇 Resource blocking enabled (images, fonts, media, trackers)")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _kill_pids(pids: list, label: str, timeout: float = 5.0) -> None:
        """SIGTERM then SIGKILL a list of PIDs."""
        import signal
        import time
        import subprocess as sp
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
            print("⚠️ Chrome still alive after 10s — force-killing...")
            temp_dir = getattr(self, '_temp_dir', None)
            if temp_dir:
                self._kill_chrome_holding_dir(temp_dir)
            else:
                self._kill_chrome_holding_dir(profile_marker)

        # 6. Sweep Chrome's temp artifacts from the system temp dir.
        # Chrome leaves behind .com.google.Chrome.* session files (~458 MB each)
        # and chrome_chrome_url_fetcher_* download dirs when force-killed.
        # Cleaning after every stop() keeps temp bounded across the infinite loop.
        _sweep_chrome_temp()

from src.core.config import CHROME_USER_DATA
from src.sentinel.agent import create_agent
from src.sentinel import prompts

async def main():
    print("🛡️  SENTINEL REBORN - Infinite Loop Mode")
    
    # Define Tasks: (Task Name, Start URL, Prompt)
    tasks = [
        # Priority 1 & 2: Job applications (Naukri first)
        ("Naukri Application", "https://www.naukri.com/mnjuser/recommendedjobs", prompts.NAUKRI_JOB_APPLY_TASK),
        ("LinkedIn Application", "https://www.linkedin.com/jobs/search-results/?currentJobId=4325424519&keywords=%22hiring%22%20AND%20%28%22Java%22%20OR%20%22JAVA%20FULL%20STACK%22%20OR%20%22React.js%22%20OR%20%22Software%20Engineer%22%29%20AND%20India&origin=JOB_SEARCH_PAGE_JOB_FILTER&referralSearchId=Qwth1ndwtouG0vtFGj%2Bpsg%3D%3D&geoId=102713980&distance=0.0&f_TPR=r86400&f_AL=true", prompts.LINKEDIN_JOB_APPLY_TASK),
        # Other tasks
        ("Instahyre Search", "https://www.instahyre.com/candidate/opportunities/?matching=true", prompts.INSTAHYRE_SEARCH_TASK),
        ("Naukri Employment LWD +15", "https://www.naukri.com/mnjuser/profile?id=&altresid", prompts.NAUKRI_EMPLOYMENT_LWD_15_TASK),
        ("Naukri Employment LWD +14", "https://www.naukri.com/mnjuser/profile?id=&altresid", prompts.NAUKRI_EMPLOYMENT_LWD_14_TASK),
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
            '--disable-features=OptimizationGuideModelDownloading,OptimizationGuide,OptimizationGuideOnDeviceModel,PromptAPIForGeminiNano,LanguageDetectionModelDownloading,OptimizationHints,OptimizationHintsFetching,OptimizationTargetPrediction,Translate,MediaRouter,DialMediaRouteProvider,CalculateNativeWinOcclusion,InterestFeedContentSuggestions,PrivacySandboxSettings4',
            '--disable-background-networking',
            '--disable-component-update',
            '--disable-sync',
            '--disable-default-apps',
            '--no-default-browser-check',
            '--disable-domain-reliability',
            '--disable-client-side-phishing-detection',
            '--disable-component-extensions-with-background-pages',
            '--metrics-recording-only',
            '--no-pings',
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
    
    # SINGLE agent instance reused across all tasks (P1a memory optimization).
    # Previously a new agent was created per task, reloading the 3.6 MB
    # qa_patterns.json and rebuilding pattern matchers/fingerprint caches
    # each time (~15-20 MB/task). Now we create once and reset per-task state.
    agent = create_agent()
    
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
                    print("✅ LinkedIn rate limit expired, resuming...")
                    linkedin_rate_limit_until = None
            
            # Check Naukri rate limit
            if task_name == "Naukri Application" and naukri_rate_limit_until:
                if datetime.datetime.now() < naukri_rate_limit_until:
                    remaining = (naukri_rate_limit_until - datetime.datetime.now()).seconds // 60
                    print(f"\n⏸️  Skipping Naukri (Rate Limited) - {remaining} mins remaining")
                    continue
                else:
                    print("✅ Naukri rate limit expired, resuming...")
                    naukri_rate_limit_until = None
            
            print(f"\n\n{'='*50}")
            print(f"📜 [{cycle_count}] TASK {i+1}/{len(tasks)}: {task_name}")
            print(f"{'='*50}")
            
            # Init Browser for THIS task (Fresh instance)
            browser = Browser(
                headless=False,
                user_data_dir=CHROME_USER_DATA,
            )
            
            # Reuse the shared agent, resetting per-task state (P1a).
            # This clears page/browser refs, counters, and injected-context
            # tracking while preserving pattern matchers and learned knowledge.
            agent.reset_per_task_state()
            
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
                cleanup_tmp_root()
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
        
        # Run Instahyre INTERSESSION task (reuse the shared agent with reset state)
        agent.reset_per_task_state()
        intersession_browser = Browser(
            headless=False,
            user_data_dir=CHROME_USER_DATA,
        )
        
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
            
            agent._page = page
            agent.browser = intersession_browser
            
            print("▶️  [INTERSESSION] Running Instahyre (20 jobs)...")
            await agent.run(task_description=prompts.INSTAHYRE_INTERSESSION_TASK)
            print("🎉 [INTERSESSION] Instahyre task completed!")
            
        except KeyboardInterrupt:
            print("\n🛑 Stopped by User (Ctrl+C)")
            await intersession_browser.stop()
            await stop_shared_playwright()
            cleanup_tmp_root()
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
            print("⏩ Intersession took longer than wait time, starting next cycle immediately")
        
        print(f"\n🔄 Starting Cycle {cycle_count + 1}...")

if __name__ == "__main__":
    asyncio.run(main())
