from difflib import SequenceMatcher
from typing import Dict, Any, List, Tuple, Optional
import re
from collections import defaultdict

from .pattern_loader import PatternLoader, get_pattern_answer
from .answer_validator import AnswerValidator


CATEGORY_KEYWORDS = {
    'salary': ['ctc', 'salary', 'compensation', 'package', 'lpa', 'inr', 'pay', 'cctc', 'ectc', 'per annum', 'annual'],
    'experience': ['experience', 'years', 'months', 'worked', 'tenure', 'yrs', 'exp', 'total exp'],
    'notice_period': ['notice', 'serving', 'join', 'availability', 'np', 'lwd', 'last working day'],
    'location': ['location', 'city', 'relocate', 'preferred location', 'based in', 'located in'],
    'skills': ['proficiency', 'rate', 'scale', 'tech stack', 'libraries', 'database', 'dsa', 'algorithms', 'knowledge'],
    'yes_no': ['willing', 'comfortable', 'open to', 'are you', 'do you', 'have you', 'can you', 'ok to', 'okay'],
    'work_mode': ['remote', 'hybrid', 'wfh', 'wfo', 'work from'],
    'availability': ['interview', 'available', 'join date', 'start date', 'joining'],
    'data_consent': ['consent', 'privacy', 'data', 'collect', 'store', 'process'],
    'education': ['degree', 'graduation', 'university', 'college', 'gpa', 'qualification', 'academic'],
    'personal_info': ['name', 'email', 'phone', 'address', 'gender', 'dob', 'date of birth'],
    'employment': ['current company', 'current organization', 'employer', 'designation', 'role', 'title'],
    'self_identification': ['disability', 'veteran', 'gender', 'race', 'ethnicity', 'identity'],
    'work_authorization': ['authorized', 'visa', 'work permit', 'legally', 'citizenship', 'sponsorship'],
}


class PatternMatcher:
    DEFAULT_THRESHOLD = 0.65

    def __init__(self, patterns: Dict[str, Any], threshold: float = DEFAULT_THRESHOLD):
        self.patterns = patterns
        self.threshold = threshold
        self._pattern_cache: Dict[str, List[str]] = {}
        self._category_index: Dict[str, List[str]] = defaultdict(list)
        self._build_index()

    def _build_index(self):
        if 'patterns' not in self.patterns:
            return
        for pattern_id, pattern_data in self.patterns['patterns'].items():
            strs = pattern_data.get('patterns', [])
            if strs:
                self._pattern_cache[pattern_id] = strs
                cat = pattern_data.get('category', 'unknown')
                self._category_index[cat].append(pattern_id)

    def _normalize(self, text: str) -> str:
        text = text.lower().strip()
        text = ' '.join(text.split())
        text = re.sub(r'[^\w\s]', '', text)
        return text

    def _similarity(self, a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio()

    def _detect_categories(self, question: str) -> List[Tuple[str, int]]:
        q = question.lower()
        scores = []
        for cat, keywords in CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in q)
            if score > 0:
                scores.append((cat, score))
        scores.sort(key=lambda x: -x[1])
        return scores

    def _passes_negative(self, pattern_data: Dict, question: str) -> bool:
        negs = pattern_data.get('negative_patterns', [])
        if not negs:
            return True
        q = question.lower()
        for neg in negs:
            if neg.lower() in q:
                return False
        return True

    def fuzzy_match(self, question: str, input_type: str = None) -> Tuple[Optional[str], float]:
        if not question:
            return None, 0.0

        normalized_q = self._normalize(question)

        # Tier 1: Exact/substring match (fast, reliable)
        result = self._tier1_match(normalized_q, question, input_type)
        if result[0]:
            return result

        # Tier 2: Category-scoped fuzzy match
        result = self._tier2_match(normalized_q, question, input_type)
        if result[0]:
            return result

        # Tier 3: Global fuzzy fallback
        result = self._tier3_match(normalized_q, question, input_type)
        return result

    def _tier1_match(self, normalized_q: str, question: str, input_type: str) -> Tuple[Optional[str], float]:
        best_id = None
        best_priority = -1
        best_len = -1

        for pattern_id, pattern_data in self.patterns['patterns'].items():
            if not self._passes_negative(pattern_data, question):
                continue
            for pstr in pattern_data.get('patterns', []):
                norm_p = self._normalize(pstr)
                if norm_p == normalized_q:
                    priority = pattern_data.get('priority', 5)
                    if priority > best_priority or (priority == best_priority and len(norm_p) > best_len):
                        best_id = pattern_id
                        best_priority = priority
                        best_len = len(norm_p)
                elif norm_p in normalized_q:
                    priority = pattern_data.get('priority', 5)
                    if priority > best_priority or (priority == best_priority and len(norm_p) > best_len):
                        best_id = pattern_id
                        best_priority = priority
                        best_len = len(norm_p)

        if best_id:
            answer = self._get_answer(best_id, input_type)
            cat = self.patterns['patterns'][best_id].get('category', '')
            is_valid, _ = AnswerValidator.validate(answer or '', cat, question)
            confidence = 0.98 if is_valid else 0.85
            return answer, confidence

        return None, 0.0

    def _tier2_match(self, normalized_q: str, question: str, input_type: str) -> Tuple[Optional[str], float]:
        detected_cats = self._detect_categories(question)
        if not detected_cats:
            return None, 0.0

        best_id = None
        best_score = 0.0
        best_priority = -1

        for cat, cat_score in detected_cats:
            pattern_ids = self._category_index.get(cat, [])
            for pid in pattern_ids:
                pdata = self.patterns['patterns'].get(pid, {})
                if not self._passes_negative(pdata, question):
                    continue
                for pstr in pdata.get('patterns', []):
                    norm_p = self._normalize(pstr)
                    sim = self._similarity(normalized_q, norm_p)
                    if norm_p in normalized_q or normalized_q in norm_p:
                        sim = max(sim, 0.85)
                    if sim >= self.threshold:
                        priority = pdata.get('priority', 5)
                        if sim > best_score or (sim == best_score and priority > best_priority):
                            best_score = sim
                            best_id = pid
                            best_priority = priority

        if best_id:
            answer = self._get_answer(best_id, input_type)
            return answer, best_score

        return None, 0.0

    def _tier3_match(self, normalized_q: str, question: str, input_type: str) -> Tuple[Optional[str], float]:
        best_id = None
        best_score = 0.0
        best_priority = -1

        for pattern_id, pattern_data in self.patterns['patterns'].items():
            if not self._passes_negative(pattern_data, question):
                continue
            for pstr in pattern_data.get('patterns', []):
                norm_p = self._normalize(pstr)
                sim = self._similarity(normalized_q, norm_p)
                if norm_p in normalized_q or normalized_q in norm_p:
                    sim = max(sim, 0.85)
                if sim >= self.threshold:
                    priority = pattern_data.get('priority', 5)
                    if sim > best_score or (sim == best_score and priority > best_priority):
                        best_score = sim
                        best_id = pattern_id
                        best_priority = priority

        if best_id:
            answer = self._get_answer(best_id, input_type)
            return answer, best_score

        return None, 0.0

    def _get_answer(self, pattern_id: str, input_type: str = None) -> Optional[str]:
        pattern = self.patterns['patterns'].get(pattern_id)
        if not pattern:
            return None
        if input_type:
            input_type = input_type.lower().strip()
            itd = pattern.get('input_type_defaults', {})
            if itd and input_type in itd:
                return itd[input_type]
            if input_type == 'number':
                return pattern.get('numeric_default') or pattern.get('default')
        return pattern.get('default')

    def match_with_details(self, question: str) -> Dict[str, Any]:
        answer, confidence = self.fuzzy_match(question)
        return {
            'question': question,
            'answer': answer,
            'confidence': confidence,
            'matched': answer is not None
        }

    def get_all_matches(self, question: str, min_confidence: float = 0.5) -> List[Tuple[str, str, float]]:
        matches = []
        normalized_q = self._normalize(question)
        for pattern_id, pattern_strings in self._pattern_cache.items():
            pattern = self.patterns['patterns'].get(pattern_id)
            if not pattern:
                continue
            best_sim = 0.0
            for pstr in pattern_strings:
                normalized_p = self._normalize(pstr)
                sim = self._similarity(normalized_q, normalized_p)
                best_sim = max(best_sim, sim)
            if best_sim >= min_confidence:
                matches.append((pattern_id, pattern.get('default', ''), best_sim))
        matches.sort(key=lambda x: x[2], reverse=True)
        return matches

    def update_patterns(self, patterns: Dict[str, Any]):
        self.patterns = patterns
        self._pattern_cache.clear()
        self._category_index.clear()
        self._build_index()


def create_matcher(json_path: Optional[str] = None, threshold: float = PatternMatcher.DEFAULT_THRESHOLD) -> PatternMatcher:
    loader = PatternLoader(json_path)
    patterns = loader.load()
    return PatternMatcher(patterns, threshold)