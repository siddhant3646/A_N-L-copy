"""
Infinite pattern-coverage audit loop ("check on net").

Fetches real job-application questions from the web (DuckDuckGo Lite, no API
key required), checks each against the existing matcher (config/qa_patterns.json),
and logs the questions with NO / LOW-CONFIDENCE match as candidate patterns that
could be added to the project.

Nothing is auto-injected into qa_patterns.json. Gaps are logged to the console
and persisted to:
    - <log-dir>/pattern_audit.log          (human-readable, timestamped)
    - <log-dir>/candidate_patterns.json    (merge-ready via inject_patterns.py later)

Usage:
    python scripts/pattern_audit_loop.py                 # runs forever
    python scripts/pattern_audit_loop.py --once         # single cycle, then exit
    python scripts/pattern_audit_loop.py --interval 45 --threshold 0.8

Stop with Ctrl-C. A summary is printed on exit.
"""

import argparse
import html
import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from collections import OrderedDict
from datetime import datetime

# --- Repo imports -----------------------------------------------------------
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from src.patterns.pattern_matcher import create_matcher  # noqa: E402
from import_qa_results import (  # noqa: E402
    categorize_question,
    generate_pattern_id,
    extract_pattern_strings,
)

# --- Web search (DuckDuckGo Lite, key-free) ---------------------------------
DDG_LITE = "https://lite.duckduckgo.com/lite/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

# Curated query pool targeting questions asked on WORKDAY application forms.
# Live-fetched only (no offline bank) — sourced from web search of Workday
# help/community docs and third-party write-ups of real Workday questions.
DEFAULT_QUERIES = [
    "workday job application questions",
    "workday application form questions",
    "workday legally authorized to work question",
    "workday will you require sponsorship now or in the future question",
    "workday previously employed by company question",
    "workday equal opportunity veteran disability question",
    "workday background check drug test question",
    "workday race ethnicity gender voluntary question",
    "workday consent to data privacy collection question",
    "workday reason for leaving dates of employment question",
    "workday are you at least 18 years of age question",
    "workday referral current employee question",
    "workday highest level of education completed question",
    "workday willing to relocate for this role question",
    "workday previously applied to this company question",
    "workday citizenship work authorization documentation question",
]

# Strong interrogative phrases (a statement containing one of these is very
# likely a real question). Single question-words alone are too noisy, so they
# are only accepted when the sentence ends with '?'.
STRONG_PHRASES = (
    "are you", "do you", "have you", "can you", "will you",
    "would you", "could you", "is your", "did you", "were you",
    "are we", "what is", "what are", "how many", "how much",
    "when is", "when are", "where is", "which",
)
Q_START = (
    "what", "when", "where", "which", "who", "why", "how",
    "are", "do", "does", "did", "have", "has", "had",
    "can", "could", "will", "would", "is", "am", "was", "were",
    "should", "may", "might", "shall",
)
# Words that signal an APPLICANT-facing question (vs. employer "ask candidates"
# content). Used to filter out noise from generic web results.
APPLICANT_SIGNAL = (
    "you", "your", " i ", "me ", "my ", "application", "apply",
    "form", "resume", "cv", "profile", "candidate",
)
# Personal-pronoun signal: required for the '?' / question-start branch so that
# employer-side titles (e.g. "What interview questions does Workday ask?") are
# excluded. Applicant questions virtually always contain "you"/"your".
PERSONAL_SIGNAL = ("you", "your", " i ", "me ", "my ")
APP_KEYWORDS = (
    "experience", "salary", "ctc", "lpa", "notice", "relocate", "location",
    "authorize", "visa", "work permit", "sponsorship", "shift", "available",
    "availability", "degree", "education", "skill", "proficiency", "tool",
    "technology", "framework", "language", "certification", "citizenship",
    "background", "criminal", "conviction", "consent", "privacy", "data",
    "remote", "hybrid", "travel", "relocation", "gender", "veteran",
    "disability", "ethnicity", "race", "employment", "employer", "joining",
    "start date", "interview", "bond", "nda", "conflict", "reference", "drug",
)

# --- Live-fetch only --------------------------------------------------------
# Questions are sourced exclusively from the web (Workday-specific queries via
# DuckDuckGo Lite). No offline/synthetic question bank is used.



def _fetch(url, data=None, timeout=8):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as r:
        return r.read().decode("utf-8", "ignore")


def _strip(html_text):
    text = re.sub(r"<[^>]+>", " ", html_text)
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def _extract_result_links(html_text):
    """Return list of real destination URLs from DDG lite redirect links."""
    links = []
    for m in re.finditer(r'uddg=([^&"\'<>\s]+)', html_text):
        try:
            links.append(urllib.parse.unquote(m.group(1)))
        except Exception:
            pass
    return links


def search_questions(query, deep_limit=2):
    """Return a list of candidate question strings harvested from the web."""
    candidates = []
    try:
        data = urllib.parse.urlencode({"q": query}).encode()
        html_text = _fetch(DDG_LITE, data=data)
    except Exception as e:
        print(f"  [web] search failed for {query!r}: {type(e).__name__}: {e}",
              file=sys.stderr)
        return candidates

    page_text = _strip(html_text)
    # Split into per-result blocks: " 1. " ... " 2. " etc.
    blocks = re.split(r"\s\d+\.\s", page_text)
    for block in blocks[1:]:
        candidates.extend(_sentences_from(block))

    # Harvest result-link TITLES (often phrased as questions, e.g.
    # "What Is Your Expected Salary? | Indeed").
    for m in re.finditer(r'class="result-link"[^>]*>(.*?)</a>', html_text, re.S | re.I):
        title = _strip(m.group(1))
        if 8 <= len(title) <= 160:
            candidates.extend(_sentences_from(title))

    # Deep fetch: pull '?' sentences from a couple of result pages.
    if deep_limit > 0:
        for url in _extract_result_links(html_text)[:deep_limit]:
            try:
                page = _fetch(url, timeout=10)
                for sent in _sentences_from(_strip(page)):
                    candidates.append(sent)
            except Exception:
                continue
    return candidates


def _sentences_from(text):
    out = []
    for raw in re.split(r"(?<=[?.])\s+", text):
        s = raw.strip().strip('"').strip()
        s = re.sub(r"^Q[:\-)]\s*", "", s, flags=re.I)
        if not (8 <= len(s) <= 220):
            continue
        low = s.lower()
        words = low.split()
        starts_q = bool(words) and words[0] in Q_START
        # A sentence ending in '?' or starting with a question word is treated
        # as a real question worth checking. Statement-style questions must
        # carry a strong interrogative phrase AND an employment-domain keyword.
        if (s.endswith("?") or starts_q) and any(sig in low for sig in PERSONAL_SIGNAL):
            out.append(s)
        elif any(w in low for w in STRONG_PHRASES) and any(k in low for k in APP_KEYWORDS):
            out.append(s)
    return out


def _token_overlap(question, pattern_data):
    """True if the question shares a meaningful token with the matched pattern
    (its pattern strings or category). Used to catch high-confidence
    MISMATCHES where the matcher latched onto an unrelated pattern."""
    qtokens = set(re.findall(r"[a-z]{3,}", question.lower()))
    if not qtokens:
        return True
    blob = " ".join(pattern_data.get("patterns", [])) + " " + pattern_data.get("category", "")
    ptokens = set(re.findall(r"[a-z]{3,}", blob.lower()))
    # Ignore ultra-common stopwords that would always overlap.
    qtokens -= {"what", "your", "have", "with", "are", "you", "the", "for", "and"}
    return len(qtokens & ptokens) > 0


def looks_like_gap(question, matcher, threshold):
    """Return (is_gap, answer, confidence, top_match_id, top_score, mismatch)."""
    answer, confidence = matcher.fuzzy_match(question)
    top = matcher.get_all_matches(question, min_confidence=0.0)
    top_id, top_score = (top[0][0], top[0][2]) if top else (None, 0.0)
    no_match = (answer is None) or (confidence < threshold)
    # Detect high-confidence mismatches: matched a pattern with zero token
    # overlap (e.g. "blood group" -> "Please provide" at 0.98).
    mismatch = False
    if top_id and top_id in matcher.patterns["patterns"]:
        mismatch = not _token_overlap(question, matcher.patterns["patterns"][top_id])
    is_gap = no_match or mismatch
    return is_gap, answer, confidence, top_id, top_score, mismatch


def normalize(q):
    return re.sub(r"\s+", " ", q.lower().strip().rstrip("?").strip())


def build_candidate(question, matcher):
    existing_keys = set(matcher.patterns["patterns"].keys())
    category = categorize_question(question, "<TODO>")
    pid = generate_pattern_id(question, existing_keys)
    pattern_strings = extract_pattern_strings(question)
    return OrderedDict([
        ("id", pid),
        ("category", category),
        ("question", question),
        ("patterns", pattern_strings),
        ("default", "<TODO: define answer for this project>"),
        ("input_type_defaults", {"text": "<TODO>"}),
        ("priority", 5),
        ("auto_discovered", True),
        ("discovered_at", datetime.now().isoformat(timespec="seconds")),
    ])


def load_existing_candidates(path):
    if not os.path.exists(path):
        return [], set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cands = data.get("candidates", [])
    except Exception:
        return [], set()
    seen = {normalize(c.get("question", "")) for c in cands if c.get("question")}
    return cands, seen


def main():
    ap = argparse.ArgumentParser(description="Infinite web-driven pattern audit loop")
    ap.add_argument("--once", action="store_true", help="Run a single cycle then exit")
    ap.add_argument("--interval", type=int, default=30, help="Seconds between cycles (default 30)")
    ap.add_argument("--threshold", type=float, default=0.7,
                    help="Confidence below this (or no match) = gap (default 0.7)")
    ap.add_argument("--max-per-cycle", type=int, default=15,
                    help="Max candidate questions logged per cycle (default 15)")
    ap.add_argument("--deep-limit", type=int, default=2,
                    help="Result pages deep-fetched per query (default 2)")
    ap.add_argument("--log-dir", default=os.path.join(REPO_ROOT, "audit"),
                    help="Directory for log + candidate JSON")
    ap.add_argument("--shuffle", action="store_true", help="Randomize query order each cycle")
    args = ap.parse_args()

    os.makedirs(args.log_dir, exist_ok=True)
    log_path = os.path.join(args.log_dir, "pattern_audit.log")
    cand_path = os.path.join(args.log_dir, "candidate_patterns.json")

    queries = list(DEFAULT_QUERIES)
    if args.shuffle:
        import random
        random.shuffle(queries)

    matcher = create_matcher()
    total_patterns = len(matcher.patterns["patterns"])
    print(f"[init] Loaded matcher with {total_patterns} patterns")
    print(f"[init] log={log_path}")
    print(f"[init] candidates={cand_path}")
    print(f"[init] threshold={args.threshold} interval={args.interval}s max/cycle={args.max_per_cycle} deep={args.deep_limit}")
    print("[init] LIVE-FETCH ONLY (Workday queries via DuckDuckGo). Press Ctrl-C to stop.\n")

    candidates, seen_questions = load_existing_candidates(cand_path)
    stats = {"cycles": 0, "checked": 0, "gaps": 0, "new_candidates": 0}

    cycle = 0
    try:
        while True:
            cycle += 1
            if args.shuffle and cycle % len(queries) == 0:
                import random
                random.shuffle(queries)
            query = queries[(cycle - 1) % len(queries)]
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{ts}] cycle {cycle}: searching -> {query!r}")

            questions = search_questions(query, deep_limit=args.deep_limit)
            source = "workday"
            if not questions:
                print(f"  [workday] no questions fetched this cycle (net blocked/empty)")

            # De-dupe against already-seen questions this run / file.
            fresh = []
            for q in questions:
                n = normalize(q)
                if n and n not in seen_questions:
                    seen_questions.add(n)
                    fresh.append(q)

            logged_this_cycle = 0
            for q in fresh:
                stats["checked"] += 1
                is_gap, answer, conf, top_id, top_score, mismatch = looks_like_gap(
                    q, matcher, args.threshold)
                if not is_gap:
                    continue
                stats["gaps"] += 1
                cand = build_candidate(q, matcher)
                cand["source"] = source
                cand["mismatch"] = mismatch
                candidates.append(cand)
                stats["new_candidates"] += 1
                logged_this_cycle += 1

                tag = "MISMATCH" if mismatch else "GAP"
                line = (f"[{source}] [{tag}] conf={conf:.2f} top={top_id}({top_score:.2f}) "
                        f"-> id={cand['id']} cat={cand['category']} | {q}")
                print(f"  {line}")
                with open(log_path, "a", encoding="utf-8") as lf:
                    lf.write(f"{ts} {line}\n")

                if logged_this_cycle >= args.max_per_cycle:
                    break

            # Persist candidates (throttled, only when something added).
            if logged_this_cycle > 0:
                with open(cand_path, "w", encoding="utf-8") as cf:
                    json.dump({"candidates": candidates}, cf, indent=2, ensure_ascii=False)

            stats["cycles"] = cycle
            print(f"[{ts}] cycle {cycle} done: checked={stats['checked']} "
                  f"gaps={stats['gaps']} new={stats['new_candidates']} "
                  f"queue={len(queries) - (cycle % len(queries)) or len(queries)}\n")

            if args.once:
                break
            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\n[stop] KeyboardInterrupt received. Final summary:")

    print(f"  cycles={stats['cycles']} checked={stats['checked']} "
          f"gaps={stats['gaps']} new_candidates={stats['new_candidates']}")
    print(f"  candidates saved to: {cand_path}")
    # Final flush of candidates.
    with open(cand_path, "w", encoding="utf-8") as cf:
        json.dump({"candidates": candidates}, cf, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
