"""Regression tests for the Indeed \"Easily apply\" surface detection.

Indeed opens SmartApply in a NEW TAB. The handler must discover that tab even
though the original job-view page never navigates. Previously the set of pages
was snapshotted *after* the Apply click, so the new tab was never detected and
every job reported "Indeed apply container not detected".
"""

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from src.sentinel.agent import SentinelAgent


class _FakeLocator:
    def __init__(self, on_click):
        self._on_click = on_click

    @property
    def first(self):
        return self

    async def count(self):
        return 1

    async def is_visible(self):
        return True

    async def click(self, **kwargs):
        self._on_click()


class _FakeContext:
    def __init__(self):
        self.pages = []


class _FakePage:
    def __init__(self, url, context):
        self.url = url
        self.context = context
        self.frames = [self]
        self.main_frame = self
        self._closed = False
        self.on_click = lambda: None

    def locator(self, selector):
        return _FakeLocator(self.on_click)

    async def bring_to_front(self):
        pass

    async def evaluate(self, expression, arg=None):
        return {}

    async def close(self):
        self._closed = True

    def is_closed(self):
        return self._closed


class _FakeFrame:
    def __init__(self, page):
        self.page = page


class TestIndeedApplyFlowDetection(unittest.TestCase):
    def setUp(self):
        self.agent = SentinelAgent()

    def _run(self, page, wait_frame=None, is_submitted=None):
        if is_submitted is None:
            is_submitted = AsyncMock(
                side_effect=lambda t: (getattr(t, 'url', '') or '').startswith('https://smartapply')
            )
        with patch.object(self.agent, '_indeed_dismiss_smartapply_cookies', AsyncMock()), \
             patch.object(self.agent, '_indeed_wait_for_apply_frame', AsyncMock(return_value=wait_frame)), \
             patch.object(self.agent, '_indeed_is_submitted', is_submitted), \
             patch('src.sentinel.agent.asyncio.sleep', AsyncMock()):
            return asyncio.run(self.agent._indeed_run_apply_flow(page))

    def test_detects_smartapply_opened_in_new_tab(self):
        ctx = _FakeContext()
        page = _FakePage('https://in.indeed.com/viewjob?jk=abc', ctx)
        ctx.pages.append(page)
        new_tab = _FakePage('about:blank', ctx)

        def on_click():
            new_tab.url = 'https://smartapply.indeed.com/beta/indeedapply/form/contact-info'
            ctx.pages.append(new_tab)

        page.on_click = on_click
        self.agent._page = page

        result = self._run(page)

        self.assertTrue(result)
        self.assertTrue(new_tab.is_closed(), "popup apply tab should be cleaned up")

    def test_detects_apply_iframe_in_new_tab(self):
        """When the new tab URL is not a SmartApply URL, its iframe is used."""
        ctx = _FakeContext()
        page = _FakePage('https://in.indeed.com/viewjob?jk=abc', ctx)
        ctx.pages.append(page)
        new_tab = _FakePage('about:blank', ctx)

        def on_click():
            ctx.pages.append(new_tab)

        page.on_click = on_click
        self.agent._page = page

        result = self._run(
            page,
            wait_frame=_FakeFrame(new_tab),
            is_submitted=AsyncMock(side_effect=lambda t: t is new_tab),
        )

        self.assertTrue(result)
        self.assertTrue(new_tab.is_closed())


if __name__ == '__main__':
    unittest.main()
