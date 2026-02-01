# QA Pattern Automation Plan

## Current Problem Analysis

Your current system relies on a hardcoded `KNOWN_QA_PATTERNS` dictionary with ~400 question patterns. The matching uses:
1. **Keyword-based priority matching** (PHASE 1) for known question types
2. **Fuzzy string matching** (PHASE 2) with 0.6 threshold
3. **Fallback to default** ("3.8") when no match found

### Pain Points Identified:
1. **Manual Pattern Addition**: Every new question variant requires code changes
2. **No Smart Defaults**: Unknown questions default to "3.8" which is often wrong
3. **Limited Classification**: Questions aren't categorized for intelligent fallback
4. **No Self-Learning**: System doesn't learn from user corrections
5. **Static Configuration**: Patterns embedded in code, not easily editable

---

## Proposed Solution Architecture

### 1. Question Categorization System

Create a classification layer that categorizes questions even without exact pattern matches:

```python
QUESTION_CATEGORIES = {
    'salary': {
        'keywords': ['ctc', 'salary', 'compensation', 'package', 'lpa', 'pay'],
        'default_answer': '20 LPA',
        'patterns': [r'current.*ctc', r'expected.*salary', r'compensation.*expect']
    },
    'experience': {
        'keywords': ['experience', 'years', 'exp', 'tenure', 'worked'],
        'default_answer': '3.8 Years',
        'patterns': [r'\d+.*years.*experience', r'total.*exp']
    },
    'notice_period': {
        'keywords': ['notice', 'serving', 'lwd', 'last working', 'join'],
        'default_answer': '30 days',
        'patterns': [r'notice.*period', r'last.*working.*day']
    },
    'location': {
        'keywords': ['location', 'city', 'relocate', 'based', 'stay'],
        'default_answer': 'Noida',
        'patterns': [r'current.*location', r'where.*located']
    },
    'skills': {
        'keywords': ['skills', 'proficiency', 'expertise', 'knowledge', 'tech stack'],
        'default_answer': 'Java, Spring Boot, React, AWS, Docker',
        'patterns': [r'tech.*stack', r'programming.*languages']
    },
    'yes_no': {
        'keywords': ['willing', 'comfortable', 'available', 'ready', 'interested'],
        'default_answer': 'Yes',
        'patterns': [r'willing.*to.*relocate', r'available.*interview']
    },
    'personal_info': {
        'keywords': ['phone', 'email', 'dob', 'pan', 'aadhar', 'name'],
        'default_answer': None,  # Requires specific info
        'patterns': [r'phone.*number', r'email.*address'],
        'require_exact_match': True
    }
}
```

### 2. Smart Fallback Engine

```
┌─────────────────────────────────────────────────────────────┐
│                    Question Input                           │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 1: Exact Pattern Match (KNOWN_QA_PATTERNS)          │
│  → If match score >= 0.85: Return answer                   │
└─────────────────────────────────────────────────────────────┘
                            │ No exact match
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 2: Category Classification                          │
│  → Match against QUESTION_CATEGORIES patterns/keywords     │
│  → Return category default_answer                          │
└─────────────────────────────────────────────────────────────┘
                            │ No category match
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 3: Regex Pattern Extractor                          │
│  → Extract implied type from question structure            │
│  → "What is your X?" → Infer X type                      │
└─────────────────────────────────────────────────────────────┘
                            │ Still unmatched
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 4: LLM Fallback (Optional)                          │
│  → Call LLM API with question + context                    │
│  → Cache response for future use                           │
└─────────────────────────────────────────────────────────────┘
                            │ LLM unavailable
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Phase 5: Safe Default + Log                               │
│  → Return conservative default ("Yes" or "3.8 Years")      │
│  → Log for manual review                                   │
└─────────────────────────────────────────────────────────────┘
```

### 3. External Configuration System

Move patterns from code to JSON for easier editing:

```json
{
  "patterns": {
    "years_of_experience": {
      "patterns": ["years of experience", "total experience", "overall experience"],
      "answer": "3.8 Years",
      "category": "experience"
    },
    "current_salary": {
      "patterns": ["current salary", "current ctc", "cctc"],
      "answer": "13.5 LPA",
      "category": "salary"
    }
  },
  "categories": {
    "salary": {
      "default_answer": "20 LPA",
      "keywords": ["ctc", "salary", "compensation"]
    }
  },
  "learning": {
    "auto_learn": true,
    "confidence_threshold": 0.8,
    "user_confirmation": true
  }
}
```

### 4. Self-Learning System

```python
class QALearningEngine:
    def __init__(self, config_path):
        self.suggestions = []  # Pending user review
        self.confirmed = {}    # Auto-added patterns
        
    def suggest_pattern(self, question: str, answer: str, confidence: float):
        """Add potential pattern for user review."""
        if confidence >= AUTO_LEARN_THRESHOLD:
            self.suggestions.append({
                'question': question,
                'suggested_answer': answer,
                'confidence': confidence,
                'timestamp': datetime.now()
            })
    
    def confirm_pattern(self, suggestion_id: str, correct_answer: str):
        """User confirms/corrects suggestion, add to patterns."""
        # Add to KNOWN_QA_PATTERNS
        # Save to JSON config
        pass
```

### 5. Enhanced Review Queue

```
~/Desktop/sentinel_errors/
├── unknown_questions.log        # Current: raw unknown questions
├── review_queue.json            # NEW: Structured review items
│   {
│     "pending": [
│       {
│         "id": "uuid",
│         "question": "What is your expected CTC?",
│         "context": "linkedin",
│         "suggested_answer": "20 LPA",
│         "match_confidence": 0.75,
│         "category": "salary",
│         "timestamp": "2026-01-31T..."
│       }
│     ],
│     "approved": [...],
│     "rejected": [...]
│   }
├── pattern_performance.json     # NEW: Track which patterns work
└── auto_learned.json            # NEW: Patterns added automatically
```

### 6. Optional LLM Fallback

For truly novel questions, use LLM with context:

```python
async def llm_fallback(question: str, context: dict) -> str:
    """Use LLM to answer unknown questions."""
    prompt = f"""
    You are helping fill a job application form. Answer concisely.
    
    Applicant Profile:
    - Experience: 3.8 Years
    - Current CTC: 13.5 LPA
    - Expected CTC: 20 LPA
    - Notice Period: 30 days
    - Location: Noida
    - Skills: Java, Spring Boot, React, AWS, Docker
    
    Question: {question}
    
    Provide only the answer, no explanation.
    """
    # Call LLM API (OpenAI/Claude/local)
    # Cache response
    return answer
```

---

## Implementation Phases

### Phase 1: Smart Categorization (Immediate Impact)
- [ ] Create `QUESTION_CATEGORIES` structure
- [ ] Implement category-based fallback before default "3.8"
- [ ] Add regex pattern matching for common question structures
- [ ] Test coverage improvement

### Phase 2: External Config (Maintainability)
- [ ] Move patterns to `config/qa_patterns.json`
- [ ] Create config loader with hot-reload
- [ ] Add config validation
- [ ] Migration script for existing patterns

### Phase 3: Self-Learning (Long-term Improvement)
- [ ] Build review queue system
- [ ] Create user confirmation flow
- [ ] Implement pattern auto-addition
- [ ] Add confidence scoring

### Phase 4: LLM Integration (Optional Enhancement)
- [ ] Design LLM prompt template
- [ ] Implement caching layer
- [ ] Add cost controls (rate limiting)

---

## Expected Improvements

| Metric | Current | After Phase 1 | After Phase 2 | After Phase 3 |
|--------|---------|---------------|---------------|---------------|
| Manual Interventions | High | Medium | Low | Minimal |
| Pattern Coverage | ~400 | ~400+smart defaults | Configurable | Auto-growing |
| Time to Add New Pattern | Code edit | Config edit | Config/Auto | Mostly Auto |
| Unknown Question Handling | Default "3.8" | Category default | Category default | LLM + Learn |

---

## Files to Create/Modify

### New Files:
1. `src/sentinel/qa_config.json` - External pattern configuration
2. `src/sentinel/question_classifier.py` - Category classification engine
3. `src/sentinel/learning_engine.py` - Self-learning system
4. `src/sentinel/review_queue.py` - Review queue management

### Modified Files:
1. `src/sentinel/agent.py` - Integrate new systems
2. `src/sentinel/prompts.py` - Update context if needed

---

## Quick Start Recommendation

Start with **Phase 1 (Smart Categorization)** as it provides immediate value:

1. Add category detection to `_fuzzy_match_question()`
2. Return sensible defaults for each category
3. This alone will handle 70%+ of currently failing questions

Example immediate improvement:
```python
# After fuzzy matching fails:
category = self._classify_question(question)
if category:
    return CATEGORY_DEFAULTS[category], 0.7

# Instead of current:
return None, best_score  # Leads to "3.8" default
```
