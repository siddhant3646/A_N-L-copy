"""Tests for pattern-load and matcher-index caching (suite runtime guard).

The corpus is a 68 MB JSON file; these caches are what keep per-test
SentinelAgent/PatternMatcher construction fast.  If they ever silently stop
working, the suite regresses to tens of minutes, so the invariants below are
asserted explicitly.
"""

import os
import shutil
import tempfile

import pytest

from src.patterns.pattern_loader import load_patterns
from src.patterns.pattern_matcher import PatternMatcher


@pytest.fixture()
def small_corpus(tmp_path):
    src = {
        "version": "3.0",
        "patterns": {
            "p_one": {"patterns": ["how many years of experience"], "category": "experience", "default": "4.2 Years"},
            "p_two": {"patterns": ["current ctc"], "category": "salary", "default": "23 LPA"},
        },
    }
    import json
    path = tmp_path / "qa.json"
    path.write_text(json.dumps(src))
    return str(path)


def test_load_patterns_is_cached_until_file_changes(small_corpus):
    first = load_patterns(small_corpus)
    assert load_patterns(small_corpus) is first

    payload = open(small_corpus).read()
    time_shift = os.stat(small_corpus).st_mtime_ns + 10_000_000_000
    with open(small_corpus, "w") as fh:
        fh.write(payload.replace("4.2 Years", "5 Years"))
    os.utime(small_corpus, ns=(time_shift, time_shift))
    second = load_patterns(small_corpus)
    assert second is not first
    assert second["patterns"]["p_one"]["default"] == "5 Years"


def test_force_reload_bypasses_cache(small_corpus):
    first = load_patterns(small_corpus)
    assert load_patterns(small_corpus, force_reload=True) is not first


def test_matcher_reuses_index_bundle_for_same_dict(small_corpus):
    data = load_patterns(small_corpus)
    a = PatternMatcher(data)
    b = PatternMatcher(data)
    assert b._norm_owner_index is a._norm_owner_index

    mutated = {"version": "3.0", "patterns": {}}
    b.update_patterns(mutated)
    assert b._norm_owner_index is not a._norm_owner_index
    assert a._norm_owner_index  # original bundle untouched by update_patterns
    assert load_patterns(small_corpus) is data
