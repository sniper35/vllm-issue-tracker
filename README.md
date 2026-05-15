# vLLM Issue Tracker

This repository is a small automation project for tracking upstream
`vllm-project/vllm` issues that are useful for learning vLLM internals and
finding practical contribution opportunities.

It is not a vLLM fork and it does not modify vLLM source code. It reads GitHub
issues, stores a local triage database, and regenerates a Markdown dashboard
and CSV export.

## What It Does

The tracker searches open `vllm-project/vllm` issues by topic, skips issues that
already have a linked pull request, and keeps your personal triage fields across
daily updates.

It is designed to answer:

- Which open vLLM issues match the areas I want to learn?
- Which issues look fixable or worth reproducing?
- Which model-family issue clusters should I watch?
- Which tracked issues became closed or already have active PR work?

The current topic buckets live in `topics.yaml`. The first buckets are model
families you chose to focus on:

- Gemma 4 / Gemma4
- DeepSeek V4
- gpt-oss

There is also a hardware-access bucket for NVIDIA B200/B300 and GB200/GB300
issues. This is intentionally narrow: the goal is to find open issues where
short-lived access to scarce accelerators can produce useful reproductions,
benchmarks, or fixes before an issue already has active PR work.

The rest cover vLLM components such as KV cache, scheduler, attention kernels,
speculative decoding, MoE, OpenAI-compatible serving, multimodal processing,
structured outputs/tooling, distributed prefill/decode, and tokenization.

## Repository Layout

```text
daily_update.py              Sync script and report generator
topics.yaml                  Search topics and GitHub issue queries
vllm_issues.sqlite                Local source-of-truth SQLite tracker database
VLLM_ISSUES.md                    Generated Markdown dashboard
vllm_issues.csv                   Generated CSV export
topics_vllm_omni.yaml        Search topics for vllm-project/vllm-omni
vllm_omni_issues.sqlite      Local vLLM-Omni tracker database
VLLM_OMNI_ISSUES.md          Generated vLLM-Omni Markdown dashboard
vllm_omni_issues.csv         Generated vLLM-Omni CSV export
requirements.txt             Python dependencies
.github/workflows/daily.yml  Scheduled GitHub Actions deployment
tests/                       Unit tests
PLAN.md                      Original implementation plan
```

Generated files:

- `VLLM_ISSUES.md`
- `vllm_issues.csv`
- `VLLM_OMNI_ISSUES.md`
- `vllm_omni_issues.csv`

The SQLite databases, `vllm_issues.sqlite` and `vllm_omni_issues.sqlite`, are the
source of truth for tracked issues and your personal triage fields.

## How The Sync Works

`daily_update.py` performs one sync run:

1. Reads topic definitions from `topics.yaml`.
2. Archives active issues whose topic bucket was removed from `topics.yaml`.
3. Archives active issues that already have assignees, AMD/ROCm labels, or
   obvious AMD GPU title markers such as MI250, MI300, MI325, MI355, or gfx.
4. Searches unassigned open issues in `vllm-project/vllm` with
   `gh search issues --no-assignee`.
5. Skips search results with assignees or the same AMD/ROCm labels/title
   markers.
6. Inserts new matching issues into `vllm_issues.sqlite`.
7. Parses configured RFC-style issues into subissues.
8. Refreshes existing active issues and archives ones that are closed,
   assigned, AMD/ROCm-labeled, or already have an open PR referencing the issue
   number.
9. Regenerates `VLLM_ISSUES.md` and `vllm_issues.csv`.

`VLLM_ISSUES.md` and `vllm_issues.csv` hide active issues labeled `stale` and archived
issues, including issues archived because an open PR is linked. `VLLM_ISSUES.md`
also groups action-queue rows by topic and orders topic sections by the number
of visible, non-stale issues in each topic.

New issues start with:

```text
my_status = new
linked_pr_status = unlinked
```

The sync preserves personal fields when GitHub metadata changes.
When a topic is removed, matching active rows are kept in the database as
history with `archive_reason = removed_topic`.
When an issue already has an assignee, it is excluded from active tracking with
`archive_reason = assigned`.
When an issue has an AMD/ROCm label or an obvious AMD GPU title marker, it is
excluded from active tracking with `archive_reason = excluded_amd_rocm`.
For the vLLM-Omni tracker, unsupported hardware-specific issues for
NPU/XPU/ROCm/Ascend are excluded with
`archive_reason = excluded_unsupported_hardware`.

## vLLM-Omni Tracker

The vLLM-Omni tracker uses the same sync script with a different repository,
topics file, database, and outputs:

```bash
python daily_update.py \
  --repo vllm-project/vllm-omni \
  --topics topics_vllm_omni.yaml \
  --db vllm_omni_issues.sqlite \
  --markdown VLLM_OMNI_ISSUES.md \
  --csv vllm_omni_issues.csv \
  --search-delay-seconds 3
```

`topics_vllm_omni.yaml` tracks the selected vLLM-Omni buckets except
`hardware_accelerators`, and the sync also filters NPU/XPU/ROCm/Ascend issues
because they require hardware that is not available for local follow-up. The
initial vLLM-Omni files were seeded from a cached issue snapshot without making
linked-PR checks; the next normal sync will refresh active issues and archive
rows with linked open PRs.

## GitHub API Rate Limits

This project uses the GitHub CLI, but `gh search issues` and
`gh pr list --search` still consume GitHub's search API bucket. That bucket is
separate from the normal REST API bucket and is much smaller.

The current `topics.yaml` has many queries, so the sync intentionally waits
between search-category requests. By default, `daily_update.py` waits `2.2`
seconds between those requests, which keeps the daily sync below the search API
pace limit in normal use.

Because there are many topic queries, a normal full sync can take several
minutes. The script prints progress such as `Searching 12/106 [...]` while it is
working. At the end it prints a UTC finish timestamp and elapsed runtime. If
you do not see progress output, rerun without `--quiet`.

You can make the sync more conservative:

```bash
GH_SEARCH_DELAY_SECONDS=3 python daily_update.py
```

or:

```bash
python daily_update.py --search-delay-seconds 3
```

If you already hit a `HTTP 403: API rate limit exceeded` error, wait for the
GitHub search bucket to reset before rerunning. Increasing the delay prevents
the next run from immediately exhausting the bucket again, but it cannot recover
requests that have already been spent.

## Local Setup

Requirements:

- Python 3.12 or compatible Python 3 version
- GitHub CLI, `gh`
- A GitHub account that can access `vllm-project/vllm`

Install dependencies:

```bash
pip install -r requirements.txt
```

Authenticate the GitHub CLI:

```bash
gh auth login -h github.com
gh auth status
```

Run a manual sync:

```bash
python daily_update.py
```

After the run, inspect:

- `VLLM_ISSUES.md` for the human-readable dashboard
- `vllm_issues.csv` for spreadsheet import
- `vllm_issues.sqlite` for full triage state

## Deploy With GitHub Actions

There is no server to deploy. Deployment means running the sync on a schedule in
GitHub Actions and committing the generated tracker outputs back to the repo.

The workflow is already defined in:

```text
.github/workflows/daily.yml
```

It runs daily at `15:00 UTC` and can also be started manually with
`workflow_dispatch`.

To deploy it:

1. Push this repository to GitHub.
2. Enable GitHub Actions for the repository.
3. Make sure the workflow has write permission to commit generated files.
   In GitHub, check `Settings -> Actions -> General -> Workflow permissions`
   and allow read and write permissions.
4. Confirm `.github/workflows/daily.yml` is on the default branch.
5. Trigger `Daily vLLM Issue Sync` manually from the Actions tab, or wait for
   the next scheduled run.

The workflow uses the built-in `GITHUB_TOKEN`:

```yaml
permissions:
  contents: write
```

No extra GitHub secret is required unless you later change the workflow to use a
different token.

## Personal Triage Workflow

Edit these fields in `vllm_issues.sqlite` with a SQLite UI or the `sqlite3` CLI:

- `difficulty`
- `component`
- `learning_value`
- `fixability`
- `my_status`
- `notes`
- `next_action`

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

Suggested workflow:

1. Open `VLLM_ISSUES.md` and review the Action Queue.
2. Pick an issue with high learning value and realistic fixability.
3. Update `my_status`, `component`, `notes`, and `next_action` in
   `vllm_issues.sqlite`.
4. Reproduce or analyze the issue in a separate vLLM checkout.
5. Before starting any fix, check the upstream vLLM repository for duplicate
   PRs or recent changes.
6. Do the actual vLLM code work in the vLLM checkout, not in this repository.

## RFC And Subissue Tracking

Some RFCs and roadmap issues are too broad to treat as solved just because one
pull request links to them. For those tracked sources, the sync keeps the parent
issue active with:

```text
linked_pr_status = linked_partial
```

It then parses known task lists or action bullet sections into synthetic child
rows such as `#28262.1`. These rows point back to the parent GitHub issue but can
have their own `my_status`, `next_action`, and triage fields.

Current fine-grained sources include:

- `#27653`: gpt-oss Harmony past-reasoning RFC parent
- `#28262`: gpt-oss Responses API Harmony metadata action list
- `#32713`: unified parser RFC TODO list

Synthetic child rows use negative internal IDs in `vllm_issues.sqlite`, but
`VLLM_ISSUES.md` renders them as parent-style labels like `#32713.3`.

## Editing Topics

Add or change topic buckets in `topics.yaml`.

Each topic has:

```yaml
topic_name:
  description: Short description of the tracked area.
  queries:
    - 'search query -linked:pr'
```

The script limits each query to 10 issues and deduplicates by GitHub issue
number.

## Tests

Run the unit tests:

```bash
python -m pytest -q
```

Run a syntax check:

```bash
python -m compileall daily_update.py tests
```

Check for whitespace problems before committing generated files:

```bash
git diff --check
```

## Troubleshooting

If sync fails locally with a GitHub CLI error, check authentication:

```bash
gh auth status
```

If sync fails with `HTTP 403: API rate limit exceeded`, wait for the search
bucket to reset and rerun with a larger search delay:

```bash
GH_SEARCH_DELAY_SECONDS=3 python daily_update.py
```

If GitHub Actions runs but cannot push generated files, check repository
workflow permissions and confirm `contents: write` is present in
`.github/workflows/daily.yml`.

If a topic is too noisy, narrow its queries in `topics.yaml`. If it misses
important issues, add alternate names, model aliases, or component-specific
terms.
