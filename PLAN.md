# vLLM Issue Tracker Plan

## Goal

Build a small daily-updated tracker for upstream `vllm-project/vllm` issues that helps learn vLLM core inference concepts by finding real, open, unclaimed issues.

The tracker should:

- group issues by vLLM core topic
- include only open issues that are not linked to a PR
- add newly matching issues each day
- archive issues that close or become linked to a PR
- preserve personal triage notes and learning status
- generate a readable Markdown dashboard and a CSV export

Primary source of truth: local SQLite database.

Generated outputs:

- `VLLM_ISSUES.md`
- `vllm_issues.csv`

Optional later output:

- Google Sheet sync from `vllm_issues.csv`

## Repository Scope

This repository is only for issue tracking and learning workflow automation.

Do not modify the vLLM source tree from this repo. When selecting a fix, switch to the actual vLLM checkout and follow its `AGENTS.md`, including duplicate-work checks before any PR.

## Proposed Files

Create these files:

```text
topics.yaml
daily_update.py
requirements.txt
VLLM_ISSUES.md
vllm_issues.csv
.github/workflows/daily.yml
README.md
```

The generated files are `VLLM_ISSUES.md` and `vllm_issues.csv`. The rest are authored files.

## Data Model

Use SQLite table `issues`:

```text
topic TEXT
issue_number INTEGER PRIMARY KEY
title TEXT
url TEXT
state TEXT
labels TEXT
created_at TEXT
updated_at TEXT
last_seen_at TEXT
archived_at TEXT
archive_reason TEXT
linked_pr_status TEXT
difficulty TEXT
component TEXT
learning_value TEXT
fixability TEXT
my_status TEXT
notes TEXT
next_action TEXT
```

Suggested `my_status` values:

```text
new
triage
learning
needs_repro
fixable
not_fixable
selected
pr_opened
archived_linked_pr
archived_closed
```

## Core Topics

Start with these topics in `topics.yaml`.

```yaml
topics:
  kv_cache:
    description: KV cache allocation, block management, eviction, offload, prefix reuse, KV dtype/layout.
    queries:
      - 'kv cache -linked:pr'
      - 'kv-cache -linked:pr'
      - 'prefix cache -linked:pr'
      - 'prefix caching -linked:pr'
      - 'kv offload -linked:pr'

  scheduler_batching:
    description: V1 scheduler, continuous batching, preemption, chunked prefill, partial prefill, fairness.
    queries:
      - 'scheduler -linked:pr'
      - 'continuous batching -linked:pr'
      - 'chunked prefill -linked:pr'
      - 'partial prefill -linked:pr'
      - 'preemption -linked:pr'

  attention_kernels:
    description: PagedAttention, FlashAttention, FlashInfer, MLA, CUDA graphs, CPU attention kernels.
    queries:
      - 'attention -linked:pr'
      - 'pagedattention -linked:pr'
      - 'flashinfer -linked:pr'
      - 'MLA attention -linked:pr'
      - 'cuda graph attention -linked:pr'

  speculative_decoding:
    description: Speculative decoding, draft models, EAGLE, MTP, ngram, tree attention.
    queries:
      - 'speculative decoding -linked:pr'
      - 'speculative -linked:pr'
      - 'EAGLE -linked:pr'
      - 'MTP -linked:pr'
      - 'ngram proposer -linked:pr'

  quantization:
    description: FP8, AWQ, GPTQ, Marlin, TurboQuant, KV cache quantization.
    queries:
      - 'quantization -linked:pr'
      - 'fp8 -linked:pr'
      - 'AWQ -linked:pr'
      - 'GPTQ -linked:pr'
      - 'TurboQuant -linked:pr'

  moe:
    description: Mixture of Experts, routing, expert parallelism, DeepEP, EPLB, MoE kernels.
    queries:
      - 'moe -linked:pr'
      - 'expert parallel -linked:pr'
      - 'DeepEP -linked:pr'
      - 'EPLB -linked:pr'
      - 'routing experts -linked:pr'

  lora_adapters:
    description: LoRA loading, dynamic adapters, multimodal LoRA, adapter serving.
    queries:
      - 'lora -linked:pr'
      - 'adapter -linked:pr'
      - 'dynamic lora -linked:pr'
      - 'multi-lora -linked:pr'

  structured_output_tooling:
    description: Structured outputs, guided decoding, xgrammar, tool calling, reasoning parsers.
    queries:
      - 'structured output -linked:pr'
      - 'guided decoding -linked:pr'
      - 'xgrammar -linked:pr'
      - 'tool calling -linked:pr'
      - 'reasoning parser -linked:pr'

  openai_server:
    description: OpenAI-compatible API server, streaming, chat completions, tools, metrics.
    queries:
      - 'openai server -linked:pr'
      - 'chat completions streaming -linked:pr'
      - 'streaming tool -linked:pr'
      - 'metrics -linked:pr'

  distributed_pd:
    description: Distributed execution, tensor/data/pipeline parallelism, disaggregated prefill, KV transfer.
    queries:
      - 'distributed -linked:pr'
      - 'tensor parallel -linked:pr'
      - 'data parallel -linked:pr'
      - 'disaggregated prefill -linked:pr'
      - 'kv transfer -linked:pr'
```

Limit each query to 10 issues. Deduplicate by issue number.

## Daily Update Algorithm

For each topic and query:

1. Run:

   ```bash
   gh search issues '<query>' --repo vllm-project/vllm --state open --limit 10 --json number,title,url,updatedAt,createdAt,labels
   ```

2. Insert any new issue into SQLite with:

   ```text
   my_status = new
   linked_pr_status = unlinked
   last_seen_at = now
   ```

3. Update title, labels, updated time, and last seen time for existing issues.

4. Re-check all active tracked issues:

   ```bash
   gh issue view <issue_number> --repo vllm-project/vllm --json state,title,url,updatedAt,labels
   gh pr list --repo vllm-project/vllm --state open --search '<issue_number> in:body' --json number,title,url
   ```

5. Archive issue if:

   ```text
   GitHub issue state is closed -> archive_reason = closed
   open PR search returns any PR -> archive_reason = linked_pr
   ```

6. Regenerate:

   ```text
   VLLM_ISSUES.md
   vllm_issues.csv
   ```

## Dashboard Format

`VLLM_ISSUES.md` should be grouped by topic.

Each row should include:

```text
issue number
title
labels
updated_at
my_status
learning_value
fixability
next_action
url
```

Add an "Action Queue" section at the top with issues where:

```text
my_status in (new, triage, learning, needs_repro, fixable)
archive_reason is empty
```

Sort by:

1. `selected`
2. `fixable`
3. high learning value
4. recently updated

## Learning Workflow

For each selected issue:

1. Read the relevant vLLM docs and modules.
2. Write notes in the issue row.
3. Reproduce or identify why reproduction is blocked.
4. Run duplicate-work checks in the vLLM checkout:

   ```bash
   gh issue view <issue_number> --repo vllm-project/vllm --comments
   gh pr list --repo vllm-project/vllm --state open --search "<issue_number> in:body"
   gh pr list --repo vllm-project/vllm --state open --search "<short area keywords>"
   ```

5. Only then start implementation in the vLLM repo.

## Scheduling

Preferred: GitHub Actions in this tracker repo.

Create `.github/workflows/daily.yml`:

```yaml
name: Daily vLLM Issue Sync

on:
  schedule:
    - cron: "0 15 * * *"
  workflow_dispatch:

permissions:
  contents: write

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: cli/gh-actions-cache@v1
        continue-on-error: true
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: python daily_update.py
        env:
          GH_TOKEN: ${{ github.token }}
      - name: Commit generated updates
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add VLLM_ISSUES.md vllm_issues.csv vllm_issues.sqlite
          git diff --cached --quiet || git commit -m "Update vLLM issue tracker"
          git push
```

If keeping the repo local only, use macOS `launchd` instead and run:

```bash
cd /path/to/vllm-issue-tracker
python daily_update.py
```

## Acceptance Criteria

The next agent should stop when:

- `daily_update.py` can run locally with `gh` authenticated
- `topics.yaml` exists with the topic definitions above
- SQLite is created or updated
- `VLLM_ISSUES.md` and `vllm_issues.csv` are generated
- linked-PR and closed issues are archived, not shown in active issue lists
- README explains how to run the sync manually
- GitHub Actions workflow is present if this repo is pushed to GitHub

## First Manual Run

After implementation:

```bash
gh auth status
python daily_update.py
git status --short
```

Review `VLLM_ISSUES.md`, then choose one issue with high learning value and realistic fixability.

