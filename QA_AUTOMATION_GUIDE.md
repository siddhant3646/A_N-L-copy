# QA Automation System - Implementation Guide

## Overview

The improved QA system now provides **smart fallback answers** for unknown questions, eliminating the need for manual intervention in most cases. The system automatically detects question types and provides appropriate defaults based on the platform (Naukri vs LinkedIn).

## What Changed

### 1. Smart Question Classification (`src/sentinel/question_classifier.py`)

New module that categorizes questions into types:
- **Experience** → Returns "3.8 Years" (Naukri) or "4" (LinkedIn)
- **Salary** → Returns "13.5 LPA" (current) or "20 LPA" (expected)
- **Notice Period** → Returns "30 days" or calculated LWD
- **Location** → Returns "Noida" or preferred locations
- **Skills** → Returns tech stack or proficiency rating
- **Yes/No** → Returns "Yes" (with smart negative detection)
- **Personal Info** → Returns PAN, DOB, phone (sensitive)
- **Education** → Returns degree, university, CGPA

### 2. Platform-Specific Defaults

| Platform | Experience Value | Months |
|----------|-----------------|--------|
| Naukri | 3.8 Years | 46 |
| LinkedIn | 4 | 46 |
| Instahyre | 3.8 Years | 46 |

### 3. External Configuration (`config/qa_patterns.json`)

Easy-to-edit JSON file for managing patterns without code changes:
```json
{
  "patterns": {
    "experience": {
      "patterns": ["years of experience", "total experience"],
      "category": "experience",
      "requires_context": true
    }
  }
}
```

### 4. Updated Matching Flow (`src/sentinel/agent.py`)

```
Question Input
     │
     ▼
┌────────────────────────────────────────┐
│ Phase 1: Known Pattern Match           │
│ (KNOWN_QA_PATTERNS dictionary)         │
│ → If match >= 0.85: Return answer     │
└────────────────────────────────────────┘
     │ No match
     ▼
┌────────────────────────────────────────┐
│ Phase 2: Keyword Priority Matching     │
│ (Salary, Experience, Location, etc.)   │
│ → If matched: Return specific answer  │
└────────────────────────────────────────┘
     │ No match
     ▼
┌────────────────────────────────────────┐
│ Phase 3: Fuzzy Matching                │
│ (SequenceMatcher on all patterns)      │
│ → If score >= 0.6: Return answer      │
└────────────────────────────────────────┘
     │ No match
     ▼
┌────────────────────────────────────────┐
│ Phase 4: Smart Category Fallback 🆕    │
│ (QuestionClassifier)                   │
│ → Classify question type               │
│ → Return category default              │
└────────────────────────────────────────┘
     │ Still unknown
     ▼
┌────────────────────────────────────────┐
│ Phase 5: Safe Default                  │
│ → Return "Yes" or "3.8 Years"         │
│ → Log for manual review                │
└────────────────────────────────────────┘
```

## How to Add New Patterns

### Option 1: Edit External JSON Config (Recommended)

Edit `config/qa_patterns.json`:

```json
{
  "patterns": {
    "new_question_type": {
      "patterns": [
        "your new question pattern",
        "alternative phrasing"
      ],
      "category": "yes_no",
      "default": "Yes"
    }
  }
}
```

**No code restart required** - Config is read dynamically.

### Option 2: Edit Code Directly

Edit `src/sentinel/agent.py` and add to `KNOWN_QA_PATTERNS`:

```python
KNOWN_QA_PATTERNS = {
    # ... existing patterns ...
    'your new question pattern': 'Your Answer',
    'alternative phrasing': 'Your Answer',
}
```

### Option 3: Add Category Defaults

Edit `src/sentinel/question_classifier.py` and add to `CATEGORY_DEFAULTS`:

```python
CATEGORY_DEFAULTS = {
    QuestionCategory.YES_NO: {
        # ... existing defaults ...
        'new_subcategory': 'Your Default Answer'
    }
}
```

## Question Categories & Smart Answers

### Experience Questions
| Question Contains | Naukri Answer | LinkedIn Answer |
|------------------|---------------|-----------------|
| "years of experience" | 3.8 Years | 4 |
| "months" | 46 | 46 |
| "number" or "whole number" | 3.8 | 4 |

### Salary Questions
| Question Contains | Answer |
|------------------|--------|
| "current" or "cctc" | 13.5 LPA |
| "expected" or "ectc" | 20 LPA |
| "in lakhs" or numeric field | 13.5 or 20 (just number) |

### Notice Period Questions
| Question Contains | Answer |
|------------------|--------|
| "last working day" or "lwd" | Calculated date (e.g., "02 March 2026") |
| "serving" | Yes |
| "days" or numeric | 30 |
| General "notice period" | 30 days |

### Location Questions
| Question Contains | Answer |
|------------------|--------|
| "current location" | Noida |
| "preferred location" | Noida, Delhi NCR, Bangalore, Hyderabad, Mumbai, Pune |
| "relocate" or "willing" | Yes |
| "based in [city]" | No, I am currently based in Noida. However, I am willing to relocate. |

### Skills Questions
| Question Contains | Answer |
|------------------|--------|
| "tech stack" | Java, Spring Boot, React, Node.js, Python, AWS, Docker, Kubernetes... |
| "proficiency" or "rate yourself" | 8 |
| "programming languages" | Java, Python, JavaScript |
| "dsa" or "data structures" | 8 |

### Yes/No Questions
| Question Contains | Answer |
|------------------|--------|
| "willing", "available", "comfortable" | Yes |
| "sponsorship", "referral", "referred" | No |

## Testing the System

### Test Question Classification

```python
from src.sentinel.question_classifier import QuestionClassifier

# Create classifier for specific platform
classifier = QuestionClassifier('naukri')  # or 'linkedin', 'instahyre'

# Classify a question
category, confidence = classifier.classify("What is your expected CTC?")
print(f"Category: {category.value}, Confidence: {confidence}")

# Get answer
answer, conf = classifier.get_answer("What is your expected CTC?", category)
print(f"Answer: {answer}")
```

### Test Platform Detection

```python
from src.sentinel.agent import SentinelAgent

agent = SentinelAgent()
# When running on actual page, platform auto-detects from URL
```

## Monitoring & Logging

All questions are now logged with full details including options and selections:

### Log Files

| File | Contents |
|------|----------|
| `~/Desktop/sentinel_errors/unknown_questions.log` | Questions that couldn't be matched |
| `~/Desktop/sentinel_errors/all_questions.log` | All questions encountered |
| `~/Desktop/sentinel_errors/all_questions_detailed.log` | **NEW:** Full question details with options |
| `~/Desktop/sentinel_errors/all_questions.jsonl` | **NEW:** Structured JSON format for parsing |

### Detailed Log Format

Each question is logged with:
```
[2026-01-31 12:34:56] [linkedin]
  URL: https://www.linkedin.com/jobs/...
  Q: How many years of experience do you have?
  A: 4
  Input Type: number
  ---

[2026-01-31 12:35:01] [linkedin]
  URL: https://www.linkedin.com/jobs/...
  Q: Are you willing to relocate?
  A: Yes
  Input Type: radio
  All Options: Yes, No
  Selected: Yes
  ---
```

### JSON Log Format

For programmatic access, questions are also logged as JSON:
```json
{
  "timestamp": "2026-01-31 12:34:56",
  "context": "linkedin",
  "url": "https://www.linkedin.com/jobs/...",
  "question": "How many years of experience do you have?",
  "answer": "4",
  "confidence": "form_filled",
  "input_type": "number",
  "options": [],
  "selected_option": "4"
}
```

### Reviewing Unknown Questions

To find new patterns to add:
```bash
# View unknown questions
cat ~/Desktop/sentinel_errors/unknown_questions.log

# View all questions with options
cat ~/Desktop/sentinel_errors/all_questions_detailed.log

# Parse JSON log for analysis
jq '.' ~/Desktop/sentinel_errors/all_questions.jsonl
```

### Adding Patterns from Logs

1. Review `unknown_questions.log` for unmatched questions
2. Add the pattern to `config/qa_patterns.json`
3. Or add to `KNOWN_QA_PATTERNS` in `src/sentinel/agent.py`
4. Or add category defaults in `src/sentinel/question_classifier.py` for smart fallback

### Example: Adding from Log

Log shows:
```
[2026-01-31 12:34:56] [linkedin]
  Q: What is your favorite programming language?
  Input Type: text
  ---
```

Add to `config/qa_patterns.json`:
```json
"favorite_language": {
  "patterns": ["favorite programming language"],
  "category": "skills",
  "default": "Java, Python, JavaScript"
}
```

Or add to `src/sentinel/agent.py`:
```python
KNOWN_QA_PATTERNS = {
    # ... existing patterns ...
    'favorite programming language': 'Java, Python, JavaScript',
}
```

Or add smart fallback in `question_classifier.py`:
```python
CATEGORY_DEFAULTS = {
    QuestionCategory.SKILLS: {
        # ... existing defaults ...
        'favorite': 'Java, Python, JavaScript'
    }
}
```
And update `_get_skills_answer()` to handle "favorite" keyword.

## Troubleshooting

### Problem: Wrong experience value returned
**Solution**: Check platform detection. LinkedIn returns "4", Naukri returns "3.8 Years".

### Problem: Unknown question not getting smart fallback
**Solution**: Check `classify()` confidence score. If below 0.4, add more keywords to the category in `question_classifier.py`.

### Problem: Sensitive info (PAN, etc.) not matching
**Solution**: Personal info requires exact pattern match. Add the exact question text to `KNOWN_QA_PATTERNS`.

## Future Enhancements (Planned)

1. **Self-Learning**: Auto-add patterns when user corrects answers
2. **LLM Fallback**: Use AI for truly novel questions
3. **Pattern Performance Tracking**: Identify which patterns fail often
4. **Web UI for Pattern Management**: Edit patterns via browser

## Files Modified/Created

| File | Purpose |
|------|---------|
| `src/sentinel/question_classifier.py` | New: Question classification engine |
| `config/qa_patterns.json` | New: External pattern configuration |
| `src/sentinel/agent.py` | Modified: Integrated classifier into matching flow |
| `plans/qa_automation_plan.md` | New: Architecture planning document |
| `QA_AUTOMATION_GUIDE.md` | This file: User guide |

## Quick Reference

| Task | File to Edit |
|------|--------------|
| Add new pattern | `config/qa_patterns.json` |
| Change default answer for category | `src/sentinel/question_classifier.py` → `CATEGORY_DEFAULTS` |
| Add new question category | `src/sentinel/question_classifier.py` → `CATEGORY_PATTERNS` |
| Change platform defaults | `src/sentinel/question_classifier.py` → `PLATFORM_CONFIGS` |
| View unknown questions | `~/Desktop/sentinel_errors/unknown_questions.log` |
