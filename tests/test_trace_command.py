import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_trace_command.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("maida_trace_command", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_trace_command_runs_as_trusted_shell_workflow_code(tmp_path):
    module = _load_module()
    marker = tmp_path / "marker.txt"

    result = module.main(
        environ={"MAIDA_TRACE_COMMAND": f"printf imported > {marker}"}
    )

    assert result == 0
    assert marker.read_text() == "imported"


def test_trace_command_preserves_command_exit_status():
    module = _load_module()

    assert module.main(environ={"MAIDA_TRACE_COMMAND": "exit 7"}) == 7


def test_trace_command_never_prints_missing_or_secret_command(capsys):
    module = _load_module()

    assert module.main(environ={}) == 2
    captured = capsys.readouterr()
    assert "MAIDA_TRACE_COMMAND is required" in captured.err
    assert captured.out == ""
