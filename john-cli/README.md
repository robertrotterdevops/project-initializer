# John · Engineering Manager for Claude Code

A complete CLI persona system for Claude Code (`claude` CLI). John boots into any project, maps it, runs specialist audits, delegates tasks, and reports back — interactively, without being invasive.

## Quick Install

```bash
git clone <this-repo>
cd john-cli
chmod +x install.sh
./install.sh
```

Then open Claude Code in your project:
```bash
cd your-project
claude
```

## Commands

| Command | Description |
|---------|-------------|
| `/project:john:init` | Boot John into a new or existing project |
| `/project:john:map` | Map and analyse project components |
| `/project:john:audit` | Full team audit — flaws, risks, quick wins |
| `/project:john:task [desc]` | Delegate a task to the right specialist |
| `/project:john:commit` | Guided commit: branch check → tests → commit |
| `/project:john:report` | Structured project status report |

## Specialist Commands

| Command | Specialist |
|---------|-----------|
| `/project:john:team:arch` | Solutions Architect |
| `/project:john:team:devops` | Senior DevOps Engineer |
| `/project:john:team:k8s` | Kubernetes Engineer (RKE2/k3s) |
| `/project:john:team:gitops` | ArgoCD / Flux GitOps Engineer |
| `/project:john:team:infra` | Cloud & Infra (Proxmox/KVM/OpenShift) |
| `/project:john:team:ui` | Senior UI Developer |

## How It Works

```
You (CLI)
  └─ /project:john:init       ← lands John in your project
  └─ /project:john:audit      ← Architect + DevOps + K8s + Infra scan silently
       └─ Report: findings, severity, top-5 strategy
  └─ /project:john:task [x]   ← John picks the right specialist, executes, reports
  └─ /project:john:commit     ← branch guard + test gate + conventional commit
```

## Team Rules (always enforced)
- ✅ DEV environment only
- ✅ Test before deploy
- ✅ Commit before done (feature/* branches)
- ✅ Minimal, clear commits
- ✅ Docs always updated
- ✅ Report back to John

## File Structure

```
john-cli/
├── CLAUDE.md                          ← John's identity (auto-loaded by Claude Code)
├── install.sh                         ← Installer (global or project scope)
├── README.md
└── .claude/
    └── commands/
        └── john/
            ├── init.md                ← /project:john:init
            ├── map.md                 ← /project:john:map
            ├── audit.md               ← /project:john:audit
            ├── task.md                ← /project:john:task
            ├── commit.md              ← /project:john:commit
            ├── report.md              ← /project:john:report
            └── team/
                ├── arch.md            ← /project:john:team:arch
                ├── devops.md          ← /project:john:team:devops
                ├── k8s.md             ← /project:john:team:k8s
                ├── gitops.md          ← /project:john:team:gitops
                ├── infra.md           ← /project:john:team:infra
                └── ui.md              ← /project:john:team:ui
```

## Token Efficiency Design

John is built to be low-token by design:
- Scans use `find`, `grep`, `head` — never reads full large files
- Reports are structured tables, not essays
- One proposal at a time — waits for your response before going further
- Commits are human-confirmed before executing

## Tips

**New project:**
```
/project:john:init my-platform
/project:john:map
/project:john:audit
```

**Existing project, specific task:**
```
/project:john:task set up ArgoCD app-of-apps for the services in ./apps/
```

**Just need the K8s engineer:**
```
/project:john:team:k8s add resource limits to all deployments in ./k8s/
```

**End of day check:**
```
/project:john:report
/project:john:commit
```
