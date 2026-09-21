import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from src.sentinel.agent import SentinelAgent


class TestInstahyreRandomSkills(unittest.TestCase):
    def setUp(self):
        self.agent = SentinelAgent()

    def test_selection_size_split_and_uniqueness(self):
        skills = self.agent._get_instahyre_skills()
        self.assertEqual(len(skills), 15)
        self.assertEqual(len(set(skills)), 15)

        languages = skills[: self.agent.INSTAHYRE_SKILL_LANGUAGES_COUNT]
        tools = skills[self.agent.INSTAHYRE_SKILL_LANGUAGES_COUNT :]

        self.assertEqual(len(languages), 8)
        self.assertEqual(len(tools), 7)
        for skill in languages:
            self.assertIn(skill, self.agent.INSTAHYRE_SKILL_LANGUAGES)
        for skill in tools:
            self.assertIn(skill, self.agent.INSTAHYRE_SKILL_TOOLS)

    def test_selection_is_stable_within_task(self):
        first = self.agent._get_instahyre_skills()
        second = self.agent._get_instahyre_skills()
        self.assertIs(first, second)
        self.assertEqual(first, second)

    def test_reset_clears_cached_selection(self):
        self.agent._get_instahyre_skills()
        self.assertIsNotNone(self.agent._instahyre_skills)

        self.agent.reset_per_task_state()
        self.assertIsNone(self.agent._instahyre_skills)

        refreshed = self.agent._get_instahyre_skills()
        self.assertEqual(len(refreshed), 15)

    def test_reset_produces_new_draw(self):
        with patch('src.sentinel.agent.random.sample') as mock_sample:
            mock_sample.side_effect = [
                ['L%d' % i for i in range(8)], ['T%d' % i for i in range(7)],
                ['X%d' % i for i in range(8)], ['Y%d' % i for i in range(7)],
            ]
            first = self.agent._get_instahyre_skills()
            self.agent.reset_per_task_state()
            second = self.agent._get_instahyre_skills()

        self.assertEqual(first[:8], ['L%d' % i for i in range(8)])
        self.assertEqual(second[:8], ['X%d' % i for i in range(8)])
        self.assertNotEqual(first, second)


class TestInstahyreSkillsInjection(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.agent = SentinelAgent()
        self.agent._task_description = "Apply to jobs on Instahyre"
        self.mock_page = AsyncMock()
        self.mock_page.url = "https://www.instahyre.com/candidate/opportunities/?matching=true"
        self.mock_page.evaluate = AsyncMock(return_value='NO_ACTION')
        self.agent._page = self.mock_page

    async def test_fallback_injects_skills_global(self):
        await self.agent._handle_scripted_fallback()

        injected = [
            call.args
            for call in self.mock_page.evaluate.await_args_list
            if len(call.args) >= 2
            and isinstance(call.args[0], str)
            and '__SENTINEL_INSTAHYRE_SKILLS__' in call.args[0]
        ]
        self.assertTrue(injected, "Skills global was not injected")
        payload = injected[-1][1]
        self.assertEqual(len(payload), 15)


if __name__ == '__main__':
    unittest.main()
