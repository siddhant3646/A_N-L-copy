"""Capture Instahyre network endpoints and inspect how skills and search work."""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, reset_shared_playwright

OUTPUT_DIR = Path("live_test_output/instahyre_skills")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


async def main():
    print("🚀 Probing Instahyre Network Calls and Opportunities API...")
    browser = Browser(headless=False, user_data_dir=CHROME_USER_DATA)
    await browser.start()

    page = await browser.get_current_page() or await browser.new_page()

    network_logs = []

    async def on_response(response):
        url = response.url
        if any(keyword in url for keyword in ['api', 'opportunit', 'skill', 'job', 'search', 'filter']):
            try:
                ct = response.headers.get('content-type', '')
                status = response.status
                body_sample = ""
                if 'json' in ct:
                    data = await response.json()
                    body_sample = json.dumps(data)[:500]
                network_logs.append({
                    "url": url,
                    "status": status,
                    "content_type": ct,
                    "body_sample": body_sample
                })
                print(f"📡 [{status}] {url[:90]}")
            except Exception:
                pass

    page.on("response", on_response)

    url = "https://www.instahyre.com/candidate/opportunities/?matching=true"
    print(f"🔗 Navigating to {url}...")
    await page.goto(url, wait_until="domcontentloaded", timeout=45000)

    # Wait for the initial "Fetching" spinner / loading to finish
    print("⏳ Waiting for initial opportunities load...")
    for _ in range(30):
        await asyncio.sleep(1)
        is_fetching = await page.evaluate("""() => {
            const body = document.body ? document.body.innerText : '';
            return body.includes('Fetching') || !!document.querySelector('.loading, .spinner, .fetching');
        }""")
        if not is_fetching:
            print("✅ Fetching finished!")
            break

    await asyncio.sleep(3)

    # Inspect the underlying load function in Selectize to see where it gets skills from
    load_details = await page.evaluate("""() => {
        const el = document.querySelector('#skills-drop-select-job-search');
        if (!el || !window.$) return { error: "no el or $" };
        const sel = window.$(el)[0]?.selectize;
        if (!sel) return { error: "no selectize" };
        
        // Let's inspect scope functions or http calls
        const ngEl = window.angular ? window.angular.element(el) : null;
        const scope = ngEl ? ngEl.scope() : null;
        
        return {
            selectizeSettings: {
                load: sel.settings.load ? sel.settings.load.toString() : null,
                url: sel.settings.url || null,
                optionsCount: Object.keys(sel.options).length
            },
            scopeFuncs: scope ? Object.keys(scope).filter(k => typeof scope[k] === 'function') : []
        };
    }""")
    print("\n🔍 Load Details:", json.dumps(load_details, indent=2))

    # Now let's test typing a skill like "Java" into the selectize input and see what network calls happen
    print("\n⌨️ Testing typing 'Java' into skills input to observe autocomplete...")
    await page.evaluate("""() => {
        const el = document.querySelector('#skills-drop-select-job-search');
        if (window.$ && el) {
            const sel = window.$(el)[0]?.selectize;
            if (sel) {
                sel.focus();
                sel.onSearchChange('Java');
            }
        }
    }""")
    await asyncio.sleep(3)

    # Check what options appeared in selectize after typing 'Java'
    options_after_java = await page.evaluate("""() => {
        const el = document.querySelector('#skills-drop-select-job-search');
        if (window.$ && el) {
            const sel = window.$(el)[0]?.selectize;
            if (sel) {
                return Object.keys(sel.options).map(k => sel.options[k]);
            }
        }
        return [];
    }""")
    print(f"✨ Selectize options after typing 'Java' ({len(options_after_java)}):", json.dumps(options_after_java[:10], indent=2))

    # Save network logs
    out = OUTPUT_DIR / f"network_logs_{int(time.time())}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "logs": network_logs,
            "load_details": load_details,
            "options_after_java": options_after_java
        }, f, indent=2)
    print(f"\n💾 Saved network logs to {out}")

    await browser.stop(fast=True)
    await reset_shared_playwright()


if __name__ == "__main__":
    asyncio.run(main())
