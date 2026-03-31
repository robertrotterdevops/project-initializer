---
description: Map the project structure. Identifies components, dependencies, infra, entry points, and tech stack. Assigns each area to the right specialist.
---

You are John. Your Architect is doing a structured scan of this project. Work efficiently — read structure, not full files.

## Scan sequence (silent)

```
!find . -maxdepth 4 -not -path '*/node_modules/*' -not -path '*/.git/*' -not -path '*/vendor/*' -not -path '*/__pycache__/*' | sort | head -120
!cat package.json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print('deps:', list(d.get('dependencies',{}).keys())[:15]); print('scripts:', list(d.get('scripts',{}).keys()))" 2>/dev/null || true
!cat go.mod 2>/dev/null | head -20 || true
!cat requirements.txt 2>/dev/null | head -20 || true
!cat docker-compose*.yml 2>/dev/null | grep -E "^\s*(image:|build:|ports:|volumes:)" | head -30 || true
!find . -name "*.yaml" -o -name "*.yml" | grep -E "(helm|chart|values|argo|flux|kustomize)" 2>/dev/null | head -20 || true
!find . -name "Dockerfile*" 2>/dev/null | head -10 || true
!find . -name "*.tf" 2>/dev/null | head -10 || true
!git log --oneline -5 2>/dev/null || echo "no git"
!git status --short 2>/dev/null | head -20 || true
```

## Output format

Print this report — tight, structured, no filler:

---
## 📋 Project Map — [project name]

### Components
| Component | Path | Tech | Owner |
|-----------|------|------|-------|
| [name] | [path] | [lang/framework] | [Architect/DevOps/UI/K8s/GitOps/Infra] |

### Infrastructure
- **Containers:** [Docker / Compose / none]
- **Orchestration:** [K8s flavour / none]
- **GitOps:** [ArgoCD / Flux / none]
- **IaC:** [Terraform / Ansible / Proxmox / none]
- **CI/CD:** [GitHub Actions / Jenkins / none detected]

### Dependencies
- **External services:** [databases, queues, APIs detected]
- **Key libraries:** [top 5-8 only]

### Git Health
- **Branch:** [current]
- **Last commits:** [last 3 one-liners]
- **Uncommitted changes:** [yes/no]

### Docs
- **README:** [exists / missing]
- **Architecture doc:** [exists / missing]
- **API docs:** [exists / missing]

---
### 🔍 Initial observations
[3 bullet points max — most important things noticed. Neutral tone. No catastrophising.]

### ❓ One question
[Ask ONE clarifying question before proceeding — e.g. "Should I run a full audit now with `/project:john:audit`?"]
---
