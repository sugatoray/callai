"""CA-3: CLI unit tests (in-process). End-to-end behaviour is covered by conformance/cli."""

import io
import json
import os
import time

import pytest

from callai import cli
from callai.adapters import get_adapter
from callai.adapters.base import Adapter
from callai.config import Config, HarnessConfig
from callai.errors import UsageError
from callai.request import Request
from callai.result import Completed, Result


class FakeStdin(io.StringIO):
    def __init__(self, text="", tty=False):
        super().__init__(text)
        self._tty = tty

    def isatty(self):
        return self._tty


# --- passthrough split ------------------------------------------------------


@pytest.mark.parametrize(
    ("argv", "own", "extra"),
    [
        (["-n", "x", "-p", "hi"], ["-n", "x", "-p", "hi"], []),
        (["-n", "x", "--", "--max-turns", "3"], ["-n", "x"], ["--max-turns", "3"]),
        (["--", "--", "a"], [], ["--", "a"]),
    ],
)
def test_split_passthrough(argv, own, extra):
    assert cli.split_passthrough(argv) == (own, extra)


# --- stdin / prompt rules (DESIGN §3) ---------------------------------------


def test_read_stdin_ignores_tty_and_missing():
    assert cli.read_stdin(FakeStdin("typed", tty=True)) == ""
    assert cli.read_stdin(None) == ""


def test_read_stdin_strips_trailing_newlines_only():
    assert cli.read_stdin(FakeStdin("  a\nb\r\n\n")) == "  a\nb"


@pytest.fixture
def pipe():
    """A real OS pipe as text stdin; the test controls whether the writer sends data or closes."""
    r, w = os.pipe()
    reader = os.fdopen(r, encoding="utf-8")
    writer = os.fdopen(w, "w", encoding="utf-8")
    yield reader, writer
    reader.close()
    if not writer.closed:
        writer.close()


def test_read_stdin_idle_pipe_gives_up_after_wait(pipe, capsys):
    reader, _writer = pipe  # writer stays open and silent, like an agent's stdin
    start = time.monotonic()
    assert cli.read_stdin(reader, wait=0.2) == ""
    assert time.monotonic() - start < 2
    err = capsys.readouterr().err
    assert "callai: warning: no stdin data received in 0.2s, proceeding without it" in err
    assert "< /dev/null" in err


def test_read_stdin_pipe_with_data_is_read_to_eof(pipe, capsys):
    reader, writer = pipe
    writer.write("diff\n")
    writer.close()
    assert cli.read_stdin(reader, wait=0.2) == "diff"
    assert capsys.readouterr().err == ""


def test_read_stdin_closed_empty_pipe_needs_no_warning(pipe, capsys):
    reader, writer = pipe
    writer.close()
    assert cli.read_stdin(reader, wait=5) == ""
    assert capsys.readouterr().err == ""


def test_read_stdin_without_fileno_reads_directly():
    assert cli.read_stdin(FakeStdin("x\n"), wait=0.01) == "x"


@pytest.mark.parametrize(
    ("environ", "expected"),
    [
        ({}, 3.0),
        ({"CALLAI_STDIN_WAIT": "0.5"}, 0.5),
        ({"CALLAI_STDIN_WAIT": ""}, 3.0),
        ({"CALLAI_STDIN_WAIT": "0"}, 0.0),
    ],
)
def test_stdin_wait_from_env(environ, expected):
    assert cli.stdin_wait(environ) == expected


def test_read_stdin_on_windows_reads_without_waiting(monkeypatch):
    monkeypatch.setattr(cli.os, "name", "nt")  # select() can't watch pipes there
    assert cli._stdin_ready(FakeStdin(), 0.01) is True


def test_read_stdin_read_error_counts_as_no_input():
    class Broken(FakeStdin):
        def read(self, *a):
            raise OSError("bad fd")

    assert cli.read_stdin(Broken()) == ""


@pytest.mark.parametrize("value", ["soon", "-1", "nan", "inf"])
def test_stdin_wait_invalid_is_usage_error(value):
    with pytest.raises(UsageError, match="CALLAI_STDIN_WAIT"):
        cli.stdin_wait({"CALLAI_STDIN_WAIT": value})


@pytest.mark.parametrize(
    ("prompt", "stdin", "expected"),
    [
        ("hi", "", "hi"),
        ("review", "diff", "review\n\ndiff"),
        ("-", "all of it", "all of it"),
        (None, "piped", "piped"),
    ],
)
def test_resolve_prompt(prompt, stdin, expected):
    assert cli.resolve_prompt(prompt, stdin) == expected


@pytest.mark.parametrize(("prompt", "stdin"), [(None, ""), ("-", ""), ("", "")])
def test_resolve_prompt_missing_is_usage_error(prompt, stdin):
    with pytest.raises(UsageError, match="prompt"):
        cli.resolve_prompt(prompt, stdin)


# --- request building -------------------------------------------------------


def _request(argv, stdin="", environ=None, config=None):
    own, extra = cli.split_passthrough(argv)
    ns = cli.build_parser().parse_args(own)
    return cli.make_request(ns, extra, stdin, environ or {}, config)


def test_make_request_maps_all_options(tmp_path):
    req = _request(
        [
            "-n", "claude-code", "-p", "hi", "-m", "opus", "-o", "json", "-C", str(tmp_path),
            "--timeout", "2.5", "--permission", "auto", "--system-prompt", "S", "--", "--x",
        ]
    )  # fmt: skip
    assert (req.harness_name, req.prompt, req.model, req.output_format) == ("claude-code", "hi", "opus", "json")
    assert (req.cwd, req.timeout, req.permission, req.system_prompt) == (str(tmp_path), 2.5, "auto", "S")
    assert req.extra_args == ("--x",)


def test_make_request_resume_and_continue():
    # CA-15a: no -c short form; -c is already --command.
    assert _request(["-n", "codex", "-p", "hi", "--resume", "S1"]).resume == "S1"
    assert _request(["-n", "codex", "-p", "hi", "--continue"]).continue_session is True
    assert _request(["-n", "codex", "-c", "hi"]).continue_session is False


def test_make_request_tool_from_env_and_flag_wins():
    assert _request(["-p", "hi"], environ={"CALLAI_HARNESS_NAME": "claude-code"}).harness_name == "claude-code"
    with pytest.raises(UsageError, match="unknown harness 'nope'"):
        _request(["-n", "nope", "-p", "hi"], environ={"CALLAI_HARNESS_NAME": "claude-code"})


def test_make_request_missing_harness():
    with pytest.raises(UsageError, match="no harness given"):
        _request(["-p", "hi"], environ={"CALLAI_HARNESS_NAME": ""})


def _ns(argv):
    own, extra = cli.split_passthrough(argv)
    return cli.build_parser().parse_args(own), extra


def test_preflight_refuses_before_any_prompt_exists():
    ns, extra = _ns(["-n", "hermes", "--permission", "read-only"])  # prompt would come from stdin
    with pytest.raises(UsageError, match="read-only"):
        cli.preflight(ns, extra, {})


def test_preflight_returns_adapter():
    ns, extra = _ns(["-n", "claude-code"])
    assert cli.preflight(ns, extra, {}).name == "claude-code"


def test_main_does_not_read_stdin_after_a_usage_error(monkeypatch):
    class Exploding(FakeStdin):
        def read(self, *a):
            raise AssertionError("stdin was read")

    monkeypatch.setattr("sys.stdin", Exploding())
    assert cli.main(["-n", "opencode", "--permission", "auto"]) == 2


# --- config file and CALLAI_* defaults (CA-12, DESIGN §6) ----------------------

CONF = Config(
    default_harness="codex",
    model="fast",
    timeout=600,
    harnesses={"codex": HarnessConfig(binary="~/bin/codex", model="o3", extra_args=("--from-config",))},
    aliases={"fast": {"claude-code": "haiku", "codex": "gpt-5-codex-mini"}},
)


def test_config_default_harness_is_last_resort():
    assert _request(["-p", "hi"], config=CONF).harness_name == "codex"
    pi = {"CALLAI_HARNESS_NAME": "pi"}  # -m x below: CONF's default model is an alias with no pi/grok entry
    assert _request(["-p", "hi", "-m", "x"], environ=pi, config=CONF).harness_name == "pi"
    assert _request(["-n", "grok", "-p", "hi", "-m", "x"], environ=pi, config=CONF).harness_name == "grok"


def test_no_harness_anywhere_mentions_the_config_file():
    with pytest.raises(UsageError, match="default_harness"):
        _request(["-p", "hi"], config=Config())


@pytest.mark.parametrize(
    ("argv", "environ", "model"),
    [
        (["-n", "codex", "-p", "hi", "-m", "gpt-5"], {"CALLAI_MODEL": "o4"}, "gpt-5"),  # flag wins
        (["-n", "codex", "-p", "hi"], {"CALLAI_MODEL": "o4"}, "o4"),  # then CALLAI_MODEL
        (["-n", "codex", "-p", "hi"], {}, "o3"),  # then [harnesses.codex] model
        (["-n", "claude-code", "-p", "hi"], {}, "haiku"),  # then top-level model, an alias here
        (["-n", "codex", "-p", "hi", "-m", "fast"], {}, "gpt-5-codex-mini"),  # aliases apply to -m too
    ],
)
def test_model_precedence_and_aliases(argv, environ, model):
    assert _request(argv, environ=environ, config=CONF).model == model


def test_alias_missing_for_harness_is_usage_error():
    with pytest.raises(UsageError, match="model alias 'fast' has no entry for pi"):
        _request(["-n", "pi", "-p", "hi"], config=CONF)


def test_timeout_precedence():
    flags = ["-n", "pi", "-p", "hi", "-m", "x"]  # -m: CONF's default model is an alias with no pi entry
    assert _request([*flags, "--timeout", "5"], environ={"CALLAI_TIMEOUT": "9"}, config=CONF).timeout == 5
    assert _request(["-n", "pi", "-p", "hi", "-m", "x"], environ={"CALLAI_TIMEOUT": "9"}, config=CONF).timeout == 9
    assert _request(["-n", "pi", "-p", "hi", "-m", "x"], config=CONF).timeout == 600
    assert _request(["-n", "pi", "-p", "hi"]).timeout is None


@pytest.mark.parametrize("value", ["soon", "0", "-2", "inf"])
def test_invalid_callai_timeout_is_usage_error(value):
    with pytest.raises(UsageError, match="CALLAI_TIMEOUT"):
        _request(["-n", "pi", "-p", "hi"], environ={"CALLAI_TIMEOUT": value})


def test_config_extra_args_come_before_passthrough_args():
    req = _request(["-n", "codex", "-p", "hi", "--", "--from-cli"], config=CONF)
    assert req.extra_args == ("--from-config", "--from-cli")


def test_harness_binary_from_config_expands_home(monkeypatch):
    monkeypatch.setenv("HOME", "/home/u")
    assert cli.harness_binary(get_adapter("codex"), CONF) == "/home/u/bin/codex"
    assert cli.harness_binary(get_adapter("pi"), CONF) == "pi"


def test_main_uses_config_file(tmp_path, capsys, monkeypatch):
    conf = tmp_path / "c.toml"
    conf.write_text('default_harness = "codex"\n[harnesses.codex]\nbinary = "/opt/codex"\n', encoding="utf-8")
    monkeypatch.setenv("CALLAI_CONFIG", str(conf))
    monkeypatch.delenv("CALLAI_HARNESS_NAME", raising=False)
    monkeypatch.setattr("sys.stdin", FakeStdin(tty=True))
    assert cli.main(["-p", "hi", "--dry-run"]) == 0
    assert capsys.readouterr().out == "/opt/codex exec --json --skip-git-repo-check -- hi\n"


def test_main_bad_config_is_exit_2(tmp_path, capsys, monkeypatch):
    conf = tmp_path / "c.toml"
    conf.write_text("default_tool = 'codex'\n", encoding="utf-8")
    monkeypatch.setenv("CALLAI_CONFIG", str(conf))
    monkeypatch.setattr("sys.stdin", FakeStdin(tty=True))
    assert cli.main(["-n", "codex", "-p", "hi", "--dry-run"]) == 2
    assert "unknown key 'default_tool'" in capsys.readouterr().err


def test_old_callai_tool_env_is_named_in_the_error():
    with pytest.raises(UsageError, match="CALLAI_TOOL was renamed to CALLAI_HARNESS_NAME"):
        _request(["-p", "hi"], environ={"CALLAI_TOOL": "claude-code"})


def test_old_tool_flag_is_gone(capsys):
    # -t/--tool was renamed to -n/--name: many harnesses have their own --tool(s) flags.
    for flag in ("-t", "--tool"):
        with pytest.raises(SystemExit):
            cli.build_parser().parse_args([flag, "claude-code"])
    parser = cli.build_parser()
    options = {opt for action in parser._actions for opt in action.option_strings}
    assert {"-n", "--name"} <= options
    assert not {"-t", "--tool"} & options
    # Help layout differs by Python version ("-n HARNESS_NAME, --name HARNESS_NAME" before 3.13,
    # "-n, --name HARNESS_NAME" from 3.13); both contain this.
    assert "--name HARNESS_NAME" in parser.format_help()


def test_stream_json_offered():
    assert cli.build_parser().parse_args(["-o", "stream-json"]).output_format == "stream-json"


# --- main() in-process --------------------------------------------------------


def test_main_dry_run_text(capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", FakeStdin(tty=True))
    assert cli.main(["-n", "claude-code", "-p", "it's here", "--dry-run"]) == 0
    assert capsys.readouterr().out == "claude -p --output-format json -- 'it'\"'\"'s here'\n"


def test_main_dry_run_json_reads_stdin(capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", FakeStdin("from pipe\n"))
    assert cli.main(["-n", "claude-code", "--dry-run", "-o", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["argv"][-1] == "from pipe"


def test_main_usage_error_message(capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", FakeStdin(tty=True))
    monkeypatch.delenv("CALLAI_HARNESS_NAME", raising=False)
    assert cli.main(["-p", "hi"]) == 2
    err = capsys.readouterr().err
    assert err.startswith("usage: callai")  # argparse-style: usage line, then the error
    assert "\ncallai: error: no harness given" in err


def test_main_bypass_dry_run_does_not_warn(capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", FakeStdin(tty=True))
    assert cli.main(["-n", "claude-code", "-p", "hi", "--permission", "bypass", "--dry-run"]) == 0
    assert capsys.readouterr().err == ""  # nothing runs, so nothing to warn about


def test_main_unimplemented_tool(capsys, monkeypatch):
    from callai import adapters

    monkeypatch.setattr(adapters, "REGISTRY", {})  # every tool known but none implemented
    monkeypatch.setattr("sys.stdin", FakeStdin(tty=True))
    assert cli.main(["-n", "codex", "-p", "hi", "--dry-run"]) == 2
    assert "not implemented yet" in capsys.readouterr().err


# --- rendering (stub adapter, independent of any real harness parser) --------


class StubAdapter(Adapter):
    name = "claude-code"
    binary = "claude"
    install_url = "https://example.invalid"

    def build_argv(self, req):
        return ["claude", "--", req.prompt]

    def parse(self, completed, req):
        return Result(
            harness_name=self.name,
            text=completed.stdout.strip(),
            exit_code=completed.exit_code,
            is_error=completed.stdout.startswith("ERR"),
            argv=completed.argv,
        )


def _render(capsys, fmt, stdout="answer", stderr="harness noise\n", exit_code=0, verbose=False):
    req = Request(harness_name="claude-code", prompt="p", output_format=fmt)
    done = Completed(argv=["claude", "--", "p"], exit_code=exit_code, stdout=stdout, stderr=stderr, duration_ms=1)
    code = cli._render(done, StubAdapter(), req, verbose)
    out, err = capsys.readouterr()
    return code, out, err


def test_render_text_success_hides_harness_stderr(capsys):
    assert _render(capsys, "text") == (0, "answer\n", "")


def test_render_text_error_goes_to_stderr_with_exit_1(capsys):
    code, out, err = _render(capsys, "text", stdout="ERR model missing")
    assert (code, out) == (1, "")
    assert err == "harness noise\nERR model missing\n"


def test_render_text_error_keeps_harness_exit_code(capsys):
    assert _render(capsys, "text", stdout="ERR x", exit_code=5)[0] == 5


def test_render_text_error_without_text(capsys):
    assert _render(capsys, "text", stdout="ERR", stderr="", exit_code=1) == (1, "", "ERR\n")
    assert _render(capsys, "text", stdout="", stderr="", exit_code=1) == (1, "\n", "")


def test_render_json(capsys):
    code, out, err = _render(capsys, "json")
    assert (code, err) == (0, "")
    assert json.loads(out)["text"] == "answer"


def test_render_json_error_shows_harness_stderr_unless_verbose(capsys):
    assert _render(capsys, "json", stdout="ERR x")[2] == "harness noise\n"
    assert _render(capsys, "json", stdout="ERR x", verbose=True)[2] == ""  # already streamed live


def test_render_raw_verbose_does_not_repeat_stderr(capsys):
    assert _render(capsys, "raw", verbose=True) == (0, "answer", "")
    assert _render(capsys, "raw") == (0, "answer", "harness noise\n")


def test_render_text_error_not_repeated_when_already_in_harness_stderr(capsys):
    # pi's "model not found" text comes from stderr itself: print it once, not twice.
    code, out, err = _render(capsys, "text", stdout="ERR model gone", stderr="log line\nERR model gone\n", exit_code=1)
    assert (code, out) == (1, "")
    assert err == "log line\nERR model gone\n"


# --- --list-harnesses (CA-13) ---------------------------------------------------


@pytest.fixture
def listing_env(fake_bin, monkeypatch, tmp_path):
    """Only claude (prints its version) and hermes (prints it but exits 1, like hermes 0.19.0) are on PATH."""
    fake_bin.add("claude", stdout="\n2.1.314 (Claude Code)\n")
    fake_bin.add("hermes", stdout="Hermes Agent v0.19.0 (2026.7.20)\nInstall directory: /x\n", exit_code=1)
    monkeypatch.setenv("PATH", str(fake_bin.dir))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "noconfig"))
    monkeypatch.delenv("CALLAI_CONFIG", raising=False)
    monkeypatch.setattr("sys.stdin", FakeStdin(tty=True))
    return fake_bin


def test_list_harnesses_text(listing_env, capsys):
    assert cli.main(["--list-harnesses"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert [line.split()[0] for line in lines] == list(cli.HARNESS_NAMES)
    claude = lines[0]
    assert "2.1.314 (Claude Code)" in claude and str(listing_env.dir / "claude") in claude
    assert "Hermes Agent v0.19.0 (2026.7.20)" in lines[list(cli.HARNESS_NAMES).index("hermes")]
    codex = lines[1]
    assert "not installed" in codex and "https://" in codex  # points at install docs
    assert listing_env.record("claude")["argv"] == ["claude", "--version"]


def test_list_harnesses_json(listing_env, capsys):
    assert cli.main(["--list-harnesses", "-o", "json"]) == 0
    rows = {r["harness_name"]: r for r in json.loads(capsys.readouterr().out)["harnesses"]}
    assert list(rows) == list(cli.HARNESS_NAMES)
    assert rows["claude-code"] == {
        "harness_name": "claude-code",
        "binary": "claude",
        "path": str(listing_env.dir / "claude"),
        "version": "2.1.314 (Claude Code)",
        "install_url": get_adapter("claude-code").install_url,
    }
    assert (rows["codex"]["path"], rows["codex"]["version"]) == (None, None)


def test_list_harnesses_uses_configured_binary(listing_env, capsys, monkeypatch, tmp_path):
    listing_env.add("my-codex", stdout="codex-cli 0.166.0\n")
    conf = tmp_path / "c.toml"
    conf.write_text('[harnesses.codex]\nbinary = "my-codex"\n', encoding="utf-8")
    monkeypatch.setenv("CALLAI_CONFIG", str(conf))
    assert cli.main(["--list-harnesses", "-o", "json"]) == 0
    codex = json.loads(capsys.readouterr().out)["harnesses"][1]
    assert (codex["binary"], codex["version"]) == ("my-codex", "codex-cli 0.166.0")


def test_harness_version_handles_silence_and_failure(fake_bin, tmp_path):
    from callai import runner

    silent = fake_bin.add("silent")
    assert runner.harness_version(str(silent)) is None
    slow = fake_bin.add("slow", stdout="1.0\n", sleep=5)
    assert runner.harness_version(str(slow), timeout=0.5) is None
    assert runner.harness_version(str(tmp_path / "missing")) is None
    err_only = fake_bin.add("err-only", stderr="\x1b[1mtool 3.2\x1b[0m\n")
    assert runner.harness_version(str(err_only)) == "tool 3.2"
