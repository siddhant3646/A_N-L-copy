"""
Tests for the Naukri "apply to 5 jobs across sections" flow.

Covers the fix for the bug where applying to fewer than 5 jobs on a page would
stop the task instead of navigating to the next section to apply to the
remaining jobs.

The core of the fix is two helper methods on SentinelAgent:
  - _resolve_naukri_completion(): parses "X out of Y" from the success page,
    updates the cumulative counter, and returns 'CHATBOT_COMPLETE: <N>/5'.
  - _handle_naukri_post_apply(): decides whether to continue (need more jobs)
    or stop (target reached) based on that string.
"""

import pytest
from unittest.mock import AsyncMock

from src.sentinel.agent import SentinelAgent
from src.sentinel.schemas import SentinelState


@pytest.fixture
def agent(mock_page):
    """A SentinelAgent wired to a mocked page."""
    a = SentinelAgent(browser=None)
    a._page = mock_page
    a.state = SentinelState()
    a.metrics['applications_submitted'] = 0
    return a


# =============================================================================
# _resolve_naukri_completion
# =============================================================================

class TestResolveNaukriCompletion:
    @pytest.mark.asyncio
    async def test_parses_count_and_returns_formatted_string(self, agent):
        """JS returns 'CHATBOT_COMPLETE: 3/5' when '3 out of 5' is on the page."""
        agent._page.evaluate = AsyncMock(return_value='CHATBOT_COMPLETE: 3/5')
        result = await agent._resolve_naukri_completion()
        assert result == 'CHATBOT_COMPLETE: 3/5'
        assert result.startswith('CHATBOT_COMPLETE')
        assert '3' in result and '5' in result

    @pytest.mark.asyncio
    async def test_cumulative_count_second_call(self, agent):
        """Second success (2 more) yields cumulative total of 5."""
        # First batch: 3 applied
        agent._page.evaluate = AsyncMock(return_value='CHATBOT_COMPLETE: 3/5')
        first = await agent._resolve_naukri_completion()
        assert first == 'CHATBOT_COMPLETE: 3/5'
        # Second batch: 2 more -> cumulative 5
        agent._page.evaluate = AsyncMock(return_value='CHATBOT_COMPLETE: 5/5')
        second = await agent._resolve_naukri_completion()
        assert second == 'CHATBOT_COMPLETE: 5/5'

    @pytest.mark.asyncio
    async def test_no_count_text_returns_zero(self, agent):
        """When no 'X out of Y' text is found, returns 0/5 (safe default)."""
        agent._page.evaluate = AsyncMock(return_value='CHATBOT_COMPLETE: 0/5')
        result = await agent._resolve_naukri_completion()
        assert result == 'CHATBOT_COMPLETE: 0/5'

    @pytest.mark.asyncio
    async def test_returns_safe_default_when_page_missing(self, agent):
        """Without a page, returns a safe 'CHATBOT_COMPLETE: 0/5' string."""
        agent._page = None
        result = await agent._resolve_naukri_completion()
        assert result == 'CHATBOT_COMPLETE: 0/5'

    @pytest.mark.asyncio
    async def test_handles_evaluate_exception(self, agent):
        """If page.evaluate throws, returns safe default instead of propagating."""
        agent._page.evaluate = AsyncMock(side_effect=RuntimeError("page detached"))
        result = await agent._resolve_naukri_completion()
        assert result == 'CHATBOT_COMPLETE: 0/5'


# =============================================================================
# _handle_naukri_post_apply — under target (continue)
# =============================================================================

class TestPostApplyUnderTarget:
    @pytest.mark.asyncio
    async def test_under_5_continues_and_navigates(self, agent):
        """Applied 3/5 -> should navigate to recommendedjobs and return True."""
        result = await agent._handle_naukri_post_apply('CHATBOT_COMPLETE: 3/5')
        assert result is True
        assert agent.state.task_complete is False
        assert agent.metrics['applications_submitted'] == 3
        agent._page.goto.assert_awaited_once()
        called_url = agent._page.goto.call_args.args[0]
        assert 'recommendedjobs' in called_url

    @pytest.mark.asyncio
    async def test_zero_applied_still_continues(self, agent):
        """Applied 0/5 (no 'X out of Y' text) -> continue to try again."""
        result = await agent._handle_naukri_post_apply('CHATBOT_COMPLETE: 0/5')
        assert result is True
        assert agent.state.task_complete is False
        assert agent.metrics['applications_submitted'] == 0


# =============================================================================
# _handle_naukri_post_apply — target reached (stop)
# =============================================================================

class TestPostApplyTargetReached:
    @pytest.mark.asyncio
    async def test_exactly_5_stops(self, agent):
        """Applied 5/5 -> task complete, return False, no navigation."""
        result = await agent._handle_naukri_post_apply('CHATBOT_COMPLETE: 5/5')
        assert result is False
        assert agent.state.task_complete is True
        assert agent.metrics['applications_submitted'] == 5
        agent._page.goto.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_over_5_stops(self, agent):
        """Applied 7/5 (overshoot) -> task complete, return False."""
        result = await agent._handle_naukri_post_apply('CHATBOT_COMPLETE: 7/5')
        assert result is False
        assert agent.state.task_complete is True
        assert agent.metrics['applications_submitted'] == 7


# =============================================================================
# _handle_naukri_post_apply — malformed input (safe fallback)
# =============================================================================

class TestPostApplyMalformedInput:
    @pytest.mark.asyncio
    async def test_unparseable_string_falls_back_to_increment(self, agent):
        """Garbage string -> assume 1 applied, continue."""
        agent.metrics['applications_submitted'] = 0
        result = await agent._handle_naukri_post_apply('GARBAGE_RESULT')
        assert result is True
        assert agent.state.task_complete is False
        assert agent.metrics['applications_submitted'] == 1

    @pytest.mark.asyncio
    async def test_non_string_input_falls_back_to_increment(self, agent):
        """Non-string (e.g. True from legacy path) -> assume 1 applied, continue."""
        agent.metrics['applications_submitted'] = 2
        result = await agent._handle_naukri_post_apply(True)
        assert result is True
        assert agent.metrics['applications_submitted'] == 3


# =============================================================================
# Integration: simulate two-round flow (3 then 2)
# =============================================================================

class TestTwoRoundFlow:
    @pytest.mark.asyncio
    async def test_round_one_partial_then_round_two_complete(self, agent):
        """End-to-end: 3 jobs applied round 1 (continue), 2 more round 2 (stop at 5)."""
        # Round 1: 3 applied
        agent._page.evaluate = AsyncMock(return_value='CHATBOT_COMPLETE: 3/5')
        r1 = await agent._handle_naukri_post_apply('CHATBOT_COMPLETE: 3/5')
        assert r1 is True
        assert agent.metrics['applications_submitted'] == 3
        assert agent.state.task_complete is False

        # Round 2: 2 more -> cumulative 5
        r2 = await agent._handle_naukri_post_apply('CHATBOT_COMPLETE: 5/5')
        assert r2 is False
        assert agent.metrics['applications_submitted'] == 5
        assert agent.state.task_complete is True