"""Structural tests for action.yml — catches accidental renames / breakages."""

from pathlib import Path

import yaml

ACTION_PATH = Path(__file__).resolve().parents[1] / "action.yml"


def _load_action():
    return yaml.safe_load(ACTION_PATH.read_text())


def test_composite_action_type():
    action = _load_action()
    assert action["runs"]["using"] == "composite"


def test_required_inputs_present():
    inputs = _load_action()["inputs"]
    assert "agent-script" in inputs
    assert inputs["agent-script"]["required"] is True


def test_optional_inputs_have_defaults():
    inputs = _load_action()["inputs"]
    for name in ("baseline", "policy", "agentdbg-version", "python-version",
                 "extra-args", "post-comment"):
        assert name in inputs, f"missing input: {name}"
        assert "default" in inputs[name], f"{name} has no default"


def test_steps_non_empty():
    steps = _load_action()["runs"]["steps"]
    assert isinstance(steps, list) and len(steps) > 0


def test_no_broken_baseline_generation_step():
    """The old 'Create baseline if not provided' step expanded --out to an
    empty string when baseline was omitted. It should no longer exist."""
    steps = _load_action()["runs"]["steps"]
    for step in steps:
        assert step.get("name") != "Create baseline if not provided"
