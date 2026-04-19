# AgentDbg Assert Action

A GitHub Action that runs [`agentdbg assert`](https://github.com/RefineHQ-AI/agentdbg)
against your AI agent on every PR. It executes your traced agent script,
compares the resulting run to a baseline and policy, and posts a Markdown
regression report as a sticky PR comment. The job fails (exit 1) if any
check regresses.

## Usage

Add a workflow to your repository (for example
`.github/workflows/agent-check.yml`):

```yaml
name: Agent Regression Check
on: [pull_request]

jobs:
  agent-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: RefineHQ-AI/agentdbg-assert@v1
        with:
          agent-script: my_agent.py
          baseline: baselines/my_agent.json
```

Your `agent-script` must instrument the agent with `@trace` or
`traced_run()` so that AgentDbg can capture the run.

### Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `agent-script` | yes | — | Path to the Python script that runs the agent. The script must use `@trace` or `traced_run()` so a run is recorded. |
| `baseline` | no | `''` | Path to a baseline JSON file produced by `agentdbg baseline`. If omitted, only the policy is enforced. |
| `policy` | no | `.agentdbg/policy.yaml` | Path to a policy YAML file. The policy is only applied if the file exists. |
| `agentdbg-version` | no | `@main` | Version of `agentdbg` to install. Use `v<version>` to install from PyPI (e.g. `v0.2.1`) or `@<ref>` to install from the [`agentdbg`](https://github.com/RefineHQ-AI/agentdbg) repo (branch, tag, or commit, e.g. `@main`). |
| `python-version` | no | `3.12` | Python version passed to `actions/setup-python`. |
| `extra-args` | no | `''` | Additional CLI arguments forwarded to `agentdbg assert` (e.g. `--max-steps 20 --no-loops`). CLI flags override policy values. |
| `post-comment` | no | `true` | When `true` and the workflow runs on a `pull_request` event, the Markdown report is posted as a sticky PR comment. |

**Note:** If the `post-comment` input is `true` and the workflow runs on a `pull_request` event, the action requires the `pull-requests: write` permission.
More details can be found in the [GitHub Actions documentation](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions#permissions) and [sticky-pull-request-comment documentation](https://github.com/marocchino/sticky-pull-request-comment#error-resource-not-accessible-by-integration).

## Example workflows

### Minimal: policy-only check

Use this when you don't have a baseline yet but want to enforce hard
limits (no loops, no guardrail violations, max steps, etc.) defined in
`.agentdbg/policy.yaml`:

```yaml
name: Agent Policy Check
on: [pull_request]

jobs:
  agent-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: RefineHQ-AI/agentdbg-assert@v1
        with:
          agent-script: my_agent.py
```

### Baseline regression check with inline overrides

Pin `agentdbg` to a PyPI release, override a couple of thresholds via
`extra-args`, and assert against a committed baseline:

```yaml
name: Agent Regression Check
on: [pull_request]

jobs:
  agent-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: RefineHQ-AI/agentdbg-assert@v1
        with:
          agent-script: examples/my_agent.py
          baseline: baselines/my_agent.json
          policy: .agentdbg/policy.yaml
          agentdbg-version: v0.2.1
          python-version: '3.11'
          extra-args: --max-steps 20 --max-tool-calls 10
```

### Run on `main` without posting a PR comment

Useful for nightly or post-merge runs where there is no PR to comment
on:

```yaml
name: Nightly Agent Check
on:
  schedule:
    - cron: '0 6 * * *'
  workflow_dispatch:

jobs:
  agent-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: RefineHQ-AI/agentdbg-assert@v1
        with:
          agent-script: my_agent.py
          baseline: baselines/my_agent.json
          post-comment: 'false'
```

## Policy example

The policy file controls what `agentdbg assert` checks on every run.
The full list of supported keys is documented in the
[policy reference](https://github.com/RefineHQ-AI/agentdbg/blob/main/docs/reference/policy.md).

A minimal `.agentdbg/policy.yaml` looks like this:

```yaml
assert:
  no_loops: true
  no_guardrails: true
  step_tolerance: 0.5
  expect_status: ok
```

CLI flags passed via `extra-args` always override values from the
policy file.

## Running `agentdbg assert` locally

For a quick local check before pushing, install `agentdbg` and run the
same command the action runs:

```bash
pip install agentdbg

python my_agent.py
RUN_ID=$(agentdbg list --json | python -c "import sys,json; print(json.load(sys.stdin)['runs'][0]['run_id'])")

agentdbg assert "$RUN_ID" \
  --baseline baselines/my_agent.json \
  --policy .agentdbg/policy.yaml
```

To capture a new baseline from a known-good run:

```bash
agentdbg baseline "$RUN_ID" --out baselines/my_agent.json
```

For installation, tracing your agent, and the rest of the workflow,
see the AgentDbg
[getting started guide](https://github.com/RefineHQ-AI/agentdbg/blob/main/docs/getting-started.md).
