---
description: Rules for code auditing — only report confirmed bugs with trigger paths, separate code smells
---

# Code Audit Workflow

## Classification Rules

Every finding MUST be classified into exactly ONE of these categories:

### 1. Confirmed Bug
- **Requirement:** You can describe a specific, concrete trigger scenario that causes incorrect behavior in the CURRENT codebase
- **Must include:**
  - Trigger path: exact steps or code flow that causes the bug
  - Actual behavior vs expected behavior
  - Which users/flows are affected
- **Must NOT include:** theoretical risks, dead code issues, or "if someone changes X in the future" scenarios

### 2. Code Smell / Tech Debt
- Redundant code, dead code, suboptimal patterns
- Things that don't cause incorrect behavior today but make the code harder to maintain
- No trigger path required, just explain why it's suboptimal

### 3. Theoretical Risk
- Issues in code paths that are currently unreachable or extremely unlikely
- Race conditions that require specific unlikely user behavior
- Must explicitly state the probability and conditions required to trigger

## Verification Checklist (MANDATORY before reporting any Confirmed Bug)

Before classifying anything as a "Confirmed Bug", you MUST verify ALL of the following:

- [ ] **Caller check:** Is the buggy function actually called? By whom? Trace the full call chain.
- [ ] **Execution path:** Walk through the exact runtime flow step by step. Does the bug actually trigger?
- [ ] **Guard check:** Are there upstream guards, fallbacks, or error handlers that prevent the bug from manifesting?
- [ ] **Impact check:** If the bug triggers, what is the actual user-visible impact? Not theoretical — actual.

If ANY of these checks fail, downgrade to "Code Smell" or "Theoretical Risk".

## Output Format

```markdown
## Confirmed Bugs (verified, with trigger path)

### BUG-1: [title]
- **Trigger:** [exact steps or code flow]
- **Impact:** [actual user-visible consequence]
- **Files:** [affected files with line numbers]

## Code Smells / Tech Debt

### SMELL-1: [title]
- **Issue:** [description]
- **Files:** [affected files]

## Theoretical Risks (low probability)

### RISK-1: [title]  
- **Condition:** [what must happen for this to trigger]
- **Probability:** [low/very low]
```

## Anti-Patterns to Avoid

1. **DO NOT** inflate code smells into bugs to seem thorough
2. **DO NOT** report dead code issues as bugs — classify as Code Smell
3. **DO NOT** multiply retry counts across layers without verifying the actual execution path (check for fallbacks/short-circuits)
4. **DO NOT** assume a function is called without checking its callers
5. **DO NOT** report more than you can verify — quality over quantity
