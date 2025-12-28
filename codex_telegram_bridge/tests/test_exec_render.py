import json

from codex_telegram_bridge.exec_render import ExecProgressRenderer, ExecRenderState, render_event_cli


def _loads(lines: str) -> list[dict]:
    return [json.loads(line) for line in lines.strip().splitlines() if line.strip()]


SAMPLE_STREAM = """
{"type":"thread.started","thread_id":"0199a213-81c0-7800-8aa1-bbab2a035a53"}
{"type":"turn.started"}
{"type":"item.completed","item":{"id":"item_0","type":"reasoning","text":"**Searching for README files**"}}
{"type":"item.started","item":{"id":"item_1","type":"command_execution","command":"bash -lc ls","aggregated_output":"","status":"in_progress"}}
{"type":"item.completed","item":{"id":"item_1","type":"command_execution","command":"bash -lc ls","aggregated_output":"2025-09-11\\nAGENTS.md\\nCHANGELOG.md\\ncliff.toml\\ncodex-cli\\ncodex-rs\\ndocs\\nexamples\\nflake.lock\\nflake.nix\\nLICENSE\\nnode_modules\\nNOTICE\\npackage.json\\npnpm-lock.yaml\\npnpm-workspace.yaml\\nPNPM.md\\nREADME.md\\nscripts\\nsdk\\ntmp\\n","exit_code":0,"status":"completed"}}
{"type":"item.completed","item":{"id":"item_2","type":"reasoning","text":"**Checking repository root for README**"}}
{"type":"item.completed","item":{"id":"item_3","type":"agent_message","text":"Yep — there’s a `README.md` in the repository root."}}
{"type":"turn.completed","usage":{"input_tokens":24763,"cached_input_tokens":24448,"output_tokens":122}}
"""


def test_render_event_cli_sample_stream() -> None:
    state = ExecRenderState()
    out: list[str] = []
    for evt in _loads(SAMPLE_STREAM):
        out.extend(render_event_cli(evt, state))

    assert out == [
        "thread started",
        "turn started",
        "[1] ▸ running: `bash -lc ls`",
        "[1] ✓ ran: `bash -lc ls` (exit 0)",
        "assistant:",
        "  Yep — there’s a `README.md` in the repository root.",
        "turn completed",
    ]


def test_progress_renderer_renders_progress_and_final() -> None:
    r = ExecProgressRenderer(max_actions=5, max_chars=10_000)
    for evt in _loads(SAMPLE_STREAM):
        r.note_event(evt)

    progress = r.render_progress(3.0)
    assert progress.startswith("working · 3s · turn 3")
    assert "[1] ✓ ran: `bash -lc ls` (exit 0)" in progress

    final = r.render_final(3.0, "answer", status="done")
    assert final.startswith("done · 3s · turn 3")
    assert "running:" not in final
    assert "ran:" not in final
    assert final.endswith("answer")

