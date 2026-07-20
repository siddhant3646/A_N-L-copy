"""
Tests for the Naukri "apply to 5 jobs across sections" flow.

Covers the fix for the bug where applying to fewer than 5 jobs on a page would
stop the task instead of navigating to the next section to apply to the
remaining jobs.

The core of the fix is two helper methods on SentinelAgent:
  - _resolve_naukri_completion(): parses "X out of Y" from the success page,
    updates the cumulative counter, and returns 'CHATBOT_COMPLETE: <N>/5'.
    When no "X out of Y" text is found, returns 'CHATBOT_NO_PROGRESS: <N>/5'
    so the caller can distinguish a real completion from a stale-state false
    positive.
  - _handle_naukri_post_apply(): decides whether to continue (need more jobs)
    or stop (target reached) based on that string. Includes a no-progress guard
    that breaks the infinite "applied N/5, need more, navigate, repeat" loop
    after self._naukri_no_progress_max consecutive stale rounds.
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
    async def test_no_count_text_returns_no_progress(self, agent):
        """When no 'X out of Y' text is found, returns CHATBOT_NO_PROGRESS (not COMPLETE)."""
        agent._page.evaluate = AsyncMock(return_value='CHATBOT_NO_PROGRESS: 0/5')
        result = await agent._resolve_naukri_completion()
        assert result == 'CHATBOT_NO_PROGRESS: 0/5'
        assert 'CHATBOT_NO_PROGRESS' in result

    @pytest.mark.asyncio
    async def test_returns_safe_default_when_page_missing(self, agent):
        """Without a page, returns a safe 'CHATBOT_NO_PROGRESS: 0/5' string."""
        agent._page = None
        result = await agent._resolve_naukri_completion()
        assert result == 'CHATBOT_NO_PROGRESS: 0/5'

    @pytest.mark.asyncio
    async def test_handles_evaluate_exception(self, agent):
        """If page.evaluate throws, returns safe default instead of propagating."""
        agent._page.evaluate = AsyncMock(side_effect=RuntimeError("page detached"))
        result = await agent._resolve_naukri_completion()
        assert result == 'CHATBOT_NO_PROGRESS: 0/5'


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
# _handle_naukri_post_apply — no-progress guard (breaks infinite loop)
# =============================================================================

class TestPostApplyNoProgressGuard:
    """Tests for the no-progress counter that breaks the infinite
    'applied N/5, need more, navigate, repeat' loop when the chatbot
    keeps false-completing without advancing the cumulative count."""

    @pytest.mark.asyncio
    async def test_no_progress_signal_increments_counter(self, agent):
        """CHATBOT_NO_PROGRESS signal increments the no-progress counter but
        still navigates and continues until the max is reached."""
        agent.metrics['applications_submitted'] = 4
        result = await agent._handle_naukri_post_apply('CHATBOT_NO_PROGRESS: 4/5')
        assert result is True
        assert agent.state.task_complete is False
        assert agent._naukri_no_progress_count == 1

    @pytest.mark.asyncio
    async def test_no_progress_signal_repeated_max_times_stops(self, agent):
        """After _naukri_no_progress_max consecutive no-progress rounds, the
        task is marked complete to break the infinite loop."""
        agent.metrics['applications_submitted'] = 4
        max_rounds = agent._naukri_no_progress_max

        for i in range(max_rounds - 1):
            result = await agent._handle_naukri_post_apply('CHATBOT_NO_PROGRESS: 4/5')
            assert result is True, f"round {i + 1} should continue"
            assert agent.state.task_complete is False
            assert agent._naukri_no_progress_count == i + 1

        # Final no-progress round should stop the task.
        result = await agent._handle_naukri_post_apply('CHATBOT_NO_PROGRESS: 4/5')
        assert result is False
        assert agent.state.task_complete is True
        assert agent._naukri_no_progress_count == 0  # reset after stopping

    @pytest.mark.asyncio
    async def test_same_count_complete_signal_also_triggers_no_progress(self, agent):
        """Even a CHATBOT_COMPLETE signal that doesn't advance the count past
        the previously recorded applications_submitted is treated as no-progress.
        This guards against stale 'CHATBOT_COMPLETE: 4/5' strings from a
        previous round being re-emitted without any new applications."""
        agent.metrics['applications_submitted'] = 4
        # Same count as before -> no progress.
        result = await agent._handle_naukri_post_apply('CHATBOT_COMPLETE: 4/5')
        assert result is True
        assert agent._naukri_no_progress_count == 1
        assert agent.state.task_complete is False

    @pytest.mark.asyncio
    async def test_real_progress_resets_no_progress_counter(self, agent):
        """When actual progress is made (count advances), the no-progress
        counter resets to 0 so a future stale round starts fresh."""
        agent.metrics['applications_submitted'] = 2
        agent._naukri_no_progress_count = 2  # simulate prior stale rounds

        result = await agent._handle_naukri_post_apply('CHATBOT_COMPLETE: 4/5')
        assert result is True
        assert agent._naukri_no_progress_count == 0
        assert agent.metrics['applications_submitted'] == 4

    @pytest.mark.asyncio
    async def test_no_progress_then_progress_then_no_progress_resets(self, agent):
        """Two no-progress rounds, then progress, then two more no-progress
        rounds should NOT stop the task (counter reset by the progress round)."""
        agent.metrics['applications_submitted'] = 3

        # Round 1: no progress
        r1 = await agent._handle_naukri_post_apply('CHATBOT_NO_PROGRESS: 3/5')
        assert r1 is True
        assert agent._naukri_no_progress_count == 1

        # Round 2: no progress
        r2 = await agent._handle_naukri_post_apply('CHATBOT_NO_PROGRESS: 3/5')
        assert r2 is True
        assert agent._naukri_no_progress_count == 2

        # Round 3: real progress (3 -> 4)
        r3 = await agent._handle_naukri_post_apply('CHATBOT_COMPLETE: 4/5')
        assert r3 is True
        assert agent._naukri_no_progress_count == 0
        assert agent.metrics['applications_submitted'] == 4

        # Round 4: no progress again — counter should be 1, not 3.
        r4 = await agent._handle_naukri_post_apply('CHATBOT_NO_PROGRESS: 4/5')
        assert r4 is True
        assert agent._naukri_no_progress_count == 1
        assert agent.state.task_complete is False


# =============================================================================
# _handle_naukri_post_apply — close-enough rule (one job failed in full batch)
# =============================================================================

class TestPostApplyCloseEnough:
    """Tests for the close-enough rule: if a full batch of 5 was selected but
    one job failed (4/5 applied), accept it and stop instead of applying to
    extra jobs just to hit exactly 5."""

    @pytest.mark.asyncio
    async def test_full_batch_one_failure_stops(self, agent):
        """Selected 5 jobs, 4 applied (1 failed) -> task complete."""
        agent._naukri_last_batch_size = 5
        result = await agent._handle_naukri_post_apply('CHATBOT_COMPLETE: 4/5')
        assert result is False
        assert agent.state.task_complete is True
        assert agent.metrics['applications_submitted'] == 4
        agent._page.goto.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_full_batch_zero_applied_does_not_stop(self, agent):
        """Selected 5 jobs but 0 applied -> not close-enough, continue trying."""
        agent._naukri_last_batch_size = 5
        result = await agent._handle_naukri_post_apply('CHATBOT_COMPLETE: 0/5')
        assert result is True
        assert agent.state.task_complete is False

    @pytest.mark.asyncio
    async def test_small_batch_four_applied_does_not_trigger_close_enough(self, agent):
        """Selected only 1 job, 4 applied cumulatively -> close-enough does NOT
        trigger because the batch was not a full 5. Should continue normally
        (or hit no-progress guard if stale)."""
        agent._naukri_last_batch_size = 1
        agent.metrics['applications_submitted'] = 4
        result = await agent._handle_naukri_post_apply('CHATBOT_COMPLETE: 4/5')
        # No progress (4 == 4) -> increments counter, continues
        assert result is True
        assert agent.state.task_complete is False
        assert agent._naukri_no_progress_count == 1

    @pytest.mark.asyncio
    async def test_full_batch_three_applied_does_not_trigger_close_enough(self, agent):
        """Selected 5 jobs but only 3 applied (2 failed) -> not close-enough,
        continue trying to reach 5."""
        agent._naukri_last_batch_size = 5
        result = await agent._handle_naukri_post_apply('CHATBOT_COMPLETE: 3/5')
        assert result is True
        assert agent.state.task_complete is False
        assert agent.metrics['applications_submitted'] == 3

    @pytest.mark.asyncio
    async def test_full_batch_five_applied_stops_normally(self, agent):
        """Selected 5 jobs, all 5 applied -> normal target-reached stop
        (not the close-enough path)."""
        agent._naukri_last_batch_size = 5
        result = await agent._handle_naukri_post_apply('CHATBOT_COMPLETE: 5/5')
        assert result is False
        assert agent.state.task_complete is True
        assert agent.metrics['applications_submitted'] == 5


# =============================================================================
# _parse_naukri_batch_size
# =============================================================================

class TestParseNaukriBatchSize:
    def test_parses_jobs_selected(self, agent):
        assert agent._parse_naukri_batch_size('NAUKRI_APPLY_CLICKED: 5 jobs selected') == 5

    def test_parses_one_job_selected(self, agent):
        assert agent._parse_naukri_batch_size('NAUKRI_APPLY_CLICKED: 1 jobs selected') == 1

    def test_parses_already_selected(self, agent):
        assert agent._parse_naukri_batch_size('NAUKRI_APPLY_CLICKED: 3 jobs already selected') == 3

    def test_parses_checkbox_format(self, agent):
        assert agent._parse_naukri_batch_size('CHECKBOX_CLICKED: 5/5') == 5

    def test_returns_zero_for_unparseable(self, agent):
        assert agent._parse_naukri_batch_size('NO_ACTION') == 0

    def test_returns_zero_for_non_string(self, agent):
        assert agent._parse_naukri_batch_size(None) == 0
        assert agent._parse_naukri_batch_size(42) == 0


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


# =============================================================================
# Integration: simulate the infinite-loop bug scenario from the logs
# =============================================================================

class TestInfiniteLoopBreak:
    """Reproduces the exact bug from the logs: chatbot false-completes with a
    stale '2' question text, _resolve_naukri_completion finds no 'X out of Y'
    text and returns CHATBOT_NO_PROGRESS, and the task should stop after
    _naukri_no_progress_max rounds instead of looping forever."""

    @pytest.mark.asyncio
    async def test_repeated_no_progress_stops_task(self, agent):
        """Simulate the log scenario: 4/5 applied, then repeated no-progress
        rounds. The task must stop after the configured max."""
        agent.metrics['applications_submitted'] = 4
        max_rounds = agent._naukri_no_progress_max

        for i in range(max_rounds):
            result = await agent._handle_naukri_post_apply('CHATBOT_NO_PROGRESS: 4/5')
            if i < max_rounds - 1:
                assert result is True, f"round {i + 1} should continue"
                assert agent.state.task_complete is False
            else:
                assert result is False, f"round {i + 1} should stop the task"
                assert agent.state.task_complete is True