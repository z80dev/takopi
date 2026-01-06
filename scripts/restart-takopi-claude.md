# Restart Takopi

Restart the tmux session running Takopi using the global script.

## Instructions

1. Run `restart-takopi` (or `~/bin/restart-takopi` if PATH is missing).
2. The script auto-commits and pushes any uncommitted/unpushed changes in `~/dev/takopi` before restarting.
3. If needed, pass overrides: `restart-takopi <session> <workdir> <command>`.
