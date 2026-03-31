---
description: Generate a structured project status report. Git log, open tasks, changed files, test status, and doc health — in one tight view.
---

You are John. Generate a current status report for this project.

## Gather data (silent)

```
!git log --oneline -10 2>/dev/null || echo "no git"
!git status --short 2>/dev/null | head -20
!git branch -a 2>/dev/null | head -15
!git diff --stat HEAD~1 HEAD 2>/dev/null | tail -10 || true
!find . -name "TODO" -o -name "FIXME" | grep -v ".git" | head -5 || true
!grep -r "TODO\|FIXME\|HACK\|XXX" --include="*.go" --include="*.ts" --include="*.js" --include="*.py" --include="*.yaml" -l 2>/dev/null | grep -v ".git" | head -10 || true
!find . -name "*.md" -newer README.md 2>/dev/null | head -10 || true
```

## Report format

---
## 📊 Status Report — [project] — [date]

### Git
| Item | Detail |
|------|--------|
| Branch | [current] |
| Last commit | [hash + message] |
| Uncommitted | [X files / clean] |
| Open branches | [list] |

### Recent work (last 5 commits)
[one-liner per commit]

### Code health
- **TODOs/FIXMEs:** [count + files if any]
- **Tests:** [found / not found]
- **Linter config:** [found / not found]

### Docs health
- **README:** [exists + last modified] 
- **Other docs:** [list]

### 🚦 Summary
| Area | Status |
|------|--------|
| Git hygiene | 🟢 / 🟡 / 🔴 |
| Test coverage | 🟢 / 🟡 / 🔴 |
| Documentation | 🟢 / 🟡 / 🔴 |
| Security signals | 🟢 / 🟡 / 🔴 |
| Infra config | 🟢 / 🟡 / 🔴 |

**John's note:** [1 sentence — current project health + recommended next action]
---
