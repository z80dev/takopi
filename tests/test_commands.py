"""Tests for the commands module."""

from pathlib import Path

from takopi.commands import (
    Command,
    CommandCatalog,
    build_command_prompt,
    load_commands_from_dirs,
    normalize_command,
    parse_command_dirs,
    strip_command,
    _parse_command_file,
)
from takopi.telegram.bridge import _trim_command_description


class TestNormalizeCommand:
    def test_simple_name(self) -> None:
        assert normalize_command("review") == "review"

    def test_with_leading_slash(self) -> None:
        assert normalize_command("/review") == "review"

    def test_uppercase(self) -> None:
        assert normalize_command("Review") == "review"

    def test_with_spaces(self) -> None:
        assert normalize_command("code review") == "code_review"

    def test_with_special_chars(self) -> None:
        assert normalize_command("code-review!") == "code_review"

    def test_multiple_underscores(self) -> None:
        assert normalize_command("code__review") == "code_review"

    def test_leading_trailing_underscores(self) -> None:
        assert normalize_command("_review_") == "review"

    def test_empty(self) -> None:
        assert normalize_command("") == ""

    def test_only_special_chars(self) -> None:
        assert normalize_command("---") == ""


class TestBuildCommandPrompt:
    def test_prompt_only(self) -> None:
        command = Command(
            name="review",
            description="Review code",
            prompt="Please review this code for best practices.",
            location=Path("/test"),
            source="test",
        )
        result = build_command_prompt(command, "")
        assert result == "Please review this code for best practices."

    def test_args_only(self) -> None:
        command = Command(
            name="review",
            description="Review code",
            prompt="",
            location=Path("/test"),
            source="test",
        )
        result = build_command_prompt(command, "def foo(): pass")
        assert result == "def foo(): pass"

    def test_prompt_and_args(self) -> None:
        command = Command(
            name="review",
            description="Review code",
            prompt="Please review this code.",
            location=Path("/test"),
            source="test",
        )
        result = build_command_prompt(command, "def foo(): pass")
        assert result == "Please review this code.\n\ndef foo(): pass"

    def test_both_empty(self) -> None:
        command = Command(
            name="review",
            description="Review code",
            prompt="",
            location=Path("/test"),
            source="test",
        )
        result = build_command_prompt(command, "")
        assert result == ""


class TestCommandCatalog:
    def test_empty(self) -> None:
        catalog = CommandCatalog.empty()
        assert catalog.commands == ()
        assert catalog.by_name == {}
        assert catalog.by_command == {}

    def test_from_commands(self) -> None:
        commands = [
            Command(
                name="review",
                description="Review code",
                prompt="Review this.",
                location=Path("/test/review.md"),
                source="test",
            ),
            Command(
                name="explain",
                description="Explain code",
                prompt="Explain this.",
                location=Path("/test/explain.md"),
                source="test",
            ),
        ]
        catalog = CommandCatalog.from_commands(commands)

        assert len(catalog.commands) == 2
        assert "review" in catalog.by_name
        assert "explain" in catalog.by_name
        assert "review" in catalog.by_command
        assert "explain" in catalog.by_command

    def test_deduplication(self) -> None:
        commands = [
            Command(
                name="review",
                description="First",
                prompt="First prompt.",
                location=Path("/test/review1.md"),
                source="test1",
            ),
            Command(
                name="Review",  # Same name, different case
                description="Second",
                prompt="Second prompt.",
                location=Path("/test/review2.md"),
                source="test2",
            ),
        ]
        catalog = CommandCatalog.from_commands(commands)

        # Should keep the second one (overwrites)
        assert len(catalog.commands) == 1
        assert catalog.by_name["review"].description == "Second"

    def test_empty_name_ignored(self) -> None:
        commands = [
            Command(
                name="",
                description="Empty",
                prompt="Empty.",
                location=Path("/test/empty.md"),
                source="test",
            ),
        ]
        catalog = CommandCatalog.from_commands(commands)
        assert len(catalog.commands) == 0


class TestTrimCommandDescription:
    def test_short_description(self) -> None:
        result = _trim_command_description("Short description")
        assert result == "Short description"

    def test_exact_limit(self) -> None:
        text = "x" * 64
        result = _trim_command_description(text)
        assert result == text
        assert len(result) == 64

    def test_over_limit(self) -> None:
        text = "x" * 100
        result = _trim_command_description(text)
        assert result.endswith("...")
        assert len(result) == 64

    def test_normalizes_whitespace(self) -> None:
        result = _trim_command_description("Multiple   spaces\n\there")
        assert result == "Multiple spaces here"

    def test_very_small_limit(self) -> None:
        result = _trim_command_description("Hello world", limit=3)
        assert result == "Hel"


class TestParseCommandFile:
    def test_with_heading(self, tmp_path: Path) -> None:
        path = tmp_path / "review.md"
        path.write_text("# Review code for best practices\n\nPlease review this code.")
        command = _parse_command_file(path, "test")

        assert command is not None
        assert command.name == "review"
        assert command.description == "Review code for best practices"
        assert command.prompt == "Please review this code."

    def test_without_heading(self, tmp_path: Path) -> None:
        path = tmp_path / "review.md"
        path.write_text("Please review this code.")
        command = _parse_command_file(path, "test")

        assert command is not None
        assert command.name == "review"
        assert command.description == "run review"  # Default description
        assert command.prompt == "Please review this code."

    def test_empty_prompt(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.md"
        path.write_text("# Just a heading\n\n")
        command = _parse_command_file(path, "test")

        assert command is None  # Empty prompts are rejected

    def test_with_frontmatter(self, tmp_path: Path) -> None:
        path = tmp_path / "review.md"
        path.write_text(
            "---\n"
            "description: Review code for best practices\n"
            "---\n"
            "\n"
            "Please review this code."
        )
        command = _parse_command_file(path, "test")

        assert command is not None
        assert command.name == "review"
        assert command.description == "Review code for best practices"
        assert command.prompt == "Please review this code."


class TestStripCommand:
    def _make_catalog(self, *names: str) -> CommandCatalog:
        commands = [
            Command(
                name=name,
                description=f"Test {name}",
                prompt="Test prompt.",
                location=Path(f"/test/{name}.md"),
                source="test",
            )
            for name in names
        ]
        return CommandCatalog.from_commands(commands)

    def test_matches_command(self) -> None:
        catalog = self._make_catalog("review", "explain")
        args, command = strip_command("/review the code", commands=catalog)
        assert command is not None
        assert command.name == "review"
        assert args == "the code"

    def test_with_bot_suffix(self) -> None:
        catalog = self._make_catalog("review")
        args, command = strip_command("/review@mybot the code", commands=catalog)
        assert command is not None
        assert command.name == "review"
        assert args == "the code"

    def test_on_own_line(self) -> None:
        catalog = self._make_catalog("review")
        args, command = strip_command("/review\nthe code", commands=catalog)
        assert command is not None
        assert command.name == "review"
        assert args == "the code"

    def test_no_match(self) -> None:
        catalog = self._make_catalog("review")
        args, command = strip_command("/unknown the code", commands=catalog)
        assert command is None
        assert args == "/unknown the code"

    def test_empty_catalog(self) -> None:
        catalog = CommandCatalog.empty()
        args, command = strip_command("/review the code", commands=catalog)
        assert command is None
        assert args == "/review the code"

    def test_empty_text(self) -> None:
        catalog = self._make_catalog("review")
        args, command = strip_command("", commands=catalog)
        assert command is None
        assert args == ""

    def test_no_slash(self) -> None:
        catalog = self._make_catalog("review")
        args, command = strip_command("review the code", commands=catalog)
        assert command is None
        assert args == "review the code"

    def test_normalizes_name(self) -> None:
        catalog = self._make_catalog("code_review")
        args, command = strip_command("/code-review file.py", commands=catalog)
        assert command is not None
        assert command.name == "code_review"

    def test_with_frontmatter_and_heading(self, tmp_path: Path) -> None:
        path = tmp_path / "review.md"
        path.write_text(
            "---\n"
            "title: Command title\n"
            "---\n"
            "# Heading\n"
            "\n"
            "Please review this code."
        )
        command = _parse_command_file(path, "test")

        assert command is not None
        assert command.name == "review"
        assert command.description == "Command title"
        assert command.prompt == "Please review this code."

    def test_file_not_found(self, tmp_path: Path) -> None:
        path = tmp_path / "missing.md"
        command = _parse_command_file(path, "test")
        assert command is None

    def test_with_runner(self, tmp_path: Path) -> None:
        path = tmp_path / "restart.md"
        path.write_text(
            "---\n"
            "description: Restart service\n"
            "runner: opencode\n"
            "---\n"
            "\n"
            "Restart the service now."
        )
        command = _parse_command_file(path, "test")

        assert command is not None
        assert command.name == "restart"
        assert command.description == "Restart service"
        assert command.prompt == "Restart the service now."
        assert command.runner == "opencode"

    def test_without_runner(self, tmp_path: Path) -> None:
        path = tmp_path / "review.md"
        path.write_text("# Review code\n\nReview this code.")
        command = _parse_command_file(path, "test")

        assert command is not None
        assert command.runner is None


class TestParseCommandDirs:
    def test_no_config(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        result = parse_command_dirs({})
        assert result == []

    def test_no_config_uses_claude_dir(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        claude_dir = tmp_path / ".claude" / "commands"
        claude_dir.mkdir(parents=True)
        result = parse_command_dirs({})
        assert result == [claude_dir]

    def test_no_config_uses_takopi_dir(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        takopi_dir = tmp_path / ".takopi" / "commands"
        takopi_dir.mkdir(parents=True)
        result = parse_command_dirs({})
        assert result == [takopi_dir]

    def test_no_config_uses_both_dirs(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        takopi_dir = tmp_path / ".takopi" / "commands"
        claude_dir = tmp_path / ".claude" / "commands"
        takopi_dir.mkdir(parents=True)
        claude_dir.mkdir(parents=True)
        result = parse_command_dirs({})
        # takopi dir comes first (higher priority)
        assert result == [takopi_dir, claude_dir]

    def test_string_value(self, tmp_path: Path) -> None:
        config = {"command_dirs": str(tmp_path)}
        result = parse_command_dirs(config)
        assert result == [tmp_path]

    def test_list_value(self, tmp_path: Path) -> None:
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        dir1.mkdir()
        dir2.mkdir()

        config = {"command_dirs": [str(dir1), str(dir2)]}
        result = parse_command_dirs(config)
        assert result == [dir1, dir2]

    def test_nonexistent_dir(self, tmp_path: Path) -> None:
        config = {"command_dirs": str(tmp_path / "nonexistent")}
        result = parse_command_dirs(config)
        assert result == []

    def test_invalid_type(self) -> None:
        config = {"command_dirs": 123}
        result = parse_command_dirs(config)
        assert result == []


class TestLoadCommandsFromDirs:
    def test_loads_md_files(self, tmp_path: Path) -> None:
        (tmp_path / "review.md").write_text("# Review code\n\nReview this code.")
        (tmp_path / "explain.md").write_text("# Explain code\n\nExplain this code.")
        (tmp_path / "ignored.txt").write_text("Not a markdown file")

        catalog = load_commands_from_dirs([tmp_path])

        assert len(catalog.commands) == 2
        assert "review" in catalog.by_command
        assert "explain" in catalog.by_command

    def test_multiple_dirs(self, tmp_path: Path) -> None:
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        dir1.mkdir()
        dir2.mkdir()

        (dir1 / "review.md").write_text("# Review\n\nReview.")
        (dir2 / "explain.md").write_text("# Explain\n\nExplain.")

        catalog = load_commands_from_dirs([dir1, dir2])

        assert len(catalog.commands) == 2

    def test_empty_dirs(self, tmp_path: Path) -> None:
        catalog = load_commands_from_dirs([tmp_path])
        assert len(catalog.commands) == 0
