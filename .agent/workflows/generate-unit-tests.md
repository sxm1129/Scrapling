---
description: generate-unit-tests
---

# Unit Test Generation Workflow

Generate comprehensive unit tests for a module or function.

---

## Phase 1: Analyze Target

// turbo
1. Read the target file with `view_file_outline` to understand structure.

2. For each function/class, identify:
   - Input types and valid ranges
   - Expected outputs for normal cases
   - Edge cases: empty, null, boundary values, type errors
   - External dependencies to mock (DB, API, file system)
   - Error paths: what exceptions can be raised

---

## Phase 2: Design Test Cases

3. For each function, plan test matrix:

| Case Type | Description |
|-----------|-------------|
| **Happy path** | Normal input → expected output |
| **Edge case** | Empty list, zero, None, max int |
| **Error path** | Invalid input, missing dependency, timeout |
| **Integration** | Multiple functions working together |

4. Apply naming convention: `test_<function>_<scenario>_<expected_result>`
   - Example: `test_parse_scenes_empty_script_returns_empty_list`

---

## Phase 3: Write Tests

5. Create test file: `tests/test_<module>.py`

6. Follow project conventions:
   - Use `pytest` with fixtures
   - Mock external dependencies with `unittest.mock.patch`
   - Use `pytest.mark.asyncio` for async functions
   - Group related tests in classes: `class TestFunctionName:`

7. Test file template:
```python
"""Tests for <module>."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Import target module
from app.<module> import <function>


class Test<FunctionName>:
    """Test suite for <function>."""

    def test_happy_path(self):
        """Normal input produces expected output."""
        result = <function>(valid_input)
        assert result == expected_output

    def test_edge_case_empty(self):
        """Empty input handled gracefully."""
        result = <function>([])
        assert result == []

    def test_error_raises(self):
        """Invalid input raises ValueError."""
        with pytest.raises(ValueError, match="expected message"):
            <function>(invalid_input)

    @pytest.mark.asyncio
    async def test_async_function(self):
        """Async function returns expected result."""
        with patch("app.<module>.<dependency>", new_callable=AsyncMock) as mock:
            mock.return_value = expected
            result = await <async_function>(input)
            assert result == expected
```

---

## Phase 4: Verify

// turbo
8. Run tests:
```bash
cd /Users/hs/workspace/github/comicDramaStudio && python -m pytest tests/test_<module>.py -v --tb=short
```

9. Ensure:
   - All tests pass
   - No tests are testing implementation details (brittle)
   - Coverage of critical paths is adequate

10. Commit:
```bash
git add tests/
git commit -m "test(<module>): add unit tests for <function>"
```
