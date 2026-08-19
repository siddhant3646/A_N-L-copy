#!/usr/bin/env python3
"""
Full Tasks Execution & Deep Selector Audit Runner
Executes all 7 Sentinel tasks to complete execution using the seeded Chrome profile,
while intercepting and logging every single CSS selector touched in the DOM.
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

# Add workspace root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import CHROME_USER_DATA
from src.sentinel.run import Browser, get_shared_playwright, reset_shared_playwright, stop_shared_playwright, cleanup_tmp_root
from src.sentinel.agent import create_agent
from src.sentinel import prompts

DOM_TRACER_SCRIPT = """
(function() {
    if (window.__DOM_TRACER_INSTALLED__) return;
    window.__DOM_TRACER_INSTALLED__ = true;
    window.__TOUCHED_SELECTORS__ = window.__TOUCHED_SELECTORS__ || [];

    function record(selector, method, count, sampleTag) {
        if (typeof selector !== 'string' || !selector.trim()) return;
        window.__TOUCHED_SELECTORS__.push({
            selector: selector,
            method: method,
            count: count,
            sample: sampleTag || null,
            timestamp: Date.now(),
            url: window.location.href
        });
    }

    // Wrap document.querySelector
    const origDocQS = Document.prototype.querySelector;
    Document.prototype.querySelector = function(sel) {
        try {
            const el = origDocQS.apply(this, arguments);
            record(sel, 'document.querySelector', el ? 1 : 0, el ? el.tagName + (el.className ? '.' + el.className.split(' ').slice(0, 2).join('.') : '') : null);
            return el;
        } catch(e) {
            record(sel, 'document.querySelector:error', 0, e.message);
            throw e;
        }
    };

    // Wrap document.querySelectorAll
    const origDocQSA = Document.prototype.querySelectorAll;
    Document.prototype.querySelectorAll = function(sel) {
        try {
            const list = origDocQSA.apply(this, arguments);
            record(sel, 'document.querySelectorAll', list ? list.length : 0, list && list[0] ? list[0].tagName : null);
            return list;
        } catch(e) {
            record(sel, 'document.querySelectorAll:error', 0, e.message);
            throw e;
        }
    };

    // Wrap Element.prototype.querySelector
    const origElQS = Element.prototype.querySelector;
    Element.prototype.querySelector = function(sel) {
        try {
            const el = origElQS.apply(this, arguments);
            record(sel, 'element.querySelector', el ? 1 : 0, this.tagName + ' -> ' + (el ? el.tagName : 'none'));
            return el;
        } catch(e) {
            record(sel, 'element.querySelector:error', 0, e.message);
            throw e;
        }
    };

    // Wrap Element.prototype.querySelectorAll
    const origElQSA = Element.prototype.querySelectorAll;
    Element.prototype.querySelectorAll = function(sel) {
        try {
            const list = origElQSA.apply(this, arguments);
            record(sel, 'element.querySelectorAll', list ? list.length : 0, this.tagName + ' -> ' + (list ? list.length : 0));
            return list;
        } catch(e) {
            record(sel, 'element.querySelectorAll:error', 0, e.message);
            throw e;
        }
    };

    // Wrap Element.prototype.matches & closest
    const origClosest = Element.prototype.closest;
    Element.prototype.closest = function(sel) {
        try {
            const el = origClosest.apply(this, arguments);
            record(sel, 'element.closest', el ? 1 : 0, this.tagName + ' closest -> ' + (el ? el.tagName : 'none'));
            return el;
        } catch(e) {
            record(sel, 'element.closest:error', 0, e.message);
            throw e;
        }
    };
})();
"""


async def extract_touched_selectors(page) -> List[Dict[str, Any]]:
    """Fetch raw selector traces from the browser context."""
    if not page:
        return []
    try:
        raw_traces = await page.evaluate("() => window.__TOUCHED_SELECTORS__ || []")
        return raw_traces
    except Exception as e:
        print(f"   ⚠️ Could not extract touched selectors from page: {e}")
        return []


def aggregate_selectors(traces: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate raw selector traces into structured metrics."""
    agg = {}
    for t in traces:
        sel = t.get("selector", "")
        if not sel:
            continue
        if sel not in agg:
            agg[sel] = {
                "selector": sel,
                "methods": set(),
                "query_count": 0,
                "hit_count": 0,
                "miss_count": 0,
                "samples": set(),
                "urls": set(),
                "has_error": False,
                "error_messages": set()
            }
        
        agg[sel]["methods"].add(t.get("method", "unknown"))
        agg[sel]["query_count"] += 1
        count = t.get("count", 0)
        if count > 0:
            agg[sel]["hit_count"] += count
        else:
            agg[sel]["miss_count"] += 1
        
        if t.get("sample"):
            agg[sel]["samples"].add(str(t.get("sample"))[:60])
        if t.get("url"):
            agg[sel]["urls"].add(t.get("url"))
        if ":error" in t.get("method", ""):
            agg[sel]["has_error"] = True
            if t.get("sample"):
                agg[sel]["error_messages"].add(str(t.get("sample")))

    # Convert sets to lists for JSON serialization
    clean_agg = []
    for sel, data in agg.items():
        clean_agg.append({
            "selector": sel,
            "methods": list(data["methods"]),
            "query_count": data["query_count"],
            "total_elements_found": data["hit_count"],
            "miss_count": data["miss_count"],
            "success_rate": round(data["hit_count"] / max(1, data["query_count"]), 2) if data["hit_count"] > 0 else 0.0,
            "status": "ACTIVE_MATCH" if data["hit_count"] > 0 else "NO_MATCH",
            "samples": list(data["samples"])[:5],
            "urls": list(data["urls"])[:3],
            "has_error": data["has_error"],
            "errors": list(data["error_messages"])
        })
    
    # Sort by query count descending
    clean_agg.sort(key=lambda x: x["query_count"], reverse=True)
    return clean_agg


async def run_all_tasks_with_audit():
    print("=" * 80)
    print("🛡️  SENTINEL COMPLETE TASK EXECUTION & LIVE SELECTOR AUDIT")
    print(f"📁 Chrome Profile: {CHROME_USER_DATA}")
    print(f"⏰ Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    tasks = [
        # Task 1: Naukri Recommended Jobs Application
        ("Naukri Application", "https://www.naukri.com/mnjuser/recommendedjobs", prompts.NAUKRI_JOB_APPLY_TASK),
        
        # Task 2: LinkedIn Easy Apply Search
        ("LinkedIn Application", "https://www.linkedin.com/jobs/search/?keywords=%22hiring%22%20AND%20%28%22Java%22%20OR%20%22JAVA%20FULL%20STACK%22%20OR%20%22React.js%22%20OR%20%22Software%20Engineer%22%29%20AND%20India&origin=JOB_SEARCH_PAGE_JOB_FILTER&geoId=102713980&distance=0.0&f_TPR=r86400&f_AL=true", prompts.LINKEDIN_JOB_APPLY_TASK),
        
        # Task 3: Instahyre Job Opportunities & Search
        ("Instahyre Search", "https://www.instahyre.com/candidate/opportunities/?matching=true", prompts.INSTAHYRE_SEARCH_TASK),
        
        # Task 4: Naukri Employment LWD +15
        ("Naukri Employment LWD +15", "https://www.naukri.com/mnjuser/profile?id=&altresid", prompts.NAUKRI_EMPLOYMENT_LWD_15_TASK),
        
        # Task 5: Naukri Employment LWD +14
        ("Naukri Employment LWD +14", "https://www.naukri.com/mnjuser/profile?id=&altresid", prompts.NAUKRI_EMPLOYMENT_LWD_14_TASK),
        
        # Task 6: Naukri Profile Resume Headline Update
        ("Naukri Profile Update", "https://www.naukri.com/mnjuser/profile?id=&altresid", prompts.NAUKRI_PROFILE_UPDATE_TASK),
        
        # Task 7: Naukri Early Access Roles
        ("Naukri Early Access", "https://www.naukri.com/mnjuser/recommended-earjobs", prompts.NAUKRI_EARLY_ACCESS_TASK),
    ]

    agent = create_agent()
    all_task_reports = []

    for i, (task_name, start_url, task_prompt) in enumerate(tasks):
        print(f"\n\n{'#'*70}")
        print(f"🚀 [TASK {i+1}/{len(tasks)}] STARTING FULL RUN: {task_name}")
        print(f"🔗 URL: {start_url}")
        print(f"{'#'*70}")

        browser = Browser(
            headless=False,
            user_data_dir=CHROME_USER_DATA
        )

        agent.reset_per_task_state()
        task_start_time = time.time()
        task_report = {
            "task_id": i + 1,
            "task_name": task_name,
            "start_url": start_url,
            "start_time": datetime.now().isoformat(),
            "end_time": None,
            "duration_seconds": 0,
            "success": False,
            "steps_taken": 0,
            "applications_submitted": 0,
            "touched_selectors_count": 0,
            "active_matching_selectors_count": 0,
            "touched_selectors": [],
            "error": None
        }

        try:
            print("🌐 Launching Browser with DOM Selector Tracer...")
            await browser.start()

            page = await browser.get_current_page()
            if not page:
                page = await browser.new_page()

            # Install the DOM Selector Tracer init script on context
            await page.context.add_init_script(DOM_TRACER_SCRIPT)
            print("   ✅ DOM Selector Tracer hooked into browser context")

            # Navigate to the task starting URL
            print(f"🔗 Navigating to {start_url}...")
            await page.goto(start_url, wait_until='domcontentloaded', timeout=45000)
            await asyncio.sleep(4)

            # Re-evaluate tracer in current page to ensure early binding
            await page.evaluate(DOM_TRACER_SCRIPT)

            agent._page = page
            agent.browser = browser

            print(f"▶️  Executing Agent Task Automation: {task_name}...")
            # RUN THE REAL TASK TO FULL COMPLETION
            success = await agent.run(task_description=task_prompt)
            task_report["success"] = bool(success)
            print(f"\n🏁 Task Finished! Result Success = {success}")

            # Extract all touched CSS selectors
            print("🔍 Fetching all touched DOM selectors from runtime...")
            raw_traces = await extract_touched_selectors(page)
            aggregated = aggregate_selectors(raw_traces)
            task_report["touched_selectors"] = aggregated
            task_report["touched_selectors_count"] = len(aggregated)
            task_report["active_matching_selectors_count"] = len([s for s in aggregated if s["status"] == "ACTIVE_MATCH"])
            task_report["steps_taken"] = getattr(agent.state, 'step_count', 0)
            task_report["applications_submitted"] = getattr(agent, 'metrics', {}).get('applications_submitted', 0)

            print(f"📊 Touched Selectors in {task_name}: {len(aggregated)} unique selectors")
            print(f"   ✅ Active Matches: {task_report['active_matching_selectors_count']}")
            print(f"   ⚠️ Misses/Checks: {len(aggregated) - task_report['active_matching_selectors_count']}")

        except Exception as e:
            print(f"❌ Execution error in {task_name}: {e}")
            import traceback
            traceback.print_exc()
            task_report["error"] = str(e)
            try:
                raw_traces = await extract_touched_selectors(agent._page if agent._page else page)
                task_report["touched_selectors"] = aggregate_selectors(raw_traces)
            except:
                pass
        finally:
            task_end_time = time.time()
            task_report["end_time"] = datetime.now().isoformat()
            task_report["duration_seconds"] = round(task_end_time - task_start_time, 2)
            all_task_reports.append(task_report)

            print(f"🔒 Closing browser for '{task_name}'...")
            await browser.stop()
            await reset_shared_playwright()
            print("   ⏳ Cooldown 8s before next task...")
            await asyncio.sleep(8)

    # Save comprehensive audit results
    audit_file = Path(__file__).parent.parent / "audit" / "complete_task_execution_audit.json"
    audit_file.parent.mkdir(parents=True, exist_ok=True)
    with open(audit_file, "w") as f:
        json.dump(all_task_reports, f, indent=2)
    print(f"\n💾 Saved full execution and selector audit to: {audit_file}")

    # Generate Markdown Summary
    summary_file = Path(__file__).parent.parent / "audit" / "TOUCHED_SELECTORS_SUMMARY.md"
    with open(summary_file, "w") as f:
        f.write("# Sentinel Tasks - Live Touched CSS Selectors Audit\n\n")
        f.write(f"**Execution Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("| # | Task Name | Status | Steps | Total Selectors Touched | Active Match Selectors |\n")
        f.write("|---|-----------|--------|-------|-------------------------|------------------------|\n")
        for r in all_task_reports:
            status_emoji = "✅ Success" if r["success"] else "⚠️ Completed"
            f.write(f"| {r['task_id']} | {r['task_name']} | {status_emoji} | {r['steps_taken']} | {r['touched_selectors_count']} | {r['active_matching_selectors_count']} |\n")
        
        f.write("\n\n---\n\n")
        for r in all_task_reports:
            f.write(f"## Task {r['task_id']}: {r['task_name']}\n\n")
            f.write(f"- **URL**: `{r['start_url']}`\n")
            f.write(f"- **Duration**: {r['duration_seconds']}s\n")
            f.write(f"- **Success**: {r['success']}\n\n")
            f.write("### Touched CSS Selectors Breakdown\n\n")
            f.write("| Selector | Methods | Queries | Elements Found | Status | Sample Elements |\n")
            f.write("|---|---|---|---|---|---|\n")
            for sel in r["touched_selectors"][:40]:  # Top 40
                methods_str = ", ".join(sel["methods"])
                samples_str = ", ".join(sel["samples"]) if sel["samples"] else "None"
                f.write(f"| `{sel['selector']}` | `{methods_str}` | {sel['query_count']} | {sel['total_elements_found']} | {sel['status']} | {samples_str} |\n")
            f.write("\n---\n\n")

    print(f"📄 Saved markdown summary to: {summary_file}")

    await stop_shared_playwright()
    cleanup_tmp_root()
    print("🎉 Full task suite execution and audit completed successfully!")

if __name__ == "__main__":
    asyncio.run(run_all_tasks_with_audit())
