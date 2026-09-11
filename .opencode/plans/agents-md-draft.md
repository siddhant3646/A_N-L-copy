# Plan: Create AGENTS.md

## Goal
Create a comprehensive `AGENTS.md` at the project root that gives AI agents full project context without requiring the user to explain the project each time.

## Sections Included

1. **Project Overview** — What Sentinel is, what it does
2. **How to Run** — Main command, tests, CLI utilities, live testing
3. **Environment Variables** — All 4 env vars with examples
4. **Architecture** — Two-tier Q&A system, embedded JS, key conventions
5. **Candidate Profile** — Complete hardcoded values table
6. **Platform-Specific Rules** — LinkedIn/Naukri/Instahyre formatting differences
7. **Q&A Matching Flow** — Complete phase-by-phase trace (PHASE 0 → PHASE 3) with line numbers
8. **JS-Side FuzzyMatch** — Naukri and LinkedIn JS matching flows
9. **Platform Internals** — Deep dive into LinkedIn form filling, Naukri chatbot, Instahyre questionnaire
10. **qa_patterns.json Schema** — Full schema documentation with all 16 fields, 27 categories, 13 input types, dynamic placeholders, example entries
11. **How to Add QA Patterns** — Step-by-step guide for manually adding new patterns (NEW)
12. **File-by-File Guide** — Every key file with line count, purpose, key classes/functions
13. **Debugging Guide** — qa_results.csv analysis, common error patterns table, failure log format, debug env vars
14. **Git & Workflow** — Commit conventions, branch strategy, lessons learned
15. **Common Pitfalls** — 8 critical gotchas with explanations

## New Section: How to Add QA Patterns

When a question is answered incorrectly, add a new pattern to `config/qa_patterns.json`.

### Step-by-Step Process

1. **Identify the question** from `qa_results.csv` or failure log
2. **Create a unique pattern ID** (snake_case, descriptive)
3. **Add question variants** to `patterns` array (lowercased, multiple phrasings)
4. **Set category** (one of 27 categories)
5. **Set default answer** (platform-appropriate format)
6. **Add `input_type_defaults`** for different form controls
7. **Set priority** (2-20, higher = matched first)
8. **Add `negative_patterns`** if needed (to prevent over-matching)
9. **Validate JSON** before committing

### Naming Conventions

- Pattern IDs: `snake_case`, descriptive (e.g., `current_salary`, `experience_domain_specific`)
- Patterns array: lowercase, no punctuation, multiple variants
- Categories: use existing categories when possible

### Priority Guidelines

| Priority | Use Case |
|---|---|
| 2-5 | Generic/broad patterns (experience, location) |
| 6-10 | Standard patterns (salary, notice period) |
| 11-15 | Specific technical patterns |
| 16-20 | Highly specific/technical explanations |

### Field Usage Guide

| Field | When to Use |
|---|---|
| `requires_exact_match: true` | PII, sensitive data, self-identification (prevents fuzzy matching) |
| `sensitive: true` | Phone, email, DOB, PAN, passport (controls logging/redaction) |
| `negative_patterns` | Broad patterns that could steal matches (e.g., "experience" excluding "java experience") |
| `platform_overrides` | When answer differs by platform |
| `dynamic_answer: true` | When answer is computed at runtime (dates) |
| `numeric_default` | When form expects pure number (e.g., "23" for salary) |
| `inr_default` | Raw INR value (e.g., "2300000") |
| `lpa_default` | LPA value (e.g., "23") |

### Complete Example

```json
"java_spring_boot_experience": {
  "patterns": [
    "experience in java spring boot",
    "java spring boot experience",
    "how many years of java spring boot",
    "years of experience in java spring boot"
  ],
  "category": "experience",
  "default": "4.2 Years",
  "priority": 12,
  "negative_patterns": [
    "salary",
    "notice period"
  ],
  "input_type_defaults": {
    "radio": "4.2",
    "select": "4.2 Years",
    "text": "4.2 Years",
    "number": "4.2",
    "textarea": "4.2 Years of experience in Java Spring Boot",
    "checkbox": "Yes"
  }
}
```

### Testing After Adding

```bash
pytest tests/unit/qa/ -v
```

Add a test in `tests/unit/qa/test_qa_*.py` if the pattern is critical.

## Implementation

Single file write: `AGENTS.md` at project root.

## Verification

- File is recognized by Cursor, Copilot, opencode, Claude Code automatically
- Contains all sections the user requested: file-by-file guide, qa_patterns.json schema, Q&A matching flow, platform internals, debugging guide, git/workflow rules
