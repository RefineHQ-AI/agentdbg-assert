"""Run a trusted workflow command without including it in Action output."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping, Sequence


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> int:
    del argv
    env = dict(os.environ if environ is None else environ)
    command = env.get("MAIDA_TRACE_COMMAND", "").strip()
    if not command:
        print("MAIDA_TRACE_COMMAND is required.", file=sys.stderr)
        return 2

    completed = subprocess.run(
        ["bash", "-o", "pipefail", "-c", command],
        check=False,
        env=env,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
