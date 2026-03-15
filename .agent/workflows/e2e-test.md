---
description: Browser-based E2E testing — full-stack flow verification with screenshots.
---

# E2E Testing Workflow

End-to-end testing of user-facing flows using the browser subagent.
Covers backend API + frontend UI in a real environment.

---

## Phase 1: Environment Setup

1. Ensure backend and frontend are running:
```bash
# Backend (port 9001)
cd /Users/hs/workspace/github/comicDramaStudio && bash server.sh start
# Frontend (port 9000)
cd frontend && npm run dev -- --port 9000
```

2. Verify services are healthy:
```bash
curl -s http://localhost:9001/health | head -5
curl -s http://localhost:9000 | head -5
```
// turbo

---

## Phase 2: Define Test Scenarios

3. List the user flows to verify. Example scenarios for this project:

| Flow | Steps |
|------|-------|
| **Create Project** | Open homepage → Click "新建项目" → Fill title → Submit → Verify project card |
| **Generate Outline** | Open project → Click "生成大纲" → Wait for SSE pipeline → Verify outline text |
| **Episode Management** | Navigate to episode → Verify Kanban → Check scene cards |
| **Image Generation** | Click "生成素材" → Wait for WS update → Verify image appears |
| **Video Composition** | Click "合成视频" → Monitor progress → Verify final video |

---

## Phase 3: Execute Tests

4. For each flow, use `browser_subagent` with a detailed task description:
   - Specify exact URL to navigate to
   - Describe expected elements (buttons, text, images)
   - Define success/failure conditions
   - Request screenshots at key checkpoints

5. Example browser test:
```
Task: Navigate to http://localhost:9000, click the "新建项目" button,
enter "测试项目" as the title, submit the form. Verify that a project
card with title "测试项目" appears on the dashboard. Take a screenshot
when done. Return the project title and URL.
```

6. Between browser tests, verify backend state:
```bash
curl -s http://localhost:9001/api/projects | python -m json.tool | head -20
```
// turbo

---

## Phase 4: Report

7. Compile results:

| Flow | Status | Screenshot | Notes |
|------|--------|------------|-------|
| Create Project | ✅ Pass | [screenshot](file:///..) | — |
| Generate Outline | ❌ Fail | [screenshot](file:///..) | SSE timeout |

8. For any failures:
   - Capture error screenshot
   - Check backend logs: `tail -50 .logs/backend.log`
   - File a bug via `/bugfix` workflow if issue confirmed

---

## Best Practices

- Always wait for async operations (WS messages, SSE streams) before asserting
- Use `waitForPreviousTools: true` when browser state depends on API calls
- Take screenshots at key state transitions for documentation
- Clean up test data after runs if applicable
