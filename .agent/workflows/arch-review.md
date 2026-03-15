---
description: Architecture analysis — deep-dive into modules, identify patterns, gaps, and optimization opportunities.
---

# Architecture Review Workflow

Systematic analysis of a module or subsystem. Produces an actionable report
with findings classified by severity.

---

## Phase 1: Scope Definition

1. Define review scope:
   - Which modules/layers to analyze (backend services, frontend stores, infra)
   - Depth: surface scan vs. line-by-line audit
   - Focus areas: performance, correctness, maintainability, security

2. Create task log:
```bash
mkdir -p .tasks && touch .tasks/arch-review-<scope>.md
```
// turbo

---

## Phase 2: Static Analysis

3. Map the dependency graph:
   - Entry points → services → data layer → external APIs
   - Identify circular dependencies, God objects, or tight coupling
   - Document in a markdown table or mermaid diagram

4. Review each file using `view_file_outline` first, then dive into
   specific functions. Check for:

   | Category | What to Look For |
   |----------|-----------------|
   | **Correctness** | Off-by-one, stale closures, race conditions, missing error handling |
   | **Performance** | N+1 queries, unbounded loops, missing indexes, unnecessary re-renders |
   | **Patterns** | Consistency with project conventions (BaseGenService, strategy pattern, zustand) |
   | **Security** | SQL injection, XSS, secret exposure, missing auth checks |
   | **Resilience** | Retry exhaustion, timeout cascades, missing circuit breakers |

---

## Phase 3: Report

5. Classify findings per `/code-audit` workflow rules:
   - **Confirmed Bug:** verified trigger path + actual impact
   - **Code Smell:** suboptimal but not broken
   - **Theoretical Risk:** unlikely but worth noting

6. For each finding, include:
   - File + line reference
   - Severity: Critical / High / Medium / Low
   - Suggested fix (one-liner)

7. Produce `docs/arch-review-<scope>.md` or present inline.

8. Ask user which findings to action → transition to `/bugfix` or `/feature-dev`.

---

## Anti-Patterns

- DO NOT inflate smells into bugs
- DO NOT assume a function is called without tracing callers
- DO NOT count retry cascades without verifying short-circuit paths
- Quality over quantity — 3 verified bugs > 20 unverified guesses
