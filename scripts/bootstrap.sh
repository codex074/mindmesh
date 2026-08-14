#!/usr/bin/env bash
# Reproducibly clone the TradingAgents dependency repo into MindMesh/.
#
# This folder is gitignored in the parent repo and is version-controlled
# independently upstream. This script makes today's implicit "a folder
# sitting here" setup reproducible on a fresh machine or the eventual VPS.
#
# Pin rationale (see EXECUTION_PLAN.md D8 / A8 / F3):
#   - TradingAgents is pinned to the upstream TauricResearch main SHA that this
#     web app was built and tested against. A bare `git clone` of the branch tip
#     could silently deploy a different, newer (or older) tree.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

TRADINGAGENTS_REMOTE="https://github.com/TauricResearch/TradingAgents.git"
TRADINGAGENTS_SHA="a33fd4c0f134485a43553a2c23a63cb14adbd88f"
TRADINGAGENTS_BRANCH="main"

clone_pinned() {
  local remote="$1" branch="$2" sha="$3" dest="$4"
  if [ -d "$dest/.git" ]; then
    echo "[bootstrap] $dest already exists — skipping (checked out at: $(git -C "$dest" rev-parse --short HEAD))"
    return
  fi
  echo "[bootstrap] cloning $remote (branch $branch) into $dest"
  git clone --branch "$branch" "$remote" "$dest"
  echo "[bootstrap] pinning $dest to $sha"
  git -C "$dest" checkout "$sha"
}

clone_pinned "$TRADINGAGENTS_REMOTE" "$TRADINGAGENTS_BRANCH" "$TRADINGAGENTS_SHA" "$ROOT_DIR/TradingAgents"

echo "[bootstrap] done."
echo "[bootstrap] TradingAgents $(git -C "$ROOT_DIR/TradingAgents" rev-parse --short HEAD)"