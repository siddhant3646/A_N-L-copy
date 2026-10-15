import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..')))

from src.sentinel.agent import SentinelAgent


class TestInstahyreRandomSkills(unittest.TestCase):
    def setUp(self):
        self.agent = SentinelAgent()

    def test_main_task_returns_static_skills(self):
        """Main search task should return the static 15-skill high-yield list."""
        self.agent._task_description = "Configure job search filters on Instahyre and apply to 5 jobs"
        skills = self.agent._get_instahyre_skills()
        self.assertEqual(skills, self.agent.INSTAHYRE_STATIC_SKILLS)
        self.assertEqual(len(skills), 15)
        self.assertEqual(len(set(skills)), 15)

        languages = skills[: self.agent.INSTAHYRE_SKILL_LANGUAGES_COUNT]
        frameworks = skills[self.agent.INSTAHYRE_SKILL_LANGUAGES_COUNT :]

        self.assertEqual(languages, self.agent.INSTAHYRE_STATIC_LANGUAGES)
        self.assertEqual(frameworks, self.agent.INSTAHYRE_STATIC_FRAMEWORKS)
        self.assertEqual(len(languages), 8)
        self.assertEqual(len(frameworks), 7)

    def test_intersession_selection_size_split_and_uniqueness(self):
        """Intersession task should return a random 8 languages + 7 frameworks from the 30/30 pools."""
        self.agent._task_description = "Apply to 20 jobs on Instahyre during the intersession period"
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
        self.agent._task_description = "Apply to 20 jobs on Instahyre during intersession"
        first = self.agent._get_instahyre_skills()
        second = self.agent._get_instahyre_skills()
        self.assertIs(first, second)
        self.assertEqual(first, second)

    def test_reset_clears_cached_selection(self):
        self.agent._task_description = "Apply to 20 jobs on Instahyre during intersession"
        self.agent._get_instahyre_skills()
        self.assertIsNotNone(self.agent._instahyre_skills)

        self.agent.reset_per_task_state()
        self.assertIsNone(self.agent._instahyre_skills)

        refreshed = self.agent._get_instahyre_skills(is_intersession=True)
        self.assertEqual(len(refreshed), 15)

    def test_reset_produces_new_draw(self):
        self.agent._task_description = "Apply to 20 jobs on Instahyre during intersession"
        with patch('src.sentinel.agent.random.sample') as mock_sample:
            mock_sample.side_effect = [
                ['L%d' % i for i in range(8)], ['T%d' % i for i in range(7)],
                ['X%d' % i for i in range(8)], ['Y%d' % i for i in range(7)],
            ]
            first = self.agent._get_instahyre_skills()
            self.agent.reset_per_task_state()
            self.agent._task_description = "Apply to 20 jobs on Instahyre during intersession"
            second = self.agent._get_instahyre_skills()

        self.assertEqual(first[:8], ['L%d' % i for i in range(8)])
        self.assertEqual(second[:8], ['X%d' % i for i in range(8)])
        self.assertNotEqual(first, second)

    def test_skills_pool_completeness_and_uniqueness(self):
        """Verify Top 30 Languages and Top 30 Frameworks pools and zero overlap."""
        self.assertEqual(len(self.agent.INSTAHYRE_SKILL_LANGUAGES), 30)
        self.assertEqual(len(set(self.agent.INSTAHYRE_SKILL_LANGUAGES)), 30)
        self.assertEqual(len(self.agent.INSTAHYRE_SKILL_TOOLS), 30)
        self.assertEqual(len(set(self.agent.INSTAHYRE_SKILL_TOOLS)), 30)

        # Zero overlap between languages and frameworks pools
        overlap = set(self.agent.INSTAHYRE_SKILL_LANGUAGES) & set(self.agent.INSTAHYRE_SKILL_TOOLS)
        self.assertEqual(overlap, set())

        # Alias verification
        self.assertIs(self.agent.INSTAHYRE_SKILL_FRAMEWORKS, self.agent.INSTAHYRE_SKILL_TOOLS)

        # Static skills verification
        self.assertEqual(len(self.agent.INSTAHYRE_STATIC_LANGUAGES), 8)
        self.assertEqual(len(self.agent.INSTAHYRE_STATIC_FRAMEWORKS), 7)
        self.assertEqual(len(self.agent.INSTAHYRE_STATIC_SKILLS), 15)
        self.assertTrue(set(self.agent.INSTAHYRE_STATIC_LANGUAGES).issubset(set(self.agent.INSTAHYRE_SKILL_LANGUAGES)))
        self.assertTrue(set(self.agent.INSTAHYRE_STATIC_FRAMEWORKS).issubset(set(self.agent.INSTAHYRE_SKILL_TOOLS)))


class TestInstahyreSkillsInjection(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.agent = SentinelAgent()
        self.mock_page = AsyncMock()
        self.mock_page.url = "https://www.instahyre.com/candidate/opportunities/?matching=true"
        self.mock_page.evaluate = AsyncMock(return_value='NO_ACTION')
        self.agent._page = self.mock_page

    async def test_fallback_injects_skills_global_main_task(self):
        self.agent._task_description = "Apply to jobs on Instahyre"
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
        self.assertEqual(payload, self.agent.INSTAHYRE_STATIC_SKILLS)

    async def test_fallback_injects_skills_global_intersession_task(self):
        self.agent._task_description = "Apply to 20 jobs on Instahyre during intersession"
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
        for skill in payload[:8]:
            self.assertIn(skill, self.agent.INSTAHYRE_SKILL_LANGUAGES)
        for skill in payload[8:]:
            self.assertIn(skill, self.agent.INSTAHYRE_SKILL_TOOLS)


if __name__ == '__main__':
    unittest.main()
