---
description: Structured bug investigation and fix — root cause analysis, minimal fix, regression check.
---

# Bug Fix Workflow

Systematic approach to diagnosing and fixing bugs. Follows a compressed
mode cycle: `RESEARCH → PLAN → EXECUTE → REVIEW`.

---

## Phase 1: RESEARCH — Root Cause Analysis

1. Create branch and task log:
```bash
git checkout -b fix/<id>
mkdir -p .tasks && touch .tasks/<id>.md
```
// turbo

2. **Reproduce:** Trace the exact execution path that triggers the bug:
   - Read error logs, stack traces, or user description
   - Identify the entry point (API endpoint, UI action, background task)
   - Walk the call chain: caller → function → downstream effects

3. **Isolate:** Narrow down to the specific code block:
   - Use `rg` and `view_file` to trace data flow
   - Check for upstream guards/fallbacks that might mask the issue
   - Verify the bug actually manifests (not theoretical)

4. Document in `.tasks/<id>.md`:
```markdown
## Root Cause
- **Trigger:** [exact steps]
- **Location:** [file:line]
- **Cause:** [why it fails]
- **Impact:** [user-visible effect]
```

**EXIT GATE:** Root cause identified and documented.

---

## Phase 2: PLAN — Minimal Fix

5. Design the smallest possible fix:
   - MUST fix the root cause, not symptoms
   - MUST NOT introduce new behavior beyond the fix
   - Consider edge cases and regression risks

6. Write checklist:
```markdown
## FIX CHECKLIST
1. [ ] [file] Change X to Y (reason)
2. [ ] [test] Add regression test for trigger scenario
```

**EXIT GATE:** Fix plan documented. ZERO code changes yet.

---

## Phase 3: EXECUTE

7. Apply fix following the checklist exactly.

// turbo
8. Run syntax check:
```bash
python -m py_compile <file>
# or
cd frontend && npx -y tsc --noEmit
```

**EXIT GATE:** Fix applied, syntax passes.

---

## Phase 4: REVIEW

// turbo
9. Verify fix:
```bash
# Run relevant tests
python -m pytest tests/ -x -q -k "<test_name>"
```

10. Confirm:
    - `IMPLEMENTATION MATCHES PLAN EXACTLY`
    - No unrelated code modified
    - Root cause addressed (not just symptom)

11. Commit:
```bash
git add --all :!.tasks/*
git commit -m "fix(<scope>): <description>

Root cause: <one-line explanation>"
```

**EXIT GATE:** Committed with root cause in commit body.
