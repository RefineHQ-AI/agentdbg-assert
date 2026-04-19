# Using AgentDbg in CI

Set up behavioral regression testing for your AI agent in under 5 minutes.

## 1. Create a baseline from a known-good run

Run your agent locally and capture a baseline:

```bash
python my_agent.py
agentdbg baseline $(agentdbg list --json | python -c "import sys,json; print(json.load(sys.stdin)['runs'][0]['run_id'])") \
  --out baselines/my_agent.json
```

Commit `baselines/my_agent.json` to your repo.

## 2. Add a policy file

Create `.agentdbg/policy.yaml` in your repo root:

```yaml
assert:
  no_loops: true
  no_guardrails: true
  step_tolerance: 0.5
  expect_status: ok
```

This tells `agentdbg assert` what to check on every PR. CLI flags
always override policy file values.

## 3. Add the GitHub Actions workflow

Create `.github/workflows/agent-check.yml`:

```yaml
name: Agent Regression Check
on: [pull_request]

jobs:
  agent-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: agentdbg/assert-action@v1
        with:
          agent-script: my_agent.py
          baseline: baselines/my_agent.json
```

Every PR now gets a regression report posted as a comment.

## How it works

1. The action runs your agent script (which must use `@trace` or `traced_run`).
2. It grabs the latest run ID from `agentdbg list`.
3. `agentdbg assert` compares the run against the baseline and policy.
4. A Markdown report is posted to the PR.
5. The step fails (exit 1) if any check regresses.

## CLI quick reference

```bash
# Capture baseline
agentdbg baseline RUN_ID --out baseline.json

# Assert against baseline + policy
agentdbg assert RUN_ID --baseline baseline.json --policy .agentdbg/policy.yaml

# Assert with inline thresholds (no baseline needed)
agentdbg assert RUN_ID --max-steps 20 --max-tool-calls 10 --no-loops

# Compare two runs
agentdbg diff RUN_A RUN_B

# Output formats
agentdbg assert RUN_ID --baseline baseline.json --format json
agentdbg assert RUN_ID --baseline baseline.json --format markdown
```

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | All checks passed |
| 1 | One or more checks failed (regression) |
| 2 | Baseline not found or invalid |
| 10 | Internal error |
