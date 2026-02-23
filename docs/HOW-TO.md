# How to Use the Project Initializer Skill

A beginner-friendly guide. No prior experience with AI skills required.

---

## Table of Contents

1. [What Is This?](#1-what-is-this)
2. [Prerequisites](#2-prerequisites)
3. [Your First Project in 2 Minutes](#3-your-first-project-in-2-minutes)
4. [Understanding What Got Created](#4-understanding-what-got-created)
5. [The Five Project Types](#5-the-five-project-types)
6. [Using It With an AI Assistant](#6-using-it-with-an-ai-assistant)
7. [Using It From the Terminal (No AI Needed)](#7-using-it-from-the-terminal-no-ai-needed)
8. [Common Recipes](#8-common-recipes)
9. [How It Decides Which Skills to Assign](#9-how-it-decides-which-skills-to-assign)
10. [Customising the Tool](#10-customising-the-tool)
11. [Troubleshooting](#11-troubleshooting)
12. [File Map -- What Lives Where](#12-file-map----what-lives-where)

---

## 1. What Is This?

The **Project Initializer** is a small tool that creates a ready-to-use folder
structure for DevOps projects. You give it a project name and a short
description, and it:

- **Detects** what kind of project you are building (Elasticsearch, Kubernetes,
  Terraform, Azure, or GitOps).
- **Assigns skills** -- it picks the right AI skill files to load later so your
  AI assistant already knows the context of your project.
- **Creates folders and starter files** -- README.md, AGENTS.md, Terraform
  stubs, Kubernetes namespace, .gitignore, and the right set of directories for
  your project type.

Think of it like `cookiecutter` or `create-react-app`, but for infrastructure
projects and with built-in AI skill assignment.

### What is a "skill"?

A skill is a folder containing documentation and context that an AI coding
assistant can read to become an expert in a specific topic. For example, the
`devops-02-2026` skill contains knowledge about Elasticsearch sizing and ECK
operators. When you tell your AI assistant to "load" that skill, it reads the
skill files and becomes better at helping you with Elasticsearch work.

Skills live in `~/.config/opencode/skills/`. Each subfolder is one skill.

---

## 2. Prerequisites

You need only one thing:

- **Python 3.9 or newer** (already installed on macOS and most Linux systems)

Verify with:

```bash
python3 --version
```

You should see something like `Python 3.11.5` or higher. Any version from 3.9
onwards works.

There are **no packages to install**. The tool uses only Python's built-in
standard library. No `pip install` needed.

---

## 3. Your First Project in 2 Minutes

Open a terminal and run:

```bash
python3 ~/.config/opencode/skills/project-initializer/scripts/init_project.py \
  --name my-first-project \
  --desc "Elasticsearch cluster on OpenShift with monitoring"
```

That's it. You will see output like:

```
Project created at : ./my-first-project
Category           : elasticsearch
Primary Skill      : devops-02-2026
Assigned Skills    : devops-02-2026, kubernetes-k8s-specialist, platform-engineering, devops-general
Generated files    :
  - ./my-first-project/README.md
  - ./my-first-project/AGENTS.md
  - ./my-first-project/.gitignore
  - ./my-first-project/terraform/main.tf
  - ./my-first-project/terraform/variables.tf
  - ./my-first-project/k8s/namespace.yaml
```

A new folder `my-first-project/` now exists in your current directory with
everything set up.

### Want to preview before creating?

Add `--analyze-only` to see what *would* be created without writing anything
to disk:

```bash
python3 ~/.config/opencode/skills/project-initializer/scripts/init_project.py \
  --name my-first-project \
  --desc "Elasticsearch cluster on OpenShift with monitoring" \
  --analyze-only
```

---

## 4. Understanding What Got Created

After running the tool, your project folder looks like this:

```
my-first-project/
  ├── README.md              <-- Project overview, skill assignments, quick start
  ├── AGENTS.md              <-- Guide for AI agents working on this project
  ├── .gitignore             <-- Standard ignores for Python, IDE, OS files
  ├── terraform/
  │   ├── main.tf            <-- Terraform starter with your project name
  │   └── variables.tf       <-- Input variables with sensible defaults
  ├── k8s/
  │   └── namespace.yaml     <-- Kubernetes namespace with your project name
  ├── scripts/               <-- Empty, for your automation scripts
  ├── docs/                  <-- Empty, for your documentation
  ├── .opencode/context/     <-- Empty, for AI context files
  ├── observability/         <-- (Elasticsearch projects only)
  ├── elasticsearch/         <-- (Elasticsearch projects only)
  └── kibana/                <-- (Elasticsearch projects only)
```

### Key files explained

| File | What It Does |
|------|-------------|
| **README.md** | Lists your project name, description, assigned skills, a quick start guide showing which skills to load, and an ASCII tree of your project structure. This is the first thing a human or AI reads. |
| **AGENTS.md** | Tells an AI assistant how to work with your project: which skill to load first, what each skill does, the suggested execution order, and CLI commands to re-run the initialiser. |
| **.gitignore** | Ready-made ignores so you can `git init` immediately. |
| **terraform/main.tf** | A minimal Terraform config pre-filled with your project name. |
| **k8s/namespace.yaml** | A Kubernetes namespace manifest with your project name as the namespace. |

The extra directories (like `observability/`, `elasticsearch/`, etc.) depend on
your project type. See the next section.

---

## 5. The Five Project Types

The tool recognises five project types. It picks the right one automatically
based on keywords in your project name and description.

### Elasticsearch

**Triggered by words like:** elasticsearch, elastic, eck, kibana, logstash,
beats, observability, logging, metrics, apm

**Extra directories created:** `observability/`, `elasticsearch/`, `kibana/`

**Example:**
```bash
python3 ~/.config/opencode/skills/project-initializer/scripts/init_project.py \
  --name elastic-observability \
  --desc "Elasticsearch and Kibana on OpenShift for logging"
```

### Kubernetes

**Triggered by words like:** kubernetes, k8s, openshift, container, pod,
deployment, service, ingress, helm, operator

**Extra directories created:** `cluster/`, `platform-services/`, `applications/`

**Example:**
```bash
python3 ~/.config/opencode/skills/project-initializer/scripts/init_project.py \
  --name k8s-platform \
  --desc "OpenShift developer platform with services"
```

### Terraform

**Triggered by words like:** terraform, iac, infrastructure, provisioning, cloud

**Extra directories created:** `modules/`, `environments/`, `networking/`

**Example:**
```bash
python3 ~/.config/opencode/skills/project-initializer/scripts/init_project.py \
  --name terraform-infra \
  --desc "Terraform infrastructure for cloud networking"
```

### Azure

**Triggered by words like:** azure, aks, microsoft

**Extra directories created:** `azure/`, `aks/`, `monitoring/`

**Example:**
```bash
python3 ~/.config/opencode/skills/project-initializer/scripts/init_project.py \
  --name azure-platform \
  --desc "Azure AKS platform with monitoring"
```

### GitOps

**Triggered by words like:** fluxcd, flux, gitops, kustomize, helmrelease,
argocd, gitrepository, kustomization

**Extra directories created:** `clusters/`, `infrastructure/`, `apps/`,
`flux-system/`, `base/`, `overlays/`

**Example:**
```bash
python3 ~/.config/opencode/skills/project-initializer/scripts/init_project.py \
  --name gitops-platform \
  --desc "FluxCD GitOps for multi-cluster Kubernetes"
```

### What if the description matches multiple types?

The tool counts keyword matches and picks the type with the most hits. If you
want to force a specific type, use `--type`:

```bash
python3 ~/.config/opencode/skills/project-initializer/scripts/init_project.py \
  --name my-project \
  --desc "Platform with monitoring and cloud" \
  --type gitops
```

---

## 6. Using It With an AI Assistant

This skill works with **any** AI coding tool: Claude Code, OpenCode, ChatGPT,
Gemini, Copilot, Cursor, Windsurf, Aider, Continue.dev, or even a local LLM
running in Ollama or LM Studio.

### Step 1: Ask the AI to create your project

Just describe what you want in plain language. For example:

> "Create a new project called elastic-monitoring for deploying Elasticsearch
> on OpenShift with Terraform"

The AI will run the CLI for you (or you can paste the command yourself):

```bash
python3 ~/.config/opencode/skills/project-initializer/scripts/init_project.py \
  --name elastic-monitoring \
  --desc "Elasticsearch on OpenShift with Terraform" \
  --target ./elastic-monitoring
```

### Step 2: Load the assigned skills

The generated README.md and AGENTS.md tell you (and the AI) which skills to
load. With most AI tools, you do this by opening or referencing the skill
folder. For example, in Claude Code you would type:

```
/skill devops-02-2026
```

In OpenCode:

```
skill("devops-02-2026")
```

Or simply tell the AI: "load the devops-02-2026 skill" -- most tools understand
this.

### Step 3: Start working

Once the skills are loaded, the AI has domain-specific knowledge about your
project type. Ask it to:

- Generate Terraform modules for your infrastructure
- Create Elasticsearch sizing calculations
- Write Kubernetes manifests
- Set up FluxCD GitOps structure
- Whatever your project needs

### Tip: let the AI read AGENTS.md

If you point your AI at the generated `AGENTS.md` file, it will know exactly
which skills to load and in what order -- you don't need to remember anything.

---

## 7. Using It From the Terminal (No AI Needed)

You do not need an AI assistant at all. The CLI works standalone.

### Option A: Web UI (Recommended for Beginners)

The easiest way to use Project Initializer is through the web interface:

1. Start the UI server:

```bash
cd ~/.config/opencode/skills/project-initializer
python3 -m venv .venv
source .venv/bin/activate
pip install -r ui-draft/requirements.txt
uvicorn app:app --app-dir ui-draft/backend --reload --port 8787
```

2. Open your browser:

```
http://localhost:8787
```

The UI provides:
- **Create Project**: Full form with all options
- **Analyze**: Preview skill assignments
- **Git Sync**: Pull/rebase/push repositories
- **Settings**: Theme and preferences
- Dark/light theme toggle
- Recent projects list
- Toast notifications

### Option B: CLI

If you prefer the command line:

```bash
python3 ~/.config/opencode/skills/project-initializer/scripts/init_project.py --help
```

| Option | Required? | What It Does |
|--------|-----------|-------------|
| `--name NAME` | Yes | Your project name. Use kebab-case (words-separated-by-dashes). |
| `--desc "..."` | Yes | A short description of what the project is about. The tool reads this to detect the project type. |
| `--type TYPE` | No | Force a type instead of auto-detecting. One of: `elasticsearch`, `kubernetes`, `terraform`, `azure`, `gitops`. |
| `--target DIR` | No | Where to create the project. Defaults to `./<name>` (a folder in your current directory). |
| `--analyze-only` | No | Show what would be created but don't write any files. Good for previewing. |
| `--chain CHAIN` | No | Force a specific priority chain (advanced -- see Section 9). |
| `--json` | No | Output results as JSON instead of human-readable text. Useful for scripts. |

### Examples

**Preview a project:**
```bash
python3 ~/.config/opencode/skills/project-initializer/scripts/init_project.py \
  --name my-project --desc "Kubernetes platform" --analyze-only
```

**Create in a specific directory:**
```bash
python3 ~/.config/opencode/skills/project-initializer/scripts/init_project.py \
  --name my-project --desc "Terraform infra" --target /home/user/projects/my-project
```

**Get JSON output (for scripting):**
```bash
python3 ~/.config/opencode/skills/project-initializer/scripts/init_project.py \
  --name my-project --desc "Azure AKS" --analyze-only --json
```

**Force project type:**
```bash
python3 ~/.config/opencode/skills/project-initializer/scripts/init_project.py \
  --name my-project --desc "General platform" --type gitops
```

---

## 8. Common Recipes

### Recipe 1: Start an Elasticsearch project with the Web UI

```bash
# Step 1: Start the UI server
cd ~/.config/opencode/skills/project-initializer
source .venv/bin/activate  # if using venv
uvicorn app:app --app-dir ui-draft/backend --reload --port 8787

# Step 2: Open browser
# Navigate to http://localhost:8787

# Step 3: Fill in the form
# - Project Name: elastic-prod
# - Description: "Production Elasticsearch cluster on OpenShift"
# - Target Directory: ~/Projects/elastic-prod
# - Toggle Git options as needed
# - Click "Create Project"

# Step 4: Open in editor
# Click "Open in Zed" or "VS Code"
```

```bash
# Step 1: Create the project
python3 ~/.config/opencode/skills/project-initializer/scripts/init_project.py \
  --name elastic-prod \
  --desc "Production Elasticsearch cluster on OpenShift" \
  --target ~/projects/elastic-prod

# Step 2: Go into the project
cd ~/projects/elastic-prod

# Step 3: Initialise git
git init && git add -A && git commit -m "Initial project scaffold"

# Step 4: Open in your editor and start working
# (replace 'code' with your editor: zed, vim, etc.)
code .
```

### Recipe 2: Check what type a description maps to

```bash
python3 ~/.config/opencode/skills/project-initializer/scripts/init_project.py \
  --name test --desc "OpenShift with Helm and GitOps" --analyze-only
```

This prints the detected category, skills, and structure without creating
anything.

### Recipe 3: Generate JSON for use in another script

```bash
RESULT=$(python3 ~/.config/opencode/skills/project-initializer/scripts/init_project.py \
  --name my-app --desc "Kubernetes deployment" --analyze-only --json)

echo "$RESULT" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d['primary_category'])"
```

### Recipe 4: Create projects for all five types at once

```bash
INIT=~/.config/opencode/skills/project-initializer/scripts/init_project.py

python3 $INIT --name demo-elastic   --desc "Elasticsearch observability"     --target /tmp/demo-elastic
python3 $INIT --name demo-k8s       --desc "Kubernetes platform"             --target /tmp/demo-k8s
python3 $INIT --name demo-terraform --desc "Terraform infrastructure"        --target /tmp/demo-terraform
python3 $INIT --name demo-azure     --desc "Azure AKS platform"             --target /tmp/demo-azure
python3 $INIT --name demo-gitops    --desc "FluxCD GitOps kustomization"    --target /tmp/demo-gitops
```

---

## 9. How It Decides Which Skills to Assign

This section explains the logic under the hood. You don't need to understand
this to use the tool, but it helps if you want to customise it.

### Step 1: Keyword matching

The tool takes your project name + description, lowercases them, and counts how
many times keywords from each category appear:

| Category | Keywords scanned for |
|----------|---------------------|
| elasticsearch | elasticsearch, es, eck, elastic, kibana, logstash, beats, observability, logging, metrics, apm |
| kubernetes | kubernetes, k8s, openshift, container, pod, deployment, service, ingress, helm, operator |
| terraform | terraform, iac, infrastructure, provisioning, cloud |
| azure | azure, aks, azurekubernetesservice, microsoft |
| gitops | fluxcd, flux, gitops, kustomize, helmrelease, argocd, gitrepository, kustomization |

The category with the highest count wins.

### Step 2: Priority chain selection

Each category maps to a "priority chain" -- an ordered list of skills:

| Category | Chain Name | Skill Order (first = primary) |
|----------|-----------|-------------------------------|
| Elasticsearch | `default` | devops-02-2026, kubernetes-k8s-specialist, platform-engineering, devops-general |
| Kubernetes | `kubernetes_first` | kubernetes-k8s-specialist, platform-engineering, devops-02-2026, devops-general |
| Terraform | `terraform_first` | devops-general, kubernetes-k8s-specialist, platform-engineering, devops-02-2026 |
| Azure | `azure_focused` | devops-general, kubernetes-k8s-specialist, platform-engineering, devops-02-2026 |
| GitOps | `gitops_focused` | platform-engineering, devops-general, kubernetes-k8s-specialist, devops-02-2026 |

The first skill in the chain becomes the **primary skill** (the lead expert).
The rest are **secondary skills** (supporting expertise).

### Step 3: Skill validation

The tool checks which skills actually exist on disk in
`~/.config/opencode/skills/`. Skills that don't exist are listed as
"unavailable" but don't cause errors.

### Overriding the chain

You can force a chain with `--chain`:

```bash
python3 ~/.config/opencode/skills/project-initializer/scripts/init_project.py \
  --name my-project --desc "Some project" --chain gitops_focused --analyze-only
```

---

## 10. Customising the Tool

### Adding keywords to an existing category

Edit `priority_chains.json` and add words to the relevant array in
`keyword_mapping`:

```json
"gitops": ["fluxcd", "flux", "gitops", "kustomize", "helmrelease", "argocd",
           "gitrepository", "kustomization", "your-new-keyword"]
```

### Adding a new skill

1. Create the skill folder: `~/.config/opencode/skills/my-new-skill/`
2. Add it to `priority_chains.json` under `skill_mapping`:
   ```json
   "my-new-skill": {
     "available": true,
     "category": "kubernetes",
     "capabilities": ["something", "something-else"]
   }
   ```
3. Add it to one or more chains in `priority_chains`:
   ```json
   "kubernetes_first": ["my-new-skill", "kubernetes-k8s-specialist", ...]
   ```

### Changing the generated README/AGENTS templates

Edit the files in the `templates/` folder:

- `templates/README_template.md` -- controls what README.md looks like
- `templates/AGENTS_template.md` -- controls what AGENTS.md looks like

Templates use `{{variable_name}}` placeholders. Available variables:

| Variable | Example Value |
|----------|--------------|
| `{{project_name}}` | my-elastic-project |
| `{{project_description}}` | Elasticsearch cluster on OpenShift |
| `{{primary_skill}}` | devops-02-2026 |
| `{{assigned_skills_list}}` | devops-02-2026, kubernetes-k8s-specialist |
| `{{secondary_skills_list}}` | - **kubernetes-k8s-specialist**: Supplementary expertise |
| `{{skill_load_commands}}` | load skill kubernetes-k8s-specialist |
| `{{primary_skill_capabilities}}` | elasticsearch-sizing, openshift-deployment |
| `{{project_structure_tree}}` | (ASCII tree of folders) |
| `{{primary_category}}` | elasticsearch |
| `{{priority_chain}}` | default |
| `{{timestamp}}` | 2026-02-09 14:30:00 |

---

## 11. Troubleshooting

### "No skills detected" / category is "generic"

Your description doesn't contain any recognised keywords. Solutions:

- Add relevant keywords to your `--desc` (e.g., include "elasticsearch" or
  "kubernetes")
- Force the type with `--type elasticsearch`
- Run with `--analyze-only` to see what the tool detected

### "python3: command not found"

Python 3 is not installed or not in your PATH. On macOS:

```bash
# Check if python3 exists
which python3

# If not found, install via Homebrew
brew install python
```

### All skills show as "unavailable"

This means the skill folders don't exist in `~/.config/opencode/skills/`. The
tool still works (it creates the project structure and documentation), but the
skills won't be loadable by an AI assistant until the folders exist.

To check what skills are installed:

```bash
ls ~/.config/opencode/skills/
```

### The generated files contain `{{something}}`

This means a template variable wasn't replaced. Check that the variable name in
the template exactly matches one of the supported variables listed in Section 10.
Variable names are case-sensitive.

### "Permission denied" when creating the project

You don't have write access to the target directory. Either:

- Use a different `--target` that you own
- Or omit `--target` to create in the current directory

### I want to regenerate an existing project

Just run the command again with the same `--target`. Existing files will be
overwritten. If you want to keep your changes, commit them to git first.

---

## 12. File Map -- What Lives Where

```
~/.config/opencode/skills/project-initializer/
  ├── SKILL.md                          <-- Main skill documentation (AI reads this)
  ├── priority_chains.json              <-- Configuration: keywords, chains, skills
  ├── priority_chains.yaml              <-- Same config in YAML (human reference only)
  ├── docs/
  │   └── HOW-TO.md                     <-- This file
  ├── reference/
  │   └── quick_reference.md            <-- Cheat sheet for experienced users
  ├── templates/
  │   ├── README_template.md            <-- Template for generated README.md
  │   └── AGENTS_template.md           <-- Template for generated AGENTS.md
  ├── ui-draft/                        <-- Web UI (optional)
  │   ├── frontend/
  │   │   └── index.html               <-- Polished web interface
  │   ├── backend/
  │   │   ├── app.py                   <-- FastAPI server
  │   │   └── backend_api.py           <-- API endpoints
  │   ├── desktop/                     <-- Tauri desktop shell
  │   └── README.md                    <-- UI documentation
  └── scripts/
      ├── init_project.py               <-- CLI entry point (the main command you run)
      ├── project_analyzer.py           <-- Core logic: keyword matching, skill assignment
      ├── generate_structure.py          <-- Folder creation, template rendering
      ├── analyze_project.py            <-- Thin wrapper (backward compatibility)
      └── usage_example.py              <-- Integration tests (run to verify everything works)
```
~/.config/opencode/skills/project-initializer/
  ├── SKILL.md                          <-- Main skill documentation (AI reads this)
  ├── priority_chains.json              <-- Configuration: keywords, chains, skills
  ├── priority_chains.yaml              <-- Same config in YAML (human reference only)
  ├── docs/
  │   └── HOW-TO.md                     <-- This file
  ├── reference/
  │   └── quick_reference.md            <-- Cheat sheet for experienced users
  ├── templates/
  │   ├── README_template.md            <-- Template for generated README.md
  │   └── AGENTS_template.md            <-- Template for generated AGENTS.md
  └── scripts/
      ├── init_project.py               <-- CLI entry point (the main command you run)
      ├── project_analyzer.py           <-- Core logic: keyword matching, skill assignment
      ├── generate_structure.py         <-- Folder creation, template rendering
      ├── analyze_project.py            <-- Thin wrapper (backward compatibility)
      └── usage_example.py              <-- Integration tests (run to verify everything works)
```

### Which file should I edit for...?

| I want to... | Edit this file |
|--------------|----------------|
| Add keywords or skills | `priority_chains.json` |
| Change the generated README | `templates/README_template.md` |
| Change the generated AGENTS.md | `templates/AGENTS_template.md` |
| Add a new project type | `priority_chains.json` + `scripts/project_analyzer.py` |
| Change CLI options | `scripts/init_project.py` |
| Verify everything works | Run `python3 scripts/usage_example.py` |

---

*Last updated: 2026-02-23 -- Project Initializer v1.8*
