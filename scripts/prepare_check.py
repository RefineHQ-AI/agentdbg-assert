"""Build a GitHub Checks API payload from a Maida statistical report."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Sequence


CHECK_NAME = "Maida statistical gate"
SUPPORTED_REPORT_VERSIONS = {"1", "2.0.0"}
VERDICT_CONCLUSIONS = {
    "pass": "success",
    "fail": "failure",
    "inconclusive": "neutral",
}
VERDICT_PASSED = {
    "pass": True,
    "fail": False,
    "inconclusive": None,
}


class ReportError(ValueError):
    """Raised when the Maida sidecar does not satisfy a supported report schema."""


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReportError(f"{field} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ReportError(f"{field} must be finite")
    return result


def _escape_cell(value: str) -> str:
    return value.replace("\\", "\\\\").replace("`", "\\`").replace("|", "\\|")


def _non_negative_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ReportError(f"{field} must be a non-negative integer")
    return value


def _summary_footer(
    lines: list[str], report: dict[str, Any], details_url: str
) -> str:
    lines.extend(["", f"[Open this workflow run]({details_url}) for full gate output."])
    if report["verdict"] == "inconclusive":
        lines.extend(
            [
                "",
                "This conclusion is neutral and does not block by itself. "
                f"[Re-run this workflow]({details_url}) to collect a fresh trial set.",
            ]
        )
    return "\n".join(lines)


def _summary_v1(report: dict[str, Any], details_url: str) -> str:
    metadata = report.get("metadata")
    if not isinstance(metadata, dict):
        raise ReportError("metadata must be an object")
    trials = _non_negative_integer(
        metadata.get("trials_completed"), "metadata.trials_completed"
    )

    results = report.get("aggregate_results")
    if not isinstance(results, list) or not results:
        raise ReportError("aggregate_results must be a non-empty list")

    lines = [
        f"Overall verdict: **{report['verdict'].upper()}** across {trials} trials.",
        "",
        "| Assertion | Verdict | Confidence interval | Pass-rate threshold |",
        "| --- | --- | --- | ---: |",
    ]
    for index, result in enumerate(results):
        field = f"aggregate_results[{index}]"
        if not isinstance(result, dict):
            raise ReportError(f"{field} must be an object")

        name = result.get("check_name")
        if not isinstance(name, str) or not name:
            raise ReportError(f"{field}.check_name must be a non-empty string")
        verdict = result.get("verdict")
        if verdict not in VERDICT_CONCLUSIONS:
            raise ReportError(f"{field}.verdict must be pass, fail, or inconclusive")

        interval = result.get("confidence_interval")
        if not isinstance(interval, list) or len(interval) != 2:
            raise ReportError(f"{field}.confidence_interval must contain two numbers")
        lower = _finite_number(interval[0], f"{field}.confidence_interval[0]")
        upper = _finite_number(interval[1], f"{field}.confidence_interval[1]")
        if not 0 <= lower <= upper <= 1:
            raise ReportError(
                f"{field}.confidence_interval must satisfy 0 <= lower <= upper <= 1"
            )

        threshold = _finite_number(
            result.get("pass_rate_threshold"), f"{field}.pass_rate_threshold"
        )
        if not 0 <= threshold <= 1:
            raise ReportError(f"{field}.pass_rate_threshold must be between 0 and 1")

        lines.append(
            f"| `{_escape_cell(name)}` | **{verdict.upper()}** | "
            f"{lower:.3f}–{upper:.3f} | {threshold:.3f} |"
        )

    return _summary_footer(lines, report, details_url)


def _v2_evidence(result: dict[str, Any], field: str) -> str:
    kind = result.get("kind")
    if kind not in {"invariant", "measured", "statistical", "distributional"}:
        raise ReportError(
            f"{field}.kind must be invariant, measured, statistical, or distributional"
        )

    mode = result.get("mode")
    if mode not in {"gating", "report_only"}:
        raise ReportError(f"{field}.mode must be gating or report_only")
    verdict = result.get("verdict")
    if mode == "gating" and verdict not in VERDICT_CONCLUSIONS:
        raise ReportError(
            f"{field}.verdict must be pass, fail, or inconclusive for a gating metric"
        )
    if mode == "report_only" and verdict is not None:
        raise ReportError(f"{field}.verdict must be null for a report-only metric")

    trials_used = _non_negative_integer(
        result.get("trials_used"), f"{field}.trials_used"
    )
    trials_budgeted = _non_negative_integer(
        result.get("trials_budgeted"), f"{field}.trials_budgeted"
    )
    if trials_used > trials_budgeted:
        raise ReportError(f"{field}.trials_used must not exceed trials_budgeted")

    evidence = result.get("evidence")
    if not isinstance(evidence, dict):
        raise ReportError(f"{field}.evidence must be an object")

    if kind == "invariant":
        violations = _non_negative_integer(
            evidence.get("violations"), f"{field}.evidence.violations"
        )
        if violations > trials_used:
            raise ReportError(
                f"{field}.evidence.violations must not exceed trials_used"
            )
        return f"violated in {violations}/{trials_used} trials"

    if kind == "measured":
        delta = evidence.get("delta")
        delta_text = (
            "n/a"
            if delta is None
            else f"{_finite_number(delta, f'{field}.evidence.delta'):+.3g}"
        )
        sample = evidence.get("sample")
        if not isinstance(sample, dict):
            raise ReportError(f"{field}.evidence.sample must be an object")
        minimum = _finite_number(sample.get("min"), f"{field}.evidence.sample.min")
        median = _finite_number(
            sample.get("median"), f"{field}.evidence.sample.median"
        )
        maximum = _finite_number(sample.get("max"), f"{field}.evidence.sample.max")
        if not minimum <= median <= maximum:
            raise ReportError(
                f"{field}.evidence.sample must satisfy min <= median <= max"
            )
        return (
            f"delta {delta_text}; min/median/max "
            f"{minimum}/{median}/{maximum}"
        )

    bounds = evidence.get("confidence_bounds")
    if isinstance(bounds, dict):
        lower = _finite_number(
            bounds.get("lower"), f"{field}.evidence.confidence_bounds.lower"
        )
        upper = _finite_number(
            bounds.get("upper"), f"{field}.evidence.confidence_bounds.upper"
        )
        if not 0 <= lower <= upper <= 1:
            raise ReportError(
                f"{field}.evidence.confidence_bounds must satisfy "
                "0 <= lower <= upper <= 1"
            )
        if mode == "report_only":
            observed = _finite_number(
                evidence.get("observed_rate"), f"{field}.evidence.observed_rate"
            )
            if not 0 <= observed <= 1:
                raise ReportError(
                    f"{field}.evidence.observed_rate must be between 0 and 1"
                )
            return f"observed rate {observed:.3f}; no confidence verdict"
        return f"one-sided bounds {lower:.3f}–{upper:.3f}"

    if kind == "distributional":
        observed = _finite_number(
            evidence.get("observed"), f"{field}.evidence.observed"
        )
        bound = _finite_number(
            evidence.get("prediction_bound"), f"{field}.evidence.prediction_bound"
        )
        return f"observed {observed:.3g}; prediction bound {bound:.3g}"

    raise ReportError(f"{field}.evidence.confidence_bounds must be an object")


def _summary_v2(report: dict[str, Any], details_url: str) -> str:
    metadata = report.get("metadata")
    if not isinstance(metadata, dict):
        raise ReportError("metadata must be an object")
    trials_used = _non_negative_integer(
        metadata.get("trials_used"), "metadata.trials_used"
    )
    trials_budgeted = _non_negative_integer(
        metadata.get("trials_budgeted"), "metadata.trials_budgeted"
    )
    if trials_used > trials_budgeted:
        raise ReportError("metadata.trials_used must not exceed trials_budgeted")

    results = report.get("aggregate_results")
    if not isinstance(results, list) or not results:
        raise ReportError("aggregate_results must be a non-empty list")

    lines = [
        f"Overall verdict: **{report['verdict'].upper()}** across "
        f"{trials_used}/{trials_budgeted} trials used.",
        "",
        "| Metric | Kind | Mode | Direction | Verdict | Evidence |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for index, result in enumerate(results):
        field = f"aggregate_results[{index}]"
        if not isinstance(result, dict):
            raise ReportError(f"{field} must be an object")
        name = result.get("check_name")
        if not isinstance(name, str) or not name:
            raise ReportError(f"{field}.check_name must be a non-empty string")

        detail = _v2_evidence(result, field)
        verdict = result.get("verdict")
        verdict_text = verdict.upper() if verdict is not None else "REPORT ONLY"
        direction = result.get("direction")
        if direction not in {None, "lower", "upper", "both"}:
            raise ReportError(f"{field}.direction must be lower, upper, both, or null")
        lines.append(
            f"| `{_escape_cell(name)}` | {result['kind']} | {result['mode']} | "
            f"{direction or 'n/a'} | **{verdict_text}** | {detail} |"
        )

    return _summary_footer(lines, report, details_url)


def _summary(report: dict[str, Any], details_url: str) -> str:
    if report["report_version"] == "1":
        return _summary_v1(report, details_url)
    return _summary_v2(report, details_url)


def build_check_payload(
    report: dict[str, Any], *, head_sha: str, details_url: str
) -> dict[str, Any]:
    """Validate *report* and return a completed Checks API request body."""
    if report.get("report_version") not in SUPPORTED_REPORT_VERSIONS:
        raise ReportError("report_version must be '1' or '2.0.0'")

    verdict = report.get("verdict")
    if verdict not in VERDICT_CONCLUSIONS:
        raise ReportError("verdict must be pass, fail, or inconclusive")
    if report.get("passed") is not VERDICT_PASSED[verdict]:
        raise ReportError(f"passed is inconsistent with verdict {verdict}")
    if not isinstance(head_sha, str) or not head_sha:
        raise ReportError("head_sha must be a non-empty string")
    if not isinstance(details_url, str) or not details_url:
        raise ReportError("details_url must be a non-empty string")

    return {
        "name": CHECK_NAME,
        "head_sha": head_sha,
        "status": "completed",
        "conclusion": VERDICT_CONCLUSIONS[verdict],
        "details_url": details_url,
        "output": {
            "title": f"{CHECK_NAME}: {verdict.upper()}",
            "summary": _summary(report, details_url),
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--details-url", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReportError(f"could not read Maida report: {error}") from error
    if not isinstance(report, dict):
        raise ReportError("Maida report root must be an object")

    payload = build_check_payload(
        report, head_sha=args.head_sha, details_url=args.details_url
    )
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"verdict={report['verdict']}")
    print(f"conclusion={payload['conclusion']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
