#!/usr/bin/env bash
# ─────────────────────────────────────────────
#  John · Engineering Manager — CLI Installer
#  Installs John into: global (~/.claude) and/or current project (.claude)
# ─────────────────────────────────────────────
set -e

BLUE='\033[0;34m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RESET='\033[0m'
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo -e "${BLUE}"
echo "  ╔══════════════════════════════════════╗"
echo "  ║   John · Engineering Manager         ║"
echo "  ║   Claude Code CLI Setup              ║"
echo "  ╚══════════════════════════════════════╝"
echo -e "${RESET}"

# ── Ask install scope ──────────────────────────
echo "Where do you want to install John?"
echo "  [1] Global — available in ALL projects  (~/.claude)"
echo "  [2] Project — current project only       (.claude)"
echo "  [3] Both"
echo ""
read -rp "Choice [1/2/3]: " SCOPE

install_global=false
install_project=false

case "$SCOPE" in
  1) install_global=true ;;
  2) install_project=true ;;
  3) install_global=true; install_project=true ;;
  *) echo "Invalid choice. Exiting."; exit 1 ;;
esac

# ── Install function ───────────────────────────
install_to() {
  local TARGET="$1"
  echo -e "\n${YELLOW}→ Installing to: $TARGET${RESET}"

  mkdir -p "$TARGET/commands/john/team"

  cp "$SCRIPT_DIR/.claude/commands/john/init.md"       "$TARGET/commands/john/init.md"
  cp "$SCRIPT_DIR/.claude/commands/john/new.md"        "$TARGET/commands/john/new.md"
  cp "$SCRIPT_DIR/.claude/commands/john/map.md"        "$TARGET/commands/john/map.md"
  cp "$SCRIPT_DIR/.claude/commands/john/audit.md"      "$TARGET/commands/john/audit.md"
  cp "$SCRIPT_DIR/.claude/commands/john/task.md"       "$TARGET/commands/john/task.md"
  cp "$SCRIPT_DIR/.claude/commands/john/commit.md"     "$TARGET/commands/john/commit.md"
  cp "$SCRIPT_DIR/.claude/commands/john/report.md"     "$TARGET/commands/john/report.md"
  cp "$SCRIPT_DIR/.claude/commands/john/team/arch.md"  "$TARGET/commands/john/team/arch.md"
  cp "$SCRIPT_DIR/.claude/commands/john/team/devops.md" "$TARGET/commands/john/team/devops.md"
  cp "$SCRIPT_DIR/.claude/commands/john/team/k8s.md"   "$TARGET/commands/john/team/k8s.md"
  cp "$SCRIPT_DIR/.claude/commands/john/team/gitops.md" "$TARGET/commands/john/team/gitops.md"
  cp "$SCRIPT_DIR/.claude/commands/john/team/infra.md" "$TARGET/commands/john/team/infra.md"
  cp "$SCRIPT_DIR/.claude/commands/john/team/ui.md"    "$TARGET/commands/john/team/ui.md"
  cp "$SCRIPT_DIR/.claude/commands/john/team/search.md" "$TARGET/commands/john/team/search.md"
  cp "$SCRIPT_DIR/.claude/commands/john/team/opensearch.md" "$TARGET/commands/john/team/opensearch.md"

  echo -e "${GREEN}  ✓ Commands installed${RESET}"
}

install_claude_md() {
  local DEST="$1/CLAUDE.md"
  if [ -f "$DEST" ]; then
    echo ""
    echo -e "${YELLOW}  CLAUDE.md already exists at $DEST${RESET}"
    read -rp "  Overwrite? [y/N]: " OVR
    if [[ "$OVR" =~ ^[Yy]$ ]]; then
      cp "$SCRIPT_DIR/CLAUDE.md" "$DEST"
      echo -e "${GREEN}  ✓ CLAUDE.md updated${RESET}"
    else
      echo "  Skipped CLAUDE.md — append the contents manually from CLAUDE.md in this package."
    fi
  else
    cp "$SCRIPT_DIR/CLAUDE.md" "$DEST"
    echo -e "${GREEN}  ✓ CLAUDE.md created${RESET}"
  fi
}

# ── Run installs ───────────────────────────────
if $install_global; then
  install_to "$HOME/.claude"
  install_claude_md "$HOME"
fi

if $install_project; then
  PROJECT_CLAUDE="./.claude"
  install_to "$PROJECT_CLAUDE"
  # For project scope, copy CLAUDE.md into project root
  if [ -f "./CLAUDE.md" ]; then
    echo ""
    echo -e "${YELLOW}  CLAUDE.md already exists in project root${RESET}"
    read -rp "  Append John's config to it? [y/N]: " APP
    if [[ "$APP" =~ ^[Yy]$ ]]; then
      echo "" >> ./CLAUDE.md
      cat "$SCRIPT_DIR/CLAUDE.md" >> ./CLAUDE.md
      echo -e "${GREEN}  ✓ CLAUDE.md updated (appended)${RESET}"
    fi
  else
    cp "$SCRIPT_DIR/CLAUDE.md" ./CLAUDE.md
    echo -e "${GREEN}  ✓ CLAUDE.md created in project root${RESET}"
  fi
fi

# ── Done ──────────────────────────────────────
echo ""
echo -e "${GREEN}✅ John is ready.${RESET}"
echo ""
echo "  Start a Claude Code session in your project, then:"
echo ""
echo "  ${BLUE}/project:john:init${RESET}          Boot John into a new or existing project"
echo "  ${BLUE}/project:john:map${RESET}           Map project components"
echo "  ${BLUE}/project:john:audit${RESET}         Full team audit + strategy"
echo "  ${BLUE}/project:john:task [desc]${RESET}   Delegate a task to a specialist"
echo "  ${BLUE}/project:john:commit${RESET}        Guided commit workflow"
echo "  ${BLUE}/project:john:report${RESET}        Status report"
echo ""
echo "  Specialists:"
echo "  ${BLUE}/project:john:team:arch${RESET}     Solutions Architect"
echo "  ${BLUE}/project:john:team:devops${RESET}   Senior DevOps Engineer"
echo "  ${BLUE}/project:john:team:k8s${RESET}      Kubernetes Engineer"
echo "  ${BLUE}/project:john:team:gitops${RESET}   ArgoCD/Flux GitOps Engineer"
echo "  ${BLUE}/project:john:team:infra${RESET}    Cloud & Infra (Proxmox/KVM/OpenShift)"
echo "  ${BLUE}/project:john:team:ui${RESET}       Senior UI Developer"
echo ""
