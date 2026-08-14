#!/usr/bin/env bash
# Install the repository launcher as the user-level `mindmesh` command, then
# start the app. No sudo and no global Python installation are required.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${MINDMESH_BIN_DIR:-$HOME/.local/bin}"
COMMAND_PATH="$INSTALL_DIR/mindmesh"
LAUNCHER_PATH="$PROJECT_DIR/mindmesh"

log() {
  printf '[mindmesh] %s\n' "$1"
}

if [ ! -x "$LAUNCHER_PATH" ]; then
  printf '[mindmesh] ERROR: launcher is missing or not executable: %s\n' "$LAUNCHER_PATH" >&2
  exit 1
fi

mkdir -p "$INSTALL_DIR"

if [ -e "$COMMAND_PATH" ] && [ ! -L "$COMMAND_PATH" ]; then
  printf '[mindmesh] ERROR: %s already exists and is not a symlink; it was not changed.\n' "$COMMAND_PATH" >&2
  exit 1
fi

ln -sfn "$LAUNCHER_PATH" "$COMMAND_PATH"
log "installed command: $COMMAND_PATH"

case ":$PATH:" in
  *":$INSTALL_DIR:"*) ;;
  *)
    shell_name="$(basename "${SHELL:-}")"
    case "$shell_name" in
      zsh) shell_profile="$HOME/.zshrc" ;;
      bash) shell_profile="$HOME/.bashrc" ;;
      *) shell_profile="" ;;
    esac

    if [ -n "$shell_profile" ]; then
      if [ "$INSTALL_DIR" = "$HOME/.local/bin" ]; then
        path_line='export PATH="$HOME/.local/bin:$PATH"'
      else
        printf -v quoted_install_dir '%q' "$INSTALL_DIR"
        path_line="export PATH=$quoted_install_dir:\$PATH"
      fi
      if [ ! -f "$shell_profile" ] || ! grep -Fqx "$path_line" "$shell_profile"; then
        printf '\n# MindMesh user commands\n%s\n' "$path_line" >> "$shell_profile"
        log "added $INSTALL_DIR to PATH in $shell_profile (effective in new terminals)"
      fi
    else
      log "add $INSTALL_DIR to PATH to use 'mindmesh' in future terminals"
    fi
    ;;
esac

log "starting the app; next time, run: mindmesh"
exec "$COMMAND_PATH" "$@"
