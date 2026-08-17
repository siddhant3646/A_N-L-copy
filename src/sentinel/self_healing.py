"""
Self-Healing Module - Failure recovery and persistent learning.

This module provides:
1. Failure logging with full context
2. Pattern mutation and learning from corrections
3. Recovery strategies (try alternatives, suggest corrections)
4. Persistent storage for learned patterns
"""

import json
import os
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
import re


@dataclass
class FailureRecord:
    timestamp: str
    question: str
    attempted_answer: str
    input_type: str
    options: List[str]
    platform: str
    url: str
    error_type: str
    fingerprint: str = ""
    
    def __post_init__(self):
        if not self.fingerprint:
            self.fingerprint = self._create_fingerprint()
    
    def _create_fingerprint(self) -> str:
        normalized = re.sub(r'[^\w\s]', '', self.question.lower())
        return hashlib.md5(normalized.encode()).hexdigest()[:16]


@dataclass
class LearnedPattern:
    pattern_id: str
    question_patterns: List[str]
    answer: str
    option_mappings: Dict[str, List[str]]
    confidence: float
    learned_from: str
    created_at: str
    times_used: int = 0
    times_succeeded: int = 0
    
    @property
    def success_rate(self) -> float:
        if self.times_used == 0:
            return 0.0
        return self.times_succeeded / self.times_used


@dataclass
class RecoveryResult:
    success: bool
    answer: str
    matched_option: Optional[str]
    strategy: str
    confidence: float
    message: str


class FailureLogger:
    """Logs and analyzes failures."""
    
    def __init__(self, log_path: str = None):
        if log_path is None:
            log_path = os.path.expanduser("~/Desktop/sentinel_errors/failure_log.jsonl")
        self.log_path = log_path
        # In-memory fingerprint -> records index. Avoids re-reading/parsing the
        # entire log file on every get_similar_failures() call (which previously
        # loaded all FailureRecord objects each time).
        self._index: Dict[str, List[FailureRecord]] = {}
        self._index_loaded = False
        self._ensure_dir()
    
    def _ensure_dir(self):
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
    
    def _load_index(self):
        """Load the failure log into the in-memory fingerprint index once."""
        if self._index_loaded:
            return
        self._index_loaded = True
        try:
            if os.path.exists(self.log_path):
                with open(self.log_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        try:
                            data = json.loads(line)
                            record = FailureRecord(**data)
                            self._index.setdefault(record.fingerprint, []).append(record)
                        except (json.JSONDecodeError, TypeError):
                            continue
        except Exception:
            pass
    
    def log_failure(
        self,
        question: str,
        attempted_answer: str,
        input_type: str,
        options: List[str],
        platform: str,
        url: str,
        error_type: str
    ) -> FailureRecord:
        record = FailureRecord(
            timestamp=datetime.now().isoformat(),
            question=question,
            attempted_answer=attempted_answer,
            input_type=input_type,
            options=options or [],
            platform=platform,
            url=url,
            error_type=error_type
        )
        
        try:
            with open(self.log_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(asdict(record)) + '\n')
            # Update in-memory index if it has been loaded
            if self._index_loaded:
                self._index.setdefault(record.fingerprint, []).append(record)
        except Exception as e:
            print(f"⚠️ Failed to log failure: {e}")
        
        return record
    
    def get_similar_failures(self, question: str, limit: int = 5) -> List[FailureRecord]:
        fingerprint = hashlib.md5(
            re.sub(r'[^\w\s]', '', question.lower()).encode()
        ).hexdigest()[:16]
        
        self._load_index()
        failures = self._index.get(fingerprint, [])
        return failures[-limit:]


class LearningStore:
    """Persistent storage for learned patterns."""
    
    def __init__(self, storage_path: str = None):
        if storage_path is None:
            storage_path = os.path.expanduser("~/Desktop/sentinel_errors/learned_patterns.json")
        self.storage_path = storage_path
        self.patterns: Dict[str, LearnedPattern] = {}
        self.option_mappings: Dict[str, Dict[str, List[str]]] = {}
        self._load()
    
    def _load(self):
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for pattern_id, pattern_data in data.get('patterns', {}).items():
                        self.patterns[pattern_id] = LearnedPattern(**pattern_data)
                    self.option_mappings = data.get('option_mappings', {})
                print(f"📚 Loaded {len(self.patterns)} learned patterns")
            except Exception as e:
                print(f"⚠️ Failed to load learned patterns: {e}")
    
    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            data = {
                'patterns': {k: asdict(v) for k, v in self.patterns.items()},
                'option_mappings': self.option_mappings,
                'last_updated': datetime.now().isoformat()
            }
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"⚠️ Failed to save learned patterns: {e}")
    
    def add_pattern(
        self,
        question: str,
        answer: str,
        option_mapping: Optional[Dict[str, str]] = None,
        source: str = "manual_correction"
    ) -> str:
        pattern_id = hashlib.md5(question.lower().encode()).hexdigest()[:12]
        
        if pattern_id in self.patterns:
            pattern = self.patterns[pattern_id]
            if question not in pattern.question_patterns:
                pattern.question_patterns.append(question)
            pattern.confidence = min(pattern.confidence + 0.1, 1.0)
            pattern.times_used += 1
        else:
            pattern = LearnedPattern(
                pattern_id=pattern_id,
                question_patterns=[question],
                answer=answer,
                option_mappings=option_mapping or {},
                confidence=0.5,
                learned_from=source,
                created_at=datetime.now().isoformat()
            )
            self.patterns[pattern_id] = pattern
        
        self._save()
        return pattern_id
    
    def record_success(self, pattern_id: str):
        if pattern_id in self.patterns:
            pattern = self.patterns[pattern_id]
            pattern.times_used += 1
            pattern.times_succeeded += 1
            if pattern.times_succeeded >= 3:
                pattern.confidence = min(pattern.confidence + 0.1, 1.0)
            self._save()
    
    def record_failure(self, pattern_id: str):
        if pattern_id in self.patterns:
            pattern = self.patterns[pattern_id]
            pattern.times_used += 1
            pattern.confidence = max(pattern.confidence - 0.15, 0.1)
            self._save()
    
    def add_option_mapping(
        self,
        question_pattern: str,
        option_value: str,
        answer_variations: List[str]
    ):
        key = f"{question_pattern}:{option_value}"
        if key not in self.option_mappings:
            self.option_mappings[key] = []
        
        for answer in answer_variations:
            if answer not in self.option_mappings[key]:
                self.option_mappings[key].append(answer)
        
        self._save()
    
    def find_pattern_for_question(self, question: str) -> Optional[LearnedPattern]:
        question_lower = question.lower()
        
        for pattern in self.patterns.values():
            for q_pattern in pattern.question_patterns:
                if q_pattern.lower() in question_lower or question_lower in q_pattern.lower():
                    return pattern
                from difflib import SequenceMatcher
                if SequenceMatcher(None, question_lower, q_pattern.lower()).ratio() > 0.8:
                    return pattern
        
        return None
    
    def get_confident_patterns(self, min_confidence: float = 0.7) -> List[LearnedPattern]:
        return [p for p in self.patterns.values() if p.confidence >= min_confidence]


class RecoveryEngine:
    """Engine for recovering from answer failures."""
    
    def __init__(
        self,
        failure_logger: FailureLogger,
        learning_store: LearningStore
    ):
        self.failure_logger = failure_logger
        self.learning_store = learning_store
    
    def attempt_recovery(
        self,
        question: str,
        failed_answer: str,
        options: List[str],
        platform: str,
        url: str
    ) -> RecoveryResult:
        learned = self.learning_store.find_pattern_for_question(question)
        if learned and learned.confidence >= 0.5:
            return RecoveryResult(
                success=True,
                answer=learned.answer,
                matched_option=self._match_to_options(learned.answer, options),
                strategy='learned_pattern',
                confidence=learned.confidence,
                message=f"Using learned pattern (confidence: {learned.confidence:.0%})"
            )
        
        similar_failures = self.failure_logger.get_similar_failures(question)
        if similar_failures:
            for failure in reversed(similar_failures):
                if failure.attempted_answer != failed_answer:
                    return RecoveryResult(
                        success=True,
                        answer=failure.attempted_answer,
                        matched_option=self._match_to_options(failure.attempted_answer, options),
                        strategy='similar_failure',
                        confidence=0.6,
                        message="Trying answer from similar question"
                    )
        
        if options:
            import re
            num_match = re.search(r'(\d+\.?\d*)', failed_answer)
            if num_match:
                value = float(num_match.group(1))
                best_option = self._find_best_range_option(value, options)
                if best_option:
                    return RecoveryResult(
                        success=True,
                        answer=best_option,
                        matched_option=best_option,
                        strategy='range_match',
                        confidence=0.85,
                        message=f"Matched {value} to range option"
                    )
        
        if options and len(options) > 0:
            first_option = options[0]
            return RecoveryResult(
                success=False,
                answer=first_option,
                matched_option=first_option,
                strategy='fallback_first',
                confidence=0.3,
                message="No good match found, using first option as placeholder"
            )
        
        return RecoveryResult(
            success=False,
            answer=failed_answer,
            matched_option=None,
            strategy='no_recovery',
            confidence=0.0,
            message="Unable to recover, manual intervention needed"
        )
    
    def _match_to_options(self, answer: str, options: List[str]) -> Optional[str]:
        if not answer or not options:
            return None
        answer_lower = answer.lower()
        for opt in options:
            if answer_lower in opt.lower() or opt.lower() in answer_lower:
                return opt
        return None
    
    def _find_best_range_option(self, value: float, options: List[str]) -> Optional[str]:
        for opt in options:
            match = re.search(r'(\d+\.?\d*)\s*[-–to]+\s*(\d+\.?\d*)', opt, re.IGNORECASE)
            if match:
                min_val, max_val = float(match.group(1)), float(match.group(2))
                if min_val <= value <= max_val:
                    return opt
            
            match = re.search(r'(\d+\.?\d*)\s*\+', opt)
            if match:
                min_val = float(match.group(1))
                if value >= min_val:
                    return opt
        
        return None
    
    def learn_from_correction(
        self,
        question: str,
        wrong_answer: str,
        correct_answer: str,
        correct_option: str,
        platform: str
    ):
        pattern_id = self.learning_store.add_pattern(
            question=question,
            answer=correct_answer,
            option_mapping={correct_option: [correct_answer, wrong_answer]},
            source='manual_correction'
        )
        
        self.learning_store.add_option_mapping(
            question_pattern=question[:50],
            option_value=correct_option,
            answer_variations=[correct_answer, wrong_answer]
        )
        
        print(f"✅ Learned: '{question[:50]}...' -> '{correct_option}'")
        return pattern_id


class SelfHealingMatcher:
    """
    Main class combining failure logging, learning, and recovery.
    """
    
    def __init__(self, storage_dir: str = None):
        if storage_dir is None:
            storage_dir = os.path.expanduser("~/Desktop/sentinel_errors")
        
        self.failure_logger = FailureLogger(
            os.path.join(storage_dir, "failure_log.jsonl")
        )
        self.learning_store = LearningStore(
            os.path.join(storage_dir, "learned_patterns.json")
        )
        self.recovery_engine = RecoveryEngine(
            self.failure_logger,
            self.learning_store
        )
    
    def on_answer_failure(
        self,
        question: str,
        attempted_answer: str,
        input_type: str,
        options: List[str],
        platform: str,
        url: str,
        error_type: str = "submission_failed"
    ) -> RecoveryResult:
        self.failure_logger.log_failure(
            question=question,
            attempted_answer=attempted_answer,
            input_type=input_type,
            options=options,
            platform=platform,
            url=url,
            error_type=error_type
        )
        
        return self.recovery_engine.attempt_recovery(
            question=question,
            failed_answer=attempted_answer,
            options=options,
            platform=platform,
            url=url
        )
    
    def on_manual_correction(
        self,
        question: str,
        wrong_answer: str,
        correct_answer: str,
        correct_option: str,
        platform: str
    ):
        return self.recovery_engine.learn_from_correction(
            question=question,
            wrong_answer=wrong_answer,
            correct_answer=correct_answer,
            correct_option=correct_option,
            platform=platform
        )
    
    def get_learned_answer(self, question: str) -> Optional[Tuple[str, float]]:
        pattern = self.learning_store.find_pattern_for_question(question)
        if pattern and pattern.confidence >= 0.5:
            return (pattern.answer, pattern.confidence)
        return None
    
    def get_stats(self) -> Dict:
        patterns = self.learning_store.patterns
        confident = self.learning_store.get_confident_patterns()
        
        return {
            'total_patterns': len(patterns),
            'confident_patterns': len(confident),
            'avg_confidence': sum(p.confidence for p in patterns.values()) / len(patterns) if patterns else 0,
            'total_uses': sum(p.times_used for p in patterns.values()),
            'total_successes': sum(p.times_succeeded for p in patterns.values())
        }
