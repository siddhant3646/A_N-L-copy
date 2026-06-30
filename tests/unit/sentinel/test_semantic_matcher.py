from src.sentinel.semantic_matcher import SemanticQuestionMatcher


class TestSemanticQuestionMatcherInit:
    def test_init(self):
        matcher = SemanticQuestionMatcher()
        assert matcher.INTENTS is not None
        assert len(matcher.INTENTS) > 0
        assert matcher.EQUIVALENT_QUESTIONS is not None


class TestClassifyIntent:
    def setup_method(self):
        self.matcher = SemanticQuestionMatcher()

    def test_experience_duration_intent(self):
        intent, confidence = self.matcher.classify_intent("How many years of experience do you have?")
        assert intent == "experience_duration"
        assert confidence > 0.7

    def test_salary_current_intent(self):
        intent, confidence = self.matcher.classify_intent("What is your current salary?")
        assert intent == "salary_current"
        assert confidence > 0.7

    def test_salary_expected_intent(self):
        intent, confidence = self.matcher.classify_intent("What is your expected CTC?")
        assert intent == "salary_expected"
        assert confidence > 0.7

    def test_notice_period_intent(self):
        intent, confidence = self.matcher.classify_intent("What is your notice period?")
        assert intent == "notice_period"
        assert confidence > 0.7

    def test_empty_question(self):
        intent, confidence = self.matcher.classify_intent("")
        assert intent is None
        assert confidence == 0.0

    def test_none_question(self):
        intent, confidence = self.matcher.classify_intent(None)
        assert intent is None
        assert confidence == 0.0

    def test_unrelated_question(self):
        intent, confidence = self.matcher.classify_intent("What is your favorite color?")
        assert confidence < 0.5


class TestGetAnswerForIntent:
    def setup_method(self):
        self.matcher = SemanticQuestionMatcher()

    def test_existing_intent(self):
        answer = self.matcher.get_answer_for_intent("salary_current")
        assert answer == "23 LPA"

    def test_non_existing_intent(self):
        answer = self.matcher.get_answer_for_intent("nonexistent")
        assert answer is None


class TestGetCategoryForIntent:
    def setup_method(self):
        self.matcher = SemanticQuestionMatcher()

    def test_existing_intent(self):
        cat = self.matcher.get_category_for_intent("experience_duration")
        assert cat == "experience"

    def test_non_existing_intent(self):
        cat = self.matcher.get_category_for_intent("nonexistent")
        assert cat is None


class TestFindEquivalenceClass:
    def setup_method(self):
        self.matcher = SemanticQuestionMatcher()

    def test_found_equivalence(self):
        eq = self.matcher.find_equivalence_class("What is your current salary?")
        assert eq is not None

    def test_not_found(self):
        eq = self.matcher.find_equivalence_class("completely unrelated question xyz")
        assert eq is None or len(eq) > 0


class TestGetEquivalentQuestions:
    def setup_method(self):
        self.matcher = SemanticQuestionMatcher()

    def test_returns_list(self):
        eqs = self.matcher.get_equivalent_questions("What is your current salary?")
        assert isinstance(eqs, list)


class TestAreSemanticallyEquivalent:
    def setup_method(self):
        self.matcher = SemanticQuestionMatcher()

    def test_same_intent(self):
        assert self.matcher.are_semantically_equivalent(
            "What is your current salary?",
            "How much do you earn currently?"
        )

    def test_different_intents(self):
        assert not self.matcher.are_semantically_equivalent(
            "What is your salary?",
            "What is your notice period?"
        )


class TestExtractEntities:
    def setup_method(self):
        self.matcher = SemanticQuestionMatcher()

    def test_extract_technologies(self):
        entities = self.matcher.extract_entities("Do you have python and aws experience?")
        assert "technologies" in entities
        assert "python" in entities["technologies"]
        assert "aws" in entities["technologies"]

    def test_extract_numbers(self):
        entities = self.matcher.extract_entities("Do you have 5 years of experience?")
        assert "numbers" in entities
        assert "5" in entities["numbers"]

    def test_extract_range(self):
        entities = self.matcher.extract_entities("Experience between 3-5 years")
        assert "range" in entities

    def test_empty_question(self):
        entities = self.matcher.extract_entities("")
        assert entities == {}


class TestGetAllKeywordsForIntent:
    def setup_method(self):
        self.matcher = SemanticQuestionMatcher()

    def test_existing_intent(self):
        keywords = self.matcher.get_all_keywords_for_intent("salary_current")
        assert len(keywords) > 0
        assert "current salary" in keywords

    def test_nonexistent_intent(self):
        keywords = self.matcher.get_all_keywords_for_intent("nonexistent")
        assert keywords == []


class TestAddCustomIntent:
    def setup_method(self):
        self.matcher = SemanticQuestionMatcher()

    def test_add_custom_intent(self):
        self.matcher.add_custom_intent(
            "custom_test", ["test keyword"], "test answer", "test"
        )
        assert "custom_test" in self.matcher.INTENTS
        assert self.matcher.INTENTS["custom_test"]["answer"] == "test answer"

    def test_add_equivalent_questions_new(self):
        self.matcher.add_equivalent_questions("new_class", ["q1", "q2"])
        assert "new_class" in self.matcher.EQUIVALENT_QUESTIONS

    def test_add_equivalent_questions_existing(self):
        first_len = len(self.matcher.EQUIVALENT_QUESTIONS.get("salary_questions", []))
        self.matcher.add_equivalent_questions("salary_questions", ["extra question"])
        assert len(self.matcher.EQUIVALENT_QUESTIONS["salary_questions"]) > first_len
