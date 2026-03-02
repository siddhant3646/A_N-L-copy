# Lessons Learned

## 2026-03-02: LinkedIn Selector Debugging

### Lesson 1: Template resolution must happen at EVERY return path
- `{{TECH_EXP_YEARS}}` leaked into form fields because fingerprint matching (Phase 0.5) returned early before `_adjust_answer_for_platform()` ran
- **Rule:** When adding early-return optimizations (caches, fingerprint matches), always apply the same post-processing that the main path does

### Lesson 2: Never use `data-view-name` as a unique identifier
- `data-view-name="job-search-job-card"` is identical for ALL cards → marking one as visited marks ALL as visited
- **Rule:** Only use truly unique attributes (numeric IDs, href paths) for tracking. Validate uniqueness before using any attribute as an ID

### Lesson 3: Adding parent elements as card selectors creates hidden duplicates
- `li.scaffold-layout__list-item` + `[data-occludable-job-id]` = 50 elements (25 `li` + 25 inner `div`)
- `[...new Set()]` deduplication doesn't help because they're different DOM nodes representing the same logical card
- **Rule:** Card selectors should target the element that carries the data attributes, not its parent wrapper

### Lesson 4: `querySelector` on `queryAllDeep` results may not find nested elements
- If a card is returned from shadow DOM traversal, regular `querySelector` from it may miss children
- **Rule:** Use `.closest('li')?.querySelector(...)` as fallback when the primary querySelector fails
