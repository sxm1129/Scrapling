---
description: End-to-end feature development — from research to commit. Enforces RESEARCH → INNOVATE → PLAN → EXECUTE → REVIEW mode transitions.
---

# Feature Development Workflow

Full lifecycle for adding a new feature to the codebase. Follows the mandatory
mode state machine: `RESEARCH → INNOVATE → PLAN → EXECUTE → REVIEW`.

---

## Phase 1: RESEARCH

**Goal:** Understand the problem space and existing code.

1. Create branch and task log:
```bash
git checkout -b task/<id>
mkdir -p .tasks && touch .tasks/<id>.md
```
// turbo

2. Identify all files/modules affected by the feature. Use `rg`, `view_file_outline`,
   and `list_dir` to map dependencies, data models, API endpoints, and UI components.

3. Document findings in `.tasks/<id>.md` under a `## Research` heading:
   - Affected files (with line ranges)
   - Existing patterns to follow
   - External API contracts or schemas
   - Potential conflict points

**EXIT GATE:** Research summary written. ZERO code changes.

---

## Phase 2: INNOVATE

**Goal:** Brainstorm approaches and evaluate trade-offs.

4. List 2–3 candidate approaches with **Pros / Cons / Complexity** for each.

5. Consider:
   - Consistency with existing architecture patterns (`BaseGenService`, strategy pattern, zustand store)
   - Performance implications (DB queries, API calls, WS broadcasts)
   - Error handling and retry behavior
   - Breaking changes to existing consumers

6. Recommend ONE approach with rationale. Record in `.tasks/<id>.md` under `## Design Decision`.

**EXIT GATE:** Approach selected. ZERO code changes.

---

## Phase 3: PLAN

**Goal:** Write exact technical spec with numbered checklist.

7. Write `IMPLEMENTATION CHECKLIST` in `.tasks/<id>.md`:
```markdown
## IMPLEMENTATION CHECKLIST
1. [ ] [Backend] Add `Foo` model in `backend/app/models/foo.py`
2. [ ] [Backend] Add `GET /api/foo` endpoint in `backend/app/api/foo.py`
3. [ ] [Frontend] Add `useFooStore` in `frontend/src/stores/useFooStore.ts`
4. [ ] [Frontend] Add `FooCard` component in `frontend/src/components/FooCard.tsx`
5. [ ] [Test] Add unit test in `tests/test_foo.py`
```

8. Each checklist item MUST specify:
   - Layer tag: `[Backend]`, `[Frontend]`, `[Infra]`, `[Test]`
   - Exact file path (new or existing)
   - Brief description of the change

9. Request user review of the plan before proceeding.

**EXIT GATE:** User approves checklist. ZERO implementation code written.

---

## Phase 4: EXECUTE

**Goal:** Implement exactly what the checklist says.

10. Work through checklist items sequentially. For each item:
    - Mark `[/]` when starting
    - Write code following project conventions:
      - Python: type hints, Google docstrings, Pydantic models
      - TypeScript: strict types, functional components, zustand patterns
    - Mark `[x]` when done

11. Code modification rules:
    - NEVER rewrite entire files
    - ONLY modify the specific code block, wrapped in existing context
    - NEVER touch unrelated code

12. Run syntax/type checks after each batch of changes:
```bash
# Backend
python -m py_compile <file>
# Frontend
npx -y tsc --noEmit
```
// turbo

13. If errors occur, enter `ERROR_RECOVERY`:
    - Describe the error
    - Propose fix
    - Ask user before applying if the fix deviates from plan

**EXIT GATE:** All checklist items marked `[x]`. Syntax checks pass.

---

## Phase 5: REVIEW

**Goal:** Verify implementation matches plan exactly.

14. Compare implementation against checklist. Explicitly state:
    - `IMPLEMENTATION MATCHES PLAN EXACTLY`, or
    - Flag specific deviations with justification

// turbo
15. Run full verification:
```bash
# Backend syntax
python -m py_compile backend/app/**/*.py
# Frontend types
cd frontend && npx -y tsc --noEmit
# Tests (if applicable)
cd ../tests && python -m pytest -x -q
```

16. Stage and commit (exclude task logs):
```bash
git add --all :!.tasks/*
git commit -m "<type>(<scope>): <description>"
```

**Commit message format:** `<type>(<scope>): <description>`
- Types: `feat`, `fix`, `refactor`, `perf`, `docs`, `test`, `chore`
- Scope: module or component name
- Description: imperative mood, ≤72 chars

**EXIT GATE:** Committed. Task log updated with final status.
