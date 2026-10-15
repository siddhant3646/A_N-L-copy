"""Regression tests for the human-like Indeed search + filter flow.

The Indeed handler must reach a filtered results page the way a person would:
open the homepage, type the role into ``#text-input-what``, type the location
into ``#text-input-where``, click "Find jobs", then turn on the "Easily apply"
filter through its options popup. The previous direct-to-search-URL /
``sc=0kf:attr(DSQF7)`` facet path surfaced no in-site jobs and is gone.
"""

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from src.sentinel.agent import SentinelAgent


class _Locator:
    def __init__(self, page, selector):
        self.page = page
        self.selector = selector

    @property
    def first(self):
        return self

    @property
    def last(self):
        return self

    async def count(self):
        return 1 if self.selector in self.page.present else 0

    async def is_visible(self):
        return self.selector in self.page.present

    async def scroll_into_view_if_needed(self, **kwargs):
        pass

    async def click(self, **kwargs):
        self.page.clicks.append(self.selector)
        handler = self.page.on_click.get(self.selector)
        if handler:
            handler(self.page)

    async def fill(self, value):
        self.page.fills.append((self.selector, value))

    async def press_sequentially(self, text, delay=0):
        self.page.typed.append((self.selector, text))

    async def press(self, key):
        self.page.pressed.append((self.selector, key))

    async def get_attribute(self, name):
        return self.page.attrs.get((self.selector, name))


class _Page:
    def __init__(self, url=''):
        self.url = url
        self.present = set()
        self.clicks = []
        self.fills = []
        self.typed = []
        self.pressed = []
        self.attrs = {}
        self.on_click = {}
        self.gotos = []

    def locator(self, selector):
        return _Locator(self, selector)

    async def goto(self, url, **kwargs):
        self.gotos.append(url)
        self.url = url

    async def wait_for_selector(self, selector, **kwargs):
        for part in selector.split(','):
            if part.strip() in self.present:
                return part.strip()
        return None

    async def wait_for_load_state(self, *args, **kwargs):
        return None

    async def evaluate(self, expression, arg=None):
        return None


class TestIndeedSearchFlow(unittest.TestCase):
    def setUp(self):
        self.agent = SentinelAgent()

    def test_search_from_home_types_role_and_location_then_submits(self):
        # The page is already showing Indeed's search form: the handler must
        # reuse it (no re-navigation) instead of loading the homepage again.
        page = _Page(url=self.agent._INDEED_HOME_URL)
        page.present = {
            '#text-input-what',
            '#text-input-where',
            'button.yosegi-InlineWhatWhere-primaryButton',
        }
        with patch.dict(os.environ, {
            'INDEED_SEARCH_QUERY': 'React Developer',
            'INDEED_SEARCH_LOCATION': 'Pune, Maharashtra',
        }, clear=False), \
             patch.object(self.agent, '_indeed_dismiss_overlays', AsyncMock()), \
             patch.object(self.agent, '_human_mouse_move', AsyncMock()), \
             patch('src.sentinel.agent.asyncio.sleep', AsyncMock()):
            url = asyncio.run(self.agent._indeed_search_from_home(page))

        typed = dict(page.typed)
        self.assertEqual(typed.get('#text-input-what'), 'React Developer')
        self.assertEqual(typed.get('#text-input-where'), 'Pune, Maharashtra')
        self.assertIn('button.yosegi-InlineWhatWhere-primaryButton', page.clicks)
        # Reused the already-loaded form; no redundant homepage navigation.
        self.assertEqual(page.gotos, [])
        self.assertEqual(url, self.agent._INDEED_HOME_URL)

    def test_search_from_home_navigates_when_form_absent(self):
        page = _Page(url='about:blank')
        base_goto = page.goto

        async def _goto_and_render(url, **kwargs):
            await base_goto(url, **kwargs)
            page.present.update({
                '#text-input-what',
                '#text-input-where',
                'button.yosegi-InlineWhatWhere-primaryButton',
            })

        page.goto = _goto_and_render  # type: ignore[assignment]

        with patch.dict(os.environ, {
            'INDEED_SEARCH_QUERY': 'Java Developer',
            'INDEED_SEARCH_LOCATION': 'Pune, Maharashtra',
        }, clear=False), \
             patch.object(self.agent, '_indeed_dismiss_overlays', AsyncMock()), \
             patch.object(self.agent, '_human_mouse_move', AsyncMock()), \
             patch('src.sentinel.agent.asyncio.sleep', AsyncMock()):
            url = asyncio.run(self.agent._indeed_search_from_home(page))

        self.assertEqual(page.gotos, [self.agent._INDEED_HOME_URL])
        self.assertEqual(dict(page.typed).get('#text-input-what'), 'Java Developer')
        self.assertIn('button.yosegi-InlineWhatWhere-primaryButton', page.clicks)
        self.assertEqual(url, self.agent._INDEED_HOME_URL)

    def test_dismiss_overlays_js_ignores_navigation_drawer_and_hidden_close(self):
        # Regression: Indeed's off-canvas primary navigation is a
        # div[role="dialog"] whose hidden "Close" button blanked the tab. The
        # dismissal script must skip navigation/menu dialogs and only click
        # visible close controls.
        page = AsyncMock()
        page.url = 'https://in.indeed.com/'
        with patch('src.sentinel.agent.asyncio.sleep', AsyncMock()):
            asyncio.run(self.agent._indeed_dismiss_overlays(page))

        page.evaluate.assert_awaited_once()
        js = page.evaluate.await_args.args[0]
        self.assertIn('gnav-burger-menu-state--init', js)
        self.assertIn('navigation', js)
        self.assertIn("aria.includes('menu')", js)
        self.assertIn('getClientRects', js)

    def test_easily_filter_selects_option_and_updates(self):
        page = _Page()
        page.present = {
            'button[aria-label="Easily apply filter"]',
            'li[data-testid="selection-pill-option-1"]',
            'button:has-text("Update")',
        }
        with patch.object(self.agent, '_human_mouse_move', AsyncMock()), \
             patch('src.sentinel.agent.asyncio.sleep', AsyncMock()):
            ok = asyncio.run(self.agent._indeed_apply_easily_filter(page))

        self.assertTrue(ok)
        self.assertIn('button[aria-label="Easily apply filter"]', page.clicks)
        self.assertIn('li[data-testid="selection-pill-option-1"]', page.clicks)
        self.assertIn('button:has-text("Update")', page.clicks)

    def test_prepare_results_searches_when_not_on_results_page(self):
        page = _Page(url=self.agent._INDEED_HOME_URL)

        async def _search(p):
            p.url = 'https://in.indeed.com/jobs?q=react+developer'
            return p.url

        with patch.dict(os.environ, {'INDEED_SEARCH_URL': ''}, clear=False), \
             patch.object(self.agent, '_indeed_search_from_home', AsyncMock(side_effect=_search)) as m_search, \
             patch.object(self.agent, '_indeed_apply_easily_filter', AsyncMock(return_value=True)) as m_filter:
            seed = asyncio.run(self.agent._indeed_prepare_results(page))

        m_search.assert_awaited_once()
        m_filter.assert_awaited_once()
        self.assertEqual(seed, 'https://in.indeed.com/jobs?q=react+developer')

    def test_prepare_results_honours_explicit_search_url(self):
        page = _Page(url='about:blank')
        with patch.dict(os.environ, {
            'INDEED_SEARCH_URL': 'https://in.indeed.com/jobs?q=Java',
        }, clear=False), \
             patch('src.sentinel.agent.asyncio.sleep', AsyncMock()):
            seed = asyncio.run(self.agent._indeed_prepare_results(page))

        self.assertEqual(page.url, 'https://in.indeed.com/jobs?q=Java')
        self.assertEqual(seed, 'https://in.indeed.com/jobs?q=Java')

    def test_stealth_installs_init_script_and_patches_document(self):
        page = AsyncMock()
        asyncio.run(self.agent._indeed_apply_stealth(page))
        page.add_init_script.assert_awaited_once()
        page.evaluate.assert_awaited_once()


class TestIndeedRadioAlignment(unittest.TestCase):
    """The generic matcher can return a value that is not among the offered
    radio options (e.g. ``'15'`` for an Opt In/Opt Out consent question). For
    yes/no and consent questions the handler must fall back to the affirmative
    option so required screening questions actually get answered.
    """

    def setUp(self):
        self.agent = SentinelAgent()

    def align(self, q, opts, ans):
        return self.agent._indeed_align_radio_answer(q, opts, ans)

    def test_plain_yes_no_answer_is_preserved(self):
        self.assertEqual(
            self.align('Are you at least 18 years of age?', ['Yes', 'No'], 'Yes'),
            'Yes',
        )

    def test_consent_question_falls_back_to_opt_in(self):
        # Regression: this previously left the radio blank (answer '15' matched
        # no option), stalling the whole SmartApply flow.
        self.assertEqual(
            self.align(
                'To make our hiring process faster and more efficient, Genpact '
                'uses artificial intelligence (AI) to help match your skills.',
                ['Opt In', 'Opt Out'],
                '15',
            ),
            'Opt In',
        )

    def test_future_roles_question_falls_back_to_yes(self):
        self.assertEqual(
            self.align(
                'In case you are not selected for the job you applied for; would '
                'you like to be considered for future roles at Genpact?',
                ['Yes', 'No'],
                'Software Engineer 2 (SDE-2)',
            ),
            'Yes',
        )

    def test_negative_answer_maps_to_no(self):
        self.assertEqual(
            self.align('Are you willing to relocate?', ['Yes', 'No'], 'No'),
            'No',
        )

    def test_exact_option_match_wins_for_non_binary_questions(self):
        self.assertEqual(
            self.align('Rate your Java skill', ['1', '2', '3', '4', '5'], '4'),
            '4',
        )

    def test_unmatched_non_binary_answer_is_left_untouched(self):
        # A range/salary question must not be coerced to a yes/no option.
        self.assertEqual(
            self.align('How many years of experience?', ['0-1 Years', '1-3 Years', '3-5 Years'], '4.2'),
            '4.2',
        )


class TestIndeedInputAnswerFormatting(unittest.TestCase):
    """Indeed renders "When are you available to start?" as a masked date box
    (``placeholder="DD/MM/YYYY"`` on the India site). The generic matcher
    returns human answers such as ``"15 Days"`` which the date mask rejects,
    leaving the required field invalid and Continue stalled with
    "Answer this question to continue." forever.
    """

    def setUp(self):
        self.agent = SentinelAgent()

    def fmt(self, ans, ph='DD/MM/YYYY', it='text'):
        return self.agent._indeed_format_input_answer(ans, ph, it)

    def test_day_count_becomes_ddmmyyyy_date(self):
        from datetime import datetime, timedelta
        out = self.fmt('15 Days')
        expected = (datetime.now() + timedelta(days=15)).strftime('%d/%m/%Y')
        self.assertEqual(out, expected)
        self.assertRegex(out, r'^\d{2}/\d{2}/\d{4}$')

    def test_date_is_rendered_in_placeholder_order(self):
        self.assertEqual(self.fmt('25/09/2026'), '25/09/2026')
        self.assertEqual(self.fmt('25/09/2026', 'MM/DD/YYYY'), '09/25/2026')
        self.assertEqual(self.fmt('2026-09-25', 'DD/MM/YYYY'), '25/09/2026')

    def test_immediate_maps_to_today(self):
        from datetime import datetime
        self.assertEqual(self.fmt('Immediate'), datetime.now().strftime('%d/%m/%Y'))

    def test_non_date_field_is_untouched(self):
        self.assertEqual(self.fmt('Java', ph='', it='text'), 'Java')
        self.assertEqual(self.fmt('4.2 Years', ph='Enter years', it='text'), '4.2 Years')


class TestIndeedCheckboxQuestions(unittest.TestCase):
    """Multi-select (checkbox) questions such as "Please share your shift
    preference" are required on SmartApply. The scanner used to look only for
    text/select/radio inputs, so these groups were never answered, the required
    field stayed empty, and Continue never enabled — stalling the whole flow at
    ``questions/2`` ("No advance or submit control found"). These tests lock in
    the detection + dispatch (and that a group is ticked even when the pattern
    engine returns no answer).
    """

    def setUp(self):
        self.agent = SentinelAgent()
        self.agent._current_platform = 'indeed'

    @staticmethod
    def _checkbox_question():
        return [{
            'qid': 'q_cb',
            'question': 'Please share your shift preference',
            'hasSelect': False,
            'hasRadios': False,
            'hasCheckboxes': True,
            'hasInput': False,
            'options': [
                {'value': 'v0', 'text': 'Night Job', 'checkbox': True},
                {'value': 'v1', 'text': 'Day Job', 'checkbox': True},
                {'value': 'v2', 'text': 'Flex Job', 'checkbox': True},
            ],
        }]

    def test_checkbox_group_is_dispatched_to_checkbox_setter(self):
        frame = AsyncMock()
        frame.evaluate = AsyncMock(return_value=self._checkbox_question())
        with patch.object(self.agent, '_indeed_set_checkboxes', new=AsyncMock()) as cb, \
                patch.object(self.agent, '_indeed_set_radio', new=AsyncMock()) as rad, \
                patch.object(self.agent, '_indeed_set_text', new=AsyncMock()) as txt:
            asyncio.run(self.agent._indeed_answer_questions(frame))
        # NOTE: keep assertions outside the context manager.
        cb.assert_awaited_once()
        self.assertEqual(cb.await_args.args[1], 'q_cb')
        rad.assert_not_awaited()
        txt.assert_not_awaited()

    def test_checkbox_group_answered_even_without_pattern_answer(self):
        frame = AsyncMock()
        frame.evaluate = AsyncMock(return_value=self._checkbox_question())
        with patch.object(self.agent, '_fuzzy_match_question', return_value=(None, 0.0)), \
                patch.object(self.agent, '_indeed_set_checkboxes', new=AsyncMock()) as cb:
            asyncio.run(self.agent._indeed_answer_questions(frame))
        cb.assert_awaited_once()

    def test_set_checkboxes_clicks_matching_label(self):
        picked = ('Day Job',)

        async def _evaluate(expr, arg=None):
            return picked[0]

        frame = AsyncMock()
        frame.evaluate = _evaluate
        frame.locator = lambda sel: _Locator(_Page(), sel)
        asyncio.run(self.agent._indeed_set_checkboxes(
            frame, 'q_cb', 'Please share your shift preference',
            ['Night Job', 'Day Job', 'Flex Job'], 'Day Shift'))


if __name__ == '__main__':
    unittest.main()
