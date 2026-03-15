---
description: Docker build, push, and deploy — full CI/CD pipeline for staging and production.
---

# Deploy Workflow

Build, push, and deploy the application via Docker.

---

## Phase 1: Pre-deploy Checks

// turbo
1. Ensure all tests pass:
```bash
cd /Users/hs/workspace/github/comicDramaStudio
python -m py_compile backend/app/main.py
cd frontend && npx -y tsc --noEmit
```

// turbo
2. Verify git status is clean:
```bash
git status --short
```

3. Tag the release if needed:
```bash
git tag -a v<version> -m "Release v<version>"
```

---

## Phase 2: Build

4. Build Docker images:
```bash
# Backend
docker build -t comicstudio-backend:latest -f Dockerfile .

# Frontend (if separate)
docker build -t comicstudio-frontend:latest -f frontend/Dockerfile frontend/
```

5. For cross-platform builds (e.g., deploying to Linux from macOS):
```bash
docker buildx build --platform linux/amd64 -t <registry>/comicstudio-backend:latest -f Dockerfile . --push
```

---

## Phase 3: Push to Registry

6. Tag and push:
```bash
# Tag for registry
docker tag comicstudio-backend:latest <registry>/comicstudio-backend:<version>
docker push <registry>/comicstudio-backend:<version>
```

---

## Phase 4: Deploy

7. Update `docker-compose.yml` image tags on the target server.

8. Deploy:
```bash
# SSH to server or use docker context
docker-compose pull
docker-compose up -d --remove-orphans
```

9. Verify deployment:
```bash
# Health check
curl -s https://<domain>/health
# Check logs
docker-compose logs --tail=50 backend
```

---

## Phase 5: Post-deploy

10. Run smoke test via `/e2e-test` workflow against production URL.

11. Monitor logs for 5 minutes for any errors:
```bash
docker-compose logs -f --tail=0 backend 2>&1 | head -100
```

12. If issues found, rollback:
```bash
docker-compose down
docker tag <registry>/comicstudio-backend:<previous-version> comicstudio-backend:latest
docker-compose up -d
```

---

## Rollback Protocol

If a deployment causes issues:
1. Identify the previous working image tag
2. Roll back immediately — don't debug in production
3. File a `/bugfix` task for the issue
4. Fix, re-test via `/e2e-test`, then retry deployment
