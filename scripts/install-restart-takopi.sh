#!/usr/bin/env bash
set -euo pipefail

bin_dir="${HOME}/bin"
claude_dir="${HOME}/.claude/commands"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "$bin_dir" "$claude_dir"

install -m 0755 "${script_dir}/restart-takopi.sh" "${bin_dir}/restart-takopi"
install -m 0644 "${script_dir}/restart-takopi-claude.md" "${claude_dir}/restart-takopi.md"

echo "Installed ${bin_dir}/restart-takopi"
echo "Installed ${claude_dir}/restart-takopi.md"
