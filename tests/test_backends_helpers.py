from takopi.backends_helpers import install_issue


def test_install_issue_with_command() -> None:
    issue = install_issue("codex", "brew install codex")
    assert issue.title == "install codex"
    assert any("brew install codex" in line for line in issue.lines)


def test_install_issue_without_command() -> None:
    issue = install_issue("codex", None)
    assert issue.title == "install codex"
    assert any("install instructions" in line for line in issue.lines)
