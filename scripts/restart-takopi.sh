#!/usr/bin/env bash
set -euo pipefail

session="${1:-3}"
workdir="${2:-$HOME/dev}"
command="${3:-takopi}"
repo_dir="${TAKOPI_REPO_DIR:-$HOME/dev/takopi}"

ensure_takopi_synced() {
  if [[ ! -d "${repo_dir}/.git" ]]; then
    echo "Takopi repo not found at ${repo_dir}; skipping git sync checks."
    return 0
  fi

  if [[ -n "$(git -C "$repo_dir" status --porcelain)" ]]; then
    echo "Uncommitted changes detected in ${repo_dir}; committing before restart."
    git -C "$repo_dir" add -A
    git -C "$repo_dir" commit -m "chore: pre-restart sync ($(date -u +%Y-%m-%dT%H:%M:%SZ))"
  fi

  if git -C "$repo_dir" rev-parse --abbrev-ref --symbolic-full-name "@{u}" >/dev/null 2>&1; then
    ahead_count="$(git -C "$repo_dir" rev-list --count "@{u}..HEAD")"
    if [[ "$ahead_count" -gt 0 ]]; then
      echo "Pushing ${ahead_count} commit(s) from ${repo_dir}."
      git -C "$repo_dir" push
    fi
  else
    echo "No upstream configured for ${repo_dir}; skipping push."
  fi
}

ensure_takopi_synced

if tmux has-session -t "$session" 2>/dev/null; then
  tmux send-keys -t "$session" C-c
  tmux send-keys -t "$session" "cd $workdir" Enter
  tmux send-keys -t "$session" "$command" Enter
else
  tmux new-session -d -s "$session" -c "$workdir"
  tmux send-keys -t "$session" "$command" Enter
fi
