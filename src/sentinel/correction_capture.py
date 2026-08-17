"""
Correction Capture - Manual correction capture system.

Captures manual corrections via multiple methods:
1. Auto-detect: MutationObserver detects value changes after errors
2. Console command: window.learnCorrection()
3. Keyboard shortcut: Ctrl+Shift+C
"""

import re
from collections import deque
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Correction:
    """Represents a manual correction."""
    timestamp: str
    field_label: str
    wrong_answer: str
    correct_answer: str
    available_options: List[str]
    platform: str
    url: str
    capture_method: str  # 'auto', 'console', 'keyboard'
    

class CorrectionCapture:
    """
    Captures manual corrections for learning.
    """
    
    def __init__(self, learning_store, propagate_to_similar=True):
        self.learning_store = learning_store
        self.propagate_to_similar = propagate_to_similar
        # Bounded corrections list (deque drops oldest when full)
        self.corrections = deque(maxlen=100)
        self.last_failed_field = None
        self.last_failed_value = None
    
    def record_failure_context(
        self,
        field_label: str,
        wrong_answer: str,
        options: List[str]
    ):
        """
        Record context when a failure occurs.
        Used by auto-detect to compare with subsequent changes.
        """
        self.last_failed_field = field_label
        self.last_failed_value = wrong_answer
        self.last_failed_options = options
    
    def capture_correction(
        self,
        field_label: str,
        wrong_answer: str,
        correct_answer: str,
        available_options: List[str] = None,
        platform: str = "default",
        url: str = "",
        capture_method: str = "manual"
    ) -> str:
        """
        Capture a manual correction.
        
        Returns:
            Pattern ID if successfully learned
        """
        if not correct_answer or correct_answer == wrong_answer:
            return None
        
        correction = Correction(
            timestamp=datetime.now().isoformat(),
            field_label=field_label,
            wrong_answer=wrong_answer,
            correct_answer=correct_answer,
            available_options=available_options or [],
            platform=platform,
            url=url,
            capture_method=capture_method
        )
        
        self.corrections.append(correction)
        
        # Learn the correction
        pattern_id = self._learn_correction(correction)
        
        print(f"✅ Correction captured via {capture_method}: '{field_label[:40]}...'")
        print(f"   Wrong: '{wrong_answer}' → Correct: '{correct_answer}'")
        
        if pattern_id:
            print(f"   Pattern ID: {pattern_id}")
            
            # Propagate to similar questions
            if self.propagate_to_similar:
                self._propagate_to_equivalent_questions(correction)
        
        return pattern_id
    
    def _learn_correction(self, correction: Correction) -> str:
        """Learn a correction as a new pattern."""
        # Find the option that matches the correct answer
        matched_option = self._find_matching_option(
            correction.correct_answer,
            correction.available_options
        )
        
        option_mapping = {}
        if matched_option:
            option_mapping = {
                matched_option: [correction.correct_answer, correction.wrong_answer]
            }
        
        # Add to learning store
        pattern_id = self.learning_store.add_pattern(
            question=correction.field_label,
            answer=correction.correct_answer,
            option_mapping=option_mapping,
            source=f'manual_correction_{correction.capture_method}'
        )
        
        # Boost confidence since this was manually verified
        pattern = self.learning_store.patterns.get(pattern_id)
        if pattern:
            pattern.confidence = min(pattern.confidence + 0.2, 1.0)
        
        return pattern_id
    
    def _find_matching_option(self, answer: str, options: List[str]) -> Optional[str]:
        """Find which option matches the answer."""
        if not options:
            return None
        
        answer_lower = answer.lower()
        
        for opt in options:
            if answer_lower in opt.lower() or opt.lower() in answer_lower:
                return opt
        
        # Try numeric matching
        num_match = re.search(r'(\d+\.?\d*)', answer)
        if num_match:
            value = float(num_match.group(1))
            for opt in options:
                range_match = re.search(r'(\d+\.?\d*)\s*[-–to]+\s*(\d+\.?\d*)', opt)
                if range_match:
                    min_val = float(range_match.group(1))
                    max_val = float(range_match.group(2))
                    if min_val <= value <= max_val:
                        return opt
        
        return None
    
    def _propagate_to_equivalent_questions(self, correction: Correction):
        """Propagate learning to equivalent question patterns."""
        from src.sentinel.semantic_matcher import SemanticQuestionMatcher
        
        matcher = SemanticQuestionMatcher()
        equivalence_class = matcher.find_equivalence_class(correction.field_label)
        
        if not equivalence_class:
            return
        
        equivalents = matcher.EQUIVALENT_QUESTIONS.get(equivalence_class, [])
        propagated = 0
        
        for eq_question in equivalents:
            if eq_question.lower() != correction.field_label.lower():
                # Check if we already have this pattern
                existing = self.learning_store.find_pattern_for_question(eq_question)
                if not existing or existing.confidence < 0.7:
                    self.learning_store.add_pattern(
                        question=eq_question,
                        answer=correction.correct_answer,
                        option_mapping={},
                        source=f'propagated_from_{correction.field_label[:20]}'
                    )
                    propagated += 1
        
        if propagated > 0:
            print(f"   📚 Propagated to {propagated} equivalent questions")
    
    def auto_detect_correction(
        self,
        field_label: str,
        current_value: str,
        available_options: List[str] = None,
        platform: str = "default",
        url: str = ""
    ) -> Optional[str]:
        """
        Auto-detect if this is a correction.
        Called when a field value changes.
        """
        # Check if this field had a previous failure
        if self.last_failed_field != field_label:
            return None
        
        if current_value == self.last_failed_value:
            return None
        
        # This is likely a correction
        return self.capture_correction(
            field_label=field_label,
            wrong_answer=self.last_failed_value,
            correct_answer=current_value,
            available_options=available_options or self.last_failed_options,
            platform=platform,
            url=url,
            capture_method='auto'
        )
    
    def get_recent_corrections(self, limit: int = 20) -> List[Correction]:
        """Get recent corrections for review."""
        return sorted(
            self.corrections,
            key=lambda c: c.timestamp,
            reverse=True
        )[:limit]
    
    def get_corrections_by_field(self, field_pattern: str) -> List[Correction]:
        """Get corrections for a specific field pattern."""
        pattern_lower = field_pattern.lower()
        return [
            c for c in self.corrections
            if pattern_lower in c.field_label.lower()
        ]
    
    def get_correction_stats(self) -> Dict:
        """Get statistics about corrections."""
        if not self.corrections:
            return {
                'total': 0,
                'by_method': {},
                'by_platform': {}
            }
        
        by_method = {}
        by_platform = {}
        
        for c in self.corrections:
            by_method[c.capture_method] = by_method.get(c.capture_method, 0) + 1
            by_platform[c.platform] = by_platform.get(c.platform, 0) + 1
        
        return {
            'total': len(self.corrections),
            'by_method': by_method,
            'by_platform': by_platform
        }


# JavaScript code to inject into browser
CORRECTION_CAPTURE_JS = """
// Correction Capture JavaScript
(function() {
    'use strict';
    
    // Track last failed field
    window.__sentinel_last_failed = {
        field: null,
        value: null,
        options: []
    };
    
    // Record failure context (called from Python when error detected)
    window.recordSentinelFailure = function(fieldLabel, value, options) {
        window.__sentinel_last_failed = {
            field: fieldLabel,
            value: value,
            options: options || []
        };
        console.log('[Sentinel] Failure recorded:', fieldLabel, value);
    };
    
    // Auto-detect corrections
    document.addEventListener('change', function(e) {
        const target = e.target;
        if (!target.matches('input, select, textarea')) return;
        
        const lastFailed = window.__sentinel_last_failed;
        if (!lastFailed.field) return;
        
        // Get field label
        const label = target.closest('label')?.innerText || 
                     document.querySelector(`label[for="${target.id}"]`)?.innerText ||
                     target.name ||
                     target.id;
        
        // Check if this is the same field
        if (label && lastFailed.field.includes(label)) {
            const newValue = target.value;
            if (newValue && newValue !== lastFailed.value) {
                // This is likely a correction
                console.log('[Sentinel] Auto-detected correction:', lastFailed.value, '->', newValue);
                
                // Send to Python
                fetch('/__sentinel_learn__', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        method: 'auto',
                        field: label,
                        wrong: lastFailed.value,
                        correct: newValue,
                        options: lastFailed.options
                    })
                });
                
                // Clear failure context
                window.__sentinel_last_failed = {field: null, value: null, options: []};
            }
        }
    });
    
    // Console command for manual correction
    window.learnCorrection = function(field, wrong, correct, options) {
        if (!field) {
            // Use last failed field if not specified
            const lastFailed = window.__sentinel_last_failed;
            if (!lastFailed.field) {
                console.error('[Sentinel] No recent failure to learn from. Use: learnCorrection("field", "wrong", "correct")');
                return;
            }
            field = lastFailed.field;
            wrong = lastFailed.value;
            options = lastFailed.options;
        }
        
        if (!wrong || !correct) {
            console.error('[Sentinel] Usage: learnCorrection(field, wrongValue, correctValue)');
            return;
        }
        
        console.log('[Sentinel] Learning correction:', field, wrong, '->', correct);
        
        fetch('/__sentinel_learn__', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                method: 'console',
                field: field,
                wrong: wrong,
                correct: correct,
                options: options || []
            })
        }).then(r => r.json()).then(data => {
            console.log('[Sentinel] Correction learned:', data.pattern_id);
        });
    };
    
    // Keyboard shortcut: Ctrl+Shift+C
    document.addEventListener('keydown', function(e) {
        if (e.ctrlKey && e.shiftKey && e.key === 'C') {
            e.preventDefault();
            
            const lastFailed = window.__sentinel_last_failed;
            if (!lastFailed.field) {
                // Manual entry
                const correction = prompt(
                    'Enter correction (format: wrong|correct):',
                    '|'
                );
                if (correction && correction.includes('|')) {
                    const [wrong, correct] = correction.split('|');
                    window.learnCorrection(null, wrong.trim(), correct.trim());
                }
            } else {
                // Use last failed context
                const correct = prompt(
                    `Correct answer for "${lastFailed.field}" (was: ${lastFailed.value}):`
                );
                if (correct) {
                    window.learnCorrection(
                        lastFailed.field,
                        lastFailed.value,
                        correct,
                        lastFailed.options
                    );
                }
            }
        }
    });
    
    console.log('[Sentinel] Correction capture loaded. Methods: learnCorrection(), Ctrl+Shift+C');
})();
"""


def get_correction_capture_js() -> str:
    """Get the JavaScript code for browser injection."""
    return CORRECTION_CAPTURE_JS
