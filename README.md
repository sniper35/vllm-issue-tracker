# vLLM Issue Tracker

Daily-updated local tracker for open, unclaimed upstream issues in
`vllm-project/vllm`. The tracker groups issues by core inference topic and
keeps personal triage fields in a local SQLite database.

## Setup

Install dependencies and authenticate the GitHub CLI:

```bash
pip install -r requirements.txt
gh auth login -h github.com
gh auth status
```

## Manual Sync

Run the sync from this repository:

```bash
python daily_update.py
```

The sync reads `topics.yaml`, updates `issues.sqlite`, and regenerates:

- `ISSUES.md`
- `issues.csv`

The script inserts newly matching issues as `my_status = new`, updates GitHub
metadata for existing rows, and archives tracked issues that are closed or have
an open PR referencing the issue number in the PR body.

## Personal Triage Fields

Edit these fields directly in `issues.sqlite` or in a SQLite UI:

- `difficulty`
- `component`
- `learning_value`
- `fixability`
- `my_status`
- `notes`
- `next_action`

The daily sync preserves these personal fields when GitHub metadata changes.

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

## Learning Workflow

For a selected issue, read the relevant vLLM docs and modules, write notes in
the tracker row, reproduce the issue or record why reproduction is blocked, and
then run duplicate-work checks in the actual vLLM checkout before starting any
fix.

Do not modify the vLLM source tree from this repository.
