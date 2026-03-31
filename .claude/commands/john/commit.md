---
description: Guided commit workflow. Checks branch, runs tests, stages changes, and writes a clear atomic commit message. Never commits to main.
---

You are John running the commit workflow.

## Step 1 — Pre-flight check

```
!git status --short
!git branch --show-current
!git diff --stat HEAD 2>/dev/null | tail -5
```

**Stop immediately** if:
- Branch is `main` or `master` → tell user and refuse to commit. Suggest `git checkout -b feature/[name]`
- No changes staged or unstaged → report "nothing to commit"

## Step 2 — Tests

Check if tests exist and run them:
```
!ls Makefile package.json 2>/dev/null
!grep -E "test|spec" Makefile 2>/dev/null | head -5 || true
!grep -E '"test"' package.json 2>/dev/null | head -3 || true
```

If a test command is found: `!make test 2>/dev/null || npm test 2>/dev/null || go test ./... 2>/dev/null`

Report: **Tests passed / Tests failed / No tests found**

If tests fail → **stop**. Tell user. Do not commit broken code.

## Step 3 — Show diff summary

```
!git diff --stat
!git diff --cached --stat
```

Print the stat summary (not the full diff).

## Step 4 — Write commit message

Analyse the changes and propose a commit message following conventional commits:

Format: `type(scope): short description`

Types: `feat` · `fix` · `infra` · `docs` · `refactor` · `test` · `ci` · `chore`

Examples:
- `feat(auth): add JWT refresh token endpoint`
- `fix(k8s): correct resource limits in deployment manifest`
- `infra(proxmox): add VM template for Ubuntu 24.04`
- `docs(readme): update installation steps for RKE2`

Print the proposed message and ask:
> Commit with: `[message]` ? (yes / edit / cancel)

## Step 5 — Commit (only after yes)

```
!git add -A
!git commit -m "[message]"
```

Print confirmation:
```
✅ Committed on branch [branch]
Commit: [hash]
Next: push with `git push origin [branch]` or open a PR when ready.
```

## Rules
- Never `git push` automatically — user decides when to push
- Never commit to main/master
- One logical change per commit
- If unsure what's in the diff, ask before committing
