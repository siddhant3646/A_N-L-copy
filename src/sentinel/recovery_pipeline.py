"""
Recovery Pipeline - Multi-strategy recovery for form filling failures.

This module provides a pipeline of recovery strategies that are tried
in order until one succeeds or all are exhausted.
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import re
from difflib import SequenceMatcher

from src.patterns.input_aware_resolver import (
    InputAwareResolver, InputType, Option
)


class StrategyType(Enum):
    LEARNED_PATTERN = "learned_pattern"
    OPTION_MATCH = "option_match"
    NUMERIC_RANGE = "numeric_range"
    SYNONYM_EXPANSION = "synonym_expansion"
    SIMILAR_QUESTION = "similar_question"
    DEFAULT = "default"


@dataclass
class RecoveryResult:
    success: bool
    answer: str
    matched_option: Optional[str]
    strategy: StrategyType
    confidence: float
    message: str
    alternatives: List[Tuple[str, float]] = None
    
    def __post_init__(self):
        if self.alternatives is None:
            self.alternatives = []


class RecoveryStrategy:
    """Base class for recovery strategies."""
    
    def __init__(self, strategy_type: StrategyType):
        self.strategy_type = strategy_type
        self.resolver = InputAwareResolver()
    
    async def attempt(
        self,
        question: str,
        failed_answer: str,
        options: List[str],
        context: Dict
    ) -> RecoveryResult:
        """Attempt recovery. Must be implemented by subclasses."""
        raise NotImplementedError
    
    def _similarity(self, s1: str, s2: str) -> float:
        """Calculate string similarity."""
        return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()


class LearnedPatternStrategy(RecoveryStrategy):
    """Try learned patterns first."""
    
    def __init__(self, learning_store):
        super().__init__(StrategyType.LEARNED_PATTERN)
        self.learning_store = learning_store
    
    async def attempt(
        self,
        question: str,
        failed_answer: str,
        options: List[str],
        context: Dict
    ) -> RecoveryResult:
        # Check for exact pattern match
        pattern = self.learning_store.find_pattern_for_question(question)
        
        if pattern and pattern.confidence >= 0.5:
            # If options available, match to best option
            if options:
                opt_objects = [Option(value=o, label=o, index=i) for i, o in enumerate(options)]
                result = self.resolver.resolve(
                    answer=pattern.answer,
                    input_type=InputType.SELECT,
                    options=opt_objects,
                    question=question
                )
                
                if result.matched_option:
                    return RecoveryResult(
                        success=True,
                        answer=result.matched_option.label,
                        matched_option=result.matched_option.label,
                        strategy=self.strategy_type,
                        confidence=pattern.confidence * result.confidence,
                        message=f"Learned pattern matched: '{pattern.answer}' -> '{result.matched_option.label}'",
                        alternatives=[(o.label, s) for o, s in result.alternatives]
                    )
            
            # No options or direct text answer
            return RecoveryResult(
                success=True,
                answer=pattern.answer,
                matched_option=None,
                strategy=self.strategy_type,
                confidence=pattern.confidence,
                message=f"Using learned pattern answer: '{pattern.answer}'"
            )
        
        return RecoveryResult(
            success=False,
            answer=failed_answer,
            matched_option=None,
            strategy=self.strategy_type,
            confidence=0.0,
            message="No learned pattern found"
        )


class OptionMatchStrategy(RecoveryStrategy):
    """Fuzzy match answer to available options."""
    
    def __init__(self):
        super().__init__(StrategyType.OPTION_MATCH)
    
    async def attempt(
        self,
        question: str,
        failed_answer: str,
        options: List[str],
        context: Dict
    ) -> RecoveryResult:
        if not options:
            return RecoveryResult(
                success=False,
                answer=failed_answer,
                matched_option=None,
                strategy=self.strategy_type,
                confidence=0.0,
                message="No options available to match"
            )
        
        opt_objects = [Option(value=o, label=o, index=i) for i, o in enumerate(options)]
        
        result = self.resolver.resolve(
            answer=failed_answer,
            input_type=InputType.SELECT,
            options=opt_objects,
            question=question
        )
        
        if result.matched_option and result.confidence >= 0.6:
            return RecoveryResult(
                success=True,
                answer=result.matched_option.label,
                matched_option=result.matched_option.label,
                strategy=self.strategy_type,
                confidence=result.confidence,
                message=f"Option matched: '{failed_answer}' -> '{result.matched_option.label}' ({result.match_type})",
                alternatives=[(o.label, s) for o, s in result.alternatives]
            )
        
        # Return best alternative even if below threshold
        if result.alternatives:
            best_alt = result.alternatives[0]
            return RecoveryResult(
                success=False,
                answer=failed_answer,
                matched_option=best_alt[0].label,
                strategy=self.strategy_type,
                confidence=best_alt[1],
                message=f"Best option match (below threshold): '{best_alt[0].label}' (conf: {best_alt[1]:.2f})",
                alternatives=[(o.label, s) for o, s in result.alternatives]
            )
        
        return RecoveryResult(
            success=False,
            answer=failed_answer,
            matched_option=None,
            strategy=self.strategy_type,
            confidence=0.0,
            message="No good option match found"
        )


class NumericRangeStrategy(RecoveryStrategy):
    """Map numeric values to range options."""
    
    def __init__(self):
        super().__init__(StrategyType.NUMERIC_RANGE)
    
    async def attempt(
        self,
        question: str,
        failed_answer: str,
        options: List[str],
        context: Dict
    ) -> RecoveryResult:
        # Extract number from answer
        num_match = re.search(r'(\d+\.?\d*)', failed_answer)
        if not num_match:
            return RecoveryResult(
                success=False,
                answer=failed_answer,
                matched_option=None,
                strategy=self.strategy_type,
                confidence=0.0,
                message="No numeric value found in answer"
            )
        
        value = float(num_match.group(1))
        
        best_option = None
        best_score = 0.0
        
        for opt in options:
            # Try range pattern: "3-5" or "3 to 5"
            range_match = re.search(r'(\d+\.?\d*)\s*[-–to]+\s*(\d+\.?\d*)', opt, re.IGNORECASE)
            if range_match:
                min_val = float(range_match.group(1))
                max_val = float(range_match.group(2))
                
                if min_val <= value <= max_val:
                    # Calculate how centered the value is
                    center = (min_val + max_val) / 2
                    distance = abs(value - center)
                    score = 1.0 - (distance / (max_val - min_val)) * 0.5
                    
                    if score > best_score:
                        best_score = score
                        best_option = opt
            
            # Try "X+" pattern
            plus_match = re.search(r'(\d+\.?\d*)\s*\+', opt)
            if plus_match:
                min_val = float(plus_match.group(1))
                if value >= min_val:
                    score = 0.95
                    if score > best_score:
                        best_score = score
                        best_option = opt
        
        if best_option and best_score >= 0.7:
            return RecoveryResult(
                success=True,
                answer=best_option,
                matched_option=best_option,
                strategy=self.strategy_type,
                confidence=best_score,
                message=f"Numeric range match: {value} -> '{best_option}'"
            )
        
        return RecoveryResult(
            success=False,
            answer=failed_answer,
            matched_option=best_option,
            strategy=self.strategy_type,
            confidence=best_score,
            message=f"No good range match for {value}"
        )


class SynonymExpansionStrategy(RecoveryStrategy):
    """Expand answer with synonyms and try each."""
    
    SYNONYMS = {
        'yes': ['yes', 'true', '1', 'agree', 'accept', 'confirm', 'ok'],
        'no': ['no', 'false', '0', 'decline', 'reject', 'not'],
        'remote': ['remote', 'work from home', 'wfh', 'virtual', 'home based'],
        'hybrid': ['hybrid', 'flexible', 'mixed', 'partially remote'],
        'onsite': ['onsite', 'work from office', 'wfo', 'in-office', 'office'],
        'immediate': ['immediate', 'now', 'asap', 'right away', 'instantly'],
        'fresher': ['fresher', 'fresh graduate', 'entry level', 'no experience', '0 years'],
    }
    
    def __init__(self):
        super().__init__(StrategyType.SYNONYM_EXPANSION)
    
    async def attempt(
        self,
        question: str,
        failed_answer: str,
        options: List[str],
        context: Dict
    ) -> RecoveryResult:
        answer_lower = failed_answer.lower()
        
        # Find synonym group
        synonym_group = None
        for canonical, synonyms in self.SYNONYMS.items():
            if any(s in answer_lower for s in synonyms):
                synonym_group = synonyms
                break
        
        if not synonym_group:
            return RecoveryResult(
                success=False,
                answer=failed_answer,
                matched_option=None,
                strategy=self.strategy_type,
                confidence=0.0,
                message="No synonym group found for answer"
            )
        
        best_match = None
        best_score = 0.0
        
        # Try each synonym against options
        for synonym in synonym_group:
            for opt in options:
                score = self._similarity(synonym, opt)
                if score > best_score:
                    best_score = score
                    best_match = opt
        
        if best_match and best_score >= 0.7:
            return RecoveryResult(
                success=True,
                answer=best_match,
                matched_option=best_match,
                strategy=self.strategy_type,
                confidence=best_score,
                message=f"Synonym match: '{failed_answer}' -> '{best_match}'"
            )
        
        return RecoveryResult(
            success=False,
            answer=failed_answer,
            matched_option=best_match,
            strategy=self.strategy_type,
            confidence=best_score,
            message=f"Best synonym match: '{best_match}' (conf: {best_score:.2f})"
        )


class SimilarQuestionStrategy(RecoveryStrategy):
    """Find similar questions that succeeded and try their answers."""
    
    def __init__(self, failure_logger):
        super().__init__(StrategyType.SIMILAR_QUESTION)
        self.failure_logger = failure_logger
    
    async def attempt(
        self,
        question: str,
        failed_answer: str,
        options: List[str],
        context: Dict
    ) -> RecoveryResult:
        # Get similar past failures that recovered successfully
        similar = self.failure_logger.get_similar_failures(question, limit=5)
        
        if not similar:
            return RecoveryResult(
                success=False,
                answer=failed_answer,
                matched_option=None,
                strategy=self.strategy_type,
                confidence=0.0,
                message="No similar questions found"
            )
        
        # Try answers from similar questions
        for failure in similar:
            if failure.attempted_answer != failed_answer:
                # Check if this answer works with options
                if options:
                    opt_objects = [Option(value=o, label=o, index=i) for i, o in enumerate(options)]
                    result = self.resolver.resolve(
                        answer=failure.attempted_answer,
                        input_type=InputType.SELECT,
                        options=opt_objects,
                        question=question
                    )
                    
                    if result.matched_option and result.confidence >= 0.6:
                        return RecoveryResult(
                            success=True,
                            answer=result.matched_option.label,
                            matched_option=result.matched_option.label,
                            strategy=self.strategy_type,
                            confidence=0.6,
                            message=f"Similar question match: '{failure.question[:30]}...' -> '{result.matched_option.label}'"
                        )
                else:
                    # No options, try direct answer
                    return RecoveryResult(
                        success=True,
                        answer=failure.attempted_answer,
                        matched_option=None,
                        strategy=self.strategy_type,
                        confidence=0.5,
                        message=f"Trying similar question answer: '{failure.attempted_answer}'"
                    )
        
        return RecoveryResult(
            success=False,
            answer=failed_answer,
            matched_option=None,
            strategy=self.strategy_type,
            confidence=0.0,
            message="No successful similar question found"
        )


class RecoveryPipeline:
    """
    Pipeline that tries multiple recovery strategies in order.
    """
    
    def __init__(self, learning_store, failure_logger):
        self.learning_store = learning_store
        self.failure_logger = failure_logger
        self.strategies: List[RecoveryStrategy] = []
        self._setup_strategies()
        self.attempts = 0
        self.successes = 0
        self.success_by_strategy: Dict[str, int] = {}
    
    def _setup_strategies(self):
        """Initialize recovery strategies in order of priority."""
        self.strategies = [
            LearnedPatternStrategy(self.learning_store),
            OptionMatchStrategy(),
            NumericRangeStrategy(),
            SynonymExpansionStrategy(),
            SimilarQuestionStrategy(self.failure_logger),
        ]
    
    async def execute(
        self,
        question: str,
        failed_answer: str,
        options: List[str],
        context: Dict = None
    ) -> RecoveryResult:
        """
        Execute recovery pipeline.
        
        Args:
            question: The question text
            failed_answer: The answer that failed
            options: Available options for select/radio
            context: Additional context
            
        Returns:
            RecoveryResult with best attempt
        """
        if context is None:
            context = {}
        
        self.attempts += 1
        
        print(f"🔧 Recovery pipeline starting for: '{question[:50]}...'")
        
        for i, strategy in enumerate(self.strategies, 1):
            print(f"   Strategy {i}/{len(self.strategies)}: {strategy.strategy_type.value}...")
            
            result = await strategy.attempt(question, failed_answer, options, context)
            
            if result.success:
                self.successes += 1
                self.success_by_strategy[strategy.strategy_type.value] = \
                    self.success_by_strategy.get(strategy.strategy_type.value, 0) + 1
                
                print(f"   ✅ Success! {result.message}")
                return result
            else:
                print(f"   ❌ Failed: {result.message}")
        
        # All strategies failed
        print("   ⚠️ All recovery strategies failed")
        return RecoveryResult(
            success=False,
            answer=failed_answer,
            matched_option=None,
            strategy=StrategyType.DEFAULT,
            confidence=0.0,
            message="All recovery strategies exhausted"
        )
    
    def get_stats(self) -> Dict:
        """Get pipeline statistics."""
        return {
            'total_attempts': self.attempts,
            'successful': self.successes,
            'success_rate': self.successes / max(1, self.attempts),
            'by_strategy': self.success_by_strategy
        }
    
    def reset_stats(self):
        """Reset statistics."""
        self.attempts = 0
        self.successes = 0
        self.success_by_strategy = {}
