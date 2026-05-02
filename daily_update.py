#!/usr/bin/env python3
"""Sync open vLLM issues into a local SQLite tracker."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


REPO = "vllm-project/vllm"
TOPICS_PATH = Path("topics.yaml")
DB_PATH = Path("issues.sqlite")
MARKDOWN_PATH = Path("ISSUES.md")
CSV_PATH = Path("issues.csv")
DEFAULT_SEARCH_DELAY_SECONDS = float(os.getenv("GH_SEARCH_DELAY_SECONDS", "2.2"))

ISSUE_COLUMNS = [
    "topic",
    "issue_number",
    "title",
    "url",
    "state",
    "labels",
    "created_at",
    "updated_at",
    "last_seen_at",
    "archived_at",
    "archive_reason",
    "linked_pr_status",
    "difficulty",
    "component",
    "learning_value",
    "fixability",
    "my_status",
    "notes",
    "next_action",
]

PERSONAL_COLUMNS = {
    "difficulty",
    "component",
    "learning_value",
    "fixability",
    "my_status",
    "notes",
    "next_action",
}

ACTION_QUEUE_STATUSES = {
    "selected",
    "fixable",
    "new",
    "triage",
    "learning",
    "needs_repro",
}

RFC_SUBISSUE_SOURCES = {
    27653: {
        "topic": "model_family_gpt_oss",
        "component": "gpt-oss/harmony chat completions",
        "learning_value": "high",
        "fixability": "medium",
        "labels": "rfc-subissue, gpt-oss, harmony",
        "markers": [],
        "parent_next_action": (
            "Track concrete Harmony follow-ups instead of treating one linked "
            "PR as complete RFC coverage"
        ),
    },
    28262: {
        "topic": "model_family_gpt_oss",
        "component": "gpt-oss/responses api harmony",
        "learning_value": "high",
        "fixability": "medium",
        "labels": "rfc-subissue, gpt-oss, harmony",
        "markers": ["The changes we can make are:"],
        "parent_next_action": (
            "Track parsed subissues instead of treating linked PRs as complete "
            "coverage"
        ),
    },
    32713: {
        "topic": "structured_output_tooling",
        "component": "parser/harmony unification",
        "learning_value": "high",
        "fixability": "medium",
        "labels": "rfc-subissue, parser, harmony",
        "markers": ["### TODOs"],
        "parent_next_action": (
            "Review parser RFC TODO slices and pick a bounded entrypoint"
        ),
    },
}


class GhCommandError(RuntimeError):
    """Raised when the GitHub CLI exits unsuccessfully."""


class GhRateLimitError(GhCommandError):
    """Raised when GitHub rejects a request because a rate limit was exceeded."""


class SearchRateLimiter:
    """Keep GitHub search-category requests below the 30/minute bucket."""

    def __init__(
        self,
        min_interval_seconds: float,
        *,
        clock: Any = time.monotonic,
        sleep: Any = time.sleep,
    ) -> None:
        self.min_interval_seconds = max(0.0, min_interval_seconds)
        self._clock = clock
        self._sleep = sleep
        self._last_call_started_at: float | None = None

    def wait(self) -> None:
        if self.min_interval_seconds <= 0:
            return

        now = self._clock()
        if self._last_call_started_at is not None:
            elapsed = now - self._last_call_started_at
            remaining = self.min_interval_seconds - elapsed
            if remaining > 0:
                self._sleep(remaining)
                now = self._clock()
        self._last_call_started_at = now


def format_command(command: Any) -> str:
    if isinstance(command, list):
        return " ".join(str(part) for part in command)
    return str(command)


def is_rate_limit_error(details: str) -> bool:
    return "rate limit" in details.lower()


def stderr_progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def emit_progress(progress: Any | None, message: str) -> None:
    if progress is not None:
        progress(message)


def count_topic_queries(topics: dict[str, dict[str, Any]]) -> int:
    return sum(len(topic["queries"]) for topic in topics.values())


def format_seconds(seconds: float) -> str:
    whole_seconds = int(round(seconds))
    minutes, seconds = divmod(whole_seconds, 60)
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def format_reset_time(reset_epoch: Any) -> str:
    if reset_epoch is None:
        return "unknown"
    try:
        reset_int = int(reset_epoch)
    except (TypeError, ValueError):
        return str(reset_epoch)
    reset_iso = datetime.fromtimestamp(reset_int, timezone.utc).isoformat()
    return f"{reset_int} ({reset_iso})"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect_db(path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS issues (
            topic TEXT,
            issue_number INTEGER PRIMARY KEY,
            title TEXT,
            url TEXT,
            state TEXT,
            labels TEXT,
            created_at TEXT,
            updated_at TEXT,
            last_seen_at TEXT,
            archived_at TEXT,
            archive_reason TEXT,
            linked_pr_status TEXT,
            difficulty TEXT,
            component TEXT,
            learning_value TEXT,
            fixability TEXT,
            my_status TEXT,
            notes TEXT,
            next_action TEXT
        )
        """
    )
    conn.commit()


def load_topics(path: Path = TOPICS_PATH) -> dict[str, dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    topics = payload.get("topics")
    if not isinstance(topics, dict):
        raise ValueError(f"{path} must contain a top-level 'topics' mapping")
    for topic_name, topic in topics.items():
        if not isinstance(topic, dict):
            raise ValueError(f"Topic {topic_name!r} must be a mapping")
        if not isinstance(topic.get("queries"), list):
            raise ValueError(f"Topic {topic_name!r} must define a queries list")
    return topics


def labels_to_text(labels: Any) -> str:
    if not labels:
        return ""
    if isinstance(labels, str):
        return labels
    names = []
    for label in labels:
        if isinstance(label, dict):
            name = label.get("name")
        else:
            name = str(label)
        if name:
            names.append(str(name))
    return ", ".join(names)


def issue_has_label(issue: dict[str, Any], label_name: str) -> bool:
    target = label_name.lower()
    for label in issue.get("labels") or []:
        if isinstance(label, dict):
            name = label.get("name", "")
        else:
            name = str(label)
        if name.lower() == target:
            return True
    return False


def is_rfc_like_issue(issue: dict[str, Any]) -> bool:
    title = issue.get("title", "")
    return issue_has_label(issue, "RFC") or title.lower().startswith("[rfc")


def synthetic_subissue_number(parent_issue_number: int, index: int) -> int:
    return -(int(parent_issue_number) * 100 + int(index))


def split_synthetic_subissue_number(issue_number: int) -> tuple[int, int] | None:
    if issue_number >= 0:
        return None
    value = abs(int(issue_number))
    parent_issue_number, index = divmod(value, 100)
    if not parent_issue_number or not index:
        return None
    return parent_issue_number, index


def display_issue_number(issue_number: int) -> str:
    subissue = split_synthetic_subissue_number(int(issue_number))
    if subissue is None:
        return str(issue_number)
    parent_issue_number, index = subissue
    return f"{parent_issue_number}.{index}"


def issue_payload_to_row(topic: str, issue: dict[str, Any], now: str) -> dict[str, Any]:
    return {
        "topic": topic,
        "issue_number": int(issue["number"]),
        "title": issue.get("title", ""),
        "url": issue.get("url", ""),
        "state": (issue.get("state") or "open").lower(),
        "labels": labels_to_text(issue.get("labels")),
        "created_at": issue.get("createdAt") or issue.get("created_at") or "",
        "updated_at": issue.get("updatedAt") or issue.get("updated_at") or "",
        "last_seen_at": now,
        "archived_at": "",
        "archive_reason": "",
        "linked_pr_status": "unlinked",
        "difficulty": "",
        "component": "",
        "learning_value": "",
        "fixability": "",
        "my_status": "new",
        "notes": "",
        "next_action": "",
    }


def upsert_issue(
    conn: sqlite3.Connection,
    topic: str,
    issue: dict[str, Any],
    now: str,
) -> None:
    row = issue_payload_to_row(topic, issue, now)
    existing = conn.execute(
        "SELECT * FROM issues WHERE issue_number = ?", (row["issue_number"],)
    ).fetchone()

    if existing is None:
        placeholders = ", ".join("?" for _ in ISSUE_COLUMNS)
        conn.execute(
            f"INSERT INTO issues ({', '.join(ISSUE_COLUMNS)}) VALUES ({placeholders})",
            [row[column] for column in ISSUE_COLUMNS],
        )
    else:
        conn.execute(
            """
            UPDATE issues
            SET title = ?,
                url = ?,
                state = ?,
                labels = ?,
                created_at = COALESCE(NULLIF(created_at, ''), ?),
                updated_at = ?,
                last_seen_at = ?
            WHERE issue_number = ?
            """,
            (
                row["title"],
                row["url"],
                row["state"],
                row["labels"],
                row["created_at"],
                row["updated_at"],
                row["last_seen_at"],
                row["issue_number"],
            ),
        )
    conn.commit()


def archive_issue(
    conn: sqlite3.Connection,
    issue_number: int,
    reason: str,
    now: str,
) -> None:
    if reason not in {"closed", "linked_pr"}:
        raise ValueError(f"Unsupported archive reason: {reason}")
    my_status = "archived_closed" if reason == "closed" else "archived_linked_pr"
    state = "closed" if reason == "closed" else "open"
    linked_status = "linked" if reason == "linked_pr" else "unlinked"
    conn.execute(
        """
        UPDATE issues
        SET state = ?,
            archived_at = ?,
            archive_reason = ?,
            linked_pr_status = ?,
            my_status = ?
        WHERE issue_number = ?
        """,
        (state, now, reason, linked_status, my_status, issue_number),
    )
    conn.commit()


def mark_issue_linked_partial(
    conn: sqlite3.Connection,
    issue: dict[str, Any],
    now: str,
) -> None:
    conn.execute(
        """
        UPDATE issues
        SET state = ?,
            title = ?,
            url = ?,
            labels = ?,
            updated_at = ?,
            last_seen_at = ?,
            archived_at = '',
            archive_reason = '',
            linked_pr_status = 'linked_partial',
            my_status = CASE
                WHEN my_status IN ('archived_linked_pr', 'archived_closed')
                THEN 'triage'
                ELSE my_status
            END
        WHERE issue_number = ?
        """,
        (
            (issue.get("state") or "open").lower(),
            issue.get("title", ""),
            issue.get("url", ""),
            labels_to_text(issue.get("labels")),
            issue.get("updatedAt", ""),
            now,
            int(issue["number"]),
        ),
    )
    conn.commit()


def run_gh_json(args: list[str]) -> Any:
    command = ["gh", *args]
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or exc.stdout or "").strip()
        message = (
            f"{format_command(exc.cmd)} failed with exit code {exc.returncode}"
        )
        if details:
            message = f"{message}\n{details}"
        if is_rate_limit_error(details):
            message = (
                f"{message}\n\n"
                "GitHub search requests are limited separately from the normal "
                "REST API bucket. Wait for the search bucket to reset, or rerun "
                "with a larger delay, for example: "
                "GH_SEARCH_DELAY_SECONDS=3 python daily_update.py"
            )
            raise GhRateLimitError(message) from exc
        raise GhCommandError(message) from exc
    if not completed.stdout.strip():
        return None
    return json.loads(completed.stdout)


def search_rate_limit_status() -> dict[str, Any]:
    payload = run_gh_json(["api", "rate_limit"]) or {}
    resources = payload.get("resources") or {}
    status = resources.get("search") or {}
    if not isinstance(status, dict):
        return {}
    return status


def ensure_search_rate_available(status: dict[str, Any]) -> None:
    remaining = status.get("remaining")
    if remaining is None:
        return
    try:
        remaining_int = int(remaining)
    except (TypeError, ValueError):
        return
    if remaining_int > 0:
        return

    reset = format_reset_time(status.get("reset"))
    raise GhRateLimitError(
        "GitHub search rate limit is exhausted. "
        f"Wait until reset at {reset}, then rerun with a conservative delay, "
        "for example: GH_SEARCH_DELAY_SECONDS=3 python daily_update.py"
    )


def wait_for_search_rate_reset(
    status: dict[str, Any],
    min_remaining: int = 10,
    *,
    now: Any = time.time,
    sleep: Any = time.sleep,
    progress: Any | None = None,
) -> None:
    try:
        remaining = int(status.get("remaining"))
        reset = int(status.get("reset"))
    except (TypeError, ValueError):
        return

    if remaining >= min_remaining:
        return

    wait_seconds = max(0, reset - int(now()) + 5)
    if wait_seconds <= 0:
        return

    emit_progress(
        progress,
        "GitHub search bucket is low "
        f"({remaining} remaining). Waiting {format_seconds(wait_seconds)} "
        f"for reset at {format_reset_time(reset)}.",
    )
    sleep(wait_seconds)


def search_issues(query: str, limit: int = 10) -> list[dict[str, Any]]:
    return run_gh_json(
        [
            "search",
            "issues",
            query,
            "--repo",
            REPO,
            "--state",
            "open",
            "--limit",
            str(limit),
            "--json",
            "number,title,url,updatedAt,createdAt,labels",
        ]
    )


def fetch_issue(issue_number: int) -> dict[str, Any]:
    issue = run_gh_json(
        [
            "issue",
            "view",
            str(issue_number),
            "--repo",
            REPO,
            "--json",
            "state,title,url,updatedAt,createdAt,labels",
        ]
    )
    issue["number"] = issue_number
    return issue


def fetch_issue_with_body(issue_number: int) -> dict[str, Any]:
    issue = run_gh_json(
        [
            "issue",
            "view",
            str(issue_number),
            "--repo",
            REPO,
            "--json",
            "state,title,url,updatedAt,createdAt,labels,body",
        ]
    )
    issue["number"] = issue_number
    return issue


def find_linked_prs(issue_number: int) -> list[dict[str, Any]]:
    return run_gh_json(
        [
            "pr",
            "list",
            "--repo",
            REPO,
            "--state",
            "open",
            "--search",
            f"{issue_number} in:body",
            "--json",
            "number,title,url",
        ]
    )


def clean_subissue_title(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip()


def extract_issue_subissues(body: str, markers: list[str]) -> list[str]:
    if not body or not markers:
        return []

    subissues: list[str] = []
    in_section = False
    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if any(marker in stripped for marker in markers):
            in_section = True
            continue
        if not in_section:
            continue
        if stripped.startswith("### ") and subissues:
            break
        if not line.startswith("- "):
            continue

        task_match = re.match(r"^- \[(?P<checked>[ xX])\]\s+(?P<title>.+)$", line)
        if task_match:
            if task_match.group("checked").lower() == "x":
                continue
            subissues.append(clean_subissue_title(task_match.group("title")))
            continue

        bullet_match = re.match(r"^- (?!\[)(?P<title>.+)$", line)
        if bullet_match:
            subissues.append(clean_subissue_title(bullet_match.group("title")))

    return subissues


def apply_tracking_defaults(
    conn: sqlite3.Connection,
    issue_number: int,
    source: dict[str, Any],
    *,
    parent: bool = False,
) -> None:
    next_action = (
        source.get("parent_next_action")
        if parent
        else "Check linked PR coverage, then reproduce this slice if uncovered"
    )
    default_status = "triage"
    conn.execute(
        """
        UPDATE issues
        SET component = COALESCE(NULLIF(component, ''), ?),
            learning_value = COALESCE(NULLIF(learning_value, ''), ?),
            fixability = COALESCE(NULLIF(fixability, ''), ?),
            my_status = CASE
                WHEN COALESCE(my_status, '') IN (
                    '', 'new', 'archived_linked_pr', 'archived_closed'
                )
                THEN ?
                ELSE my_status
            END,
            next_action = COALESCE(NULLIF(next_action, ''), ?)
        WHERE issue_number = ?
        """,
        (
            source.get("component", ""),
            source.get("learning_value", ""),
            source.get("fixability", ""),
            default_status,
            next_action or "",
            issue_number,
        ),
    )
    conn.commit()


def subissue_payload(
    parent_issue: dict[str, Any],
    source: dict[str, Any],
    index: int,
    title: str,
) -> dict[str, Any]:
    parent_issue_number = int(parent_issue["number"])
    return {
        "number": synthetic_subissue_number(parent_issue_number, index),
        "title": f"[Subissue #{parent_issue_number}.{index}] {title}",
        "url": parent_issue.get("url", ""),
        "state": parent_issue.get("state", "open"),
        "labels": source.get("labels", "rfc-subissue"),
        "createdAt": parent_issue.get("createdAt", ""),
        "updatedAt": parent_issue.get("updatedAt", ""),
    }


def sync_issue_subissues(
    conn: sqlite3.Connection,
    sources: dict[int, dict[str, Any]],
    now: str,
    progress: Any | None = None,
) -> None:
    for issue_number, source in sources.items():
        emit_progress(progress, f"Parsing subissues from #{issue_number}.")
        issue = fetch_issue_with_body(issue_number)
        if not issue:
            continue
        issue["number"] = issue_number
        upsert_issue(conn, source["topic"], issue, now)
        mark_issue_linked_partial(conn, issue, now)
        apply_tracking_defaults(conn, issue_number, source, parent=True)

        for index, title in enumerate(
            extract_issue_subissues(issue.get("body", ""), source.get("markers", [])),
            start=1,
        ):
            child = subissue_payload(issue, source, index, title)
            upsert_issue(conn, source["topic"], child, now)
            apply_tracking_defaults(conn, int(child["number"]), source)


def sync_search_results(
    conn: sqlite3.Connection,
    topics: dict[str, dict[str, Any]],
    now: str,
    search_limiter: SearchRateLimiter | None = None,
    progress: Any | None = None,
) -> None:
    seen: set[int] = set()
    total_queries = count_topic_queries(topics)
    query_index = 0
    for topic_name, topic in topics.items():
        for query in topic["queries"]:
            query_index += 1
            emit_progress(
                progress,
                f"Searching {query_index}/{total_queries} [{topic_name}]: {query}",
            )
            if search_limiter is not None:
                search_limiter.wait()
            for issue in search_issues(query, limit=10):
                issue_number = int(issue["number"])
                if issue_number in seen:
                    continue
                seen.add(issue_number)
                upsert_issue(conn, topic_name, issue, now)


def active_issue_numbers(conn: sqlite3.Connection) -> list[int]:
    rows = conn.execute(
        """
        SELECT issue_number
        FROM issues
        WHERE COALESCE(archive_reason, '') = ''
          AND issue_number > 0
        ORDER BY issue_number
        """
    ).fetchall()
    return [int(row["issue_number"]) for row in rows]


def refresh_active_issues(
    conn: sqlite3.Connection,
    now: str,
    linked_pr_limiter: SearchRateLimiter | None = None,
    progress: Any | None = None,
) -> None:
    issue_numbers = active_issue_numbers(conn)
    total_issues = len(issue_numbers)
    for issue_index, issue_number in enumerate(issue_numbers, start=1):
        emit_progress(
            progress,
            f"Refreshing {issue_index}/{total_issues}: issue #{issue_number}",
        )
        issue = fetch_issue(issue_number)
        issue["number"] = issue_number
        state = (issue.get("state") or "").lower()
        if state == "closed":
            archive_issue(conn, issue_number, "closed", now)
            continue

        if linked_pr_limiter is not None:
            linked_pr_limiter.wait()
        linked_prs = find_linked_prs(issue_number)
        if linked_prs:
            if is_rfc_like_issue(issue) or issue_number in RFC_SUBISSUE_SOURCES:
                mark_issue_linked_partial(conn, issue, now)
                continue
            archive_issue(conn, issue_number, "linked_pr", now)
            continue

        conn.execute(
            """
            UPDATE issues
            SET state = ?,
                title = ?,
                url = ?,
                labels = ?,
                updated_at = ?,
                last_seen_at = ?,
                linked_pr_status = ?
            WHERE issue_number = ?
            """,
            (
                state or "open",
                issue.get("title", ""),
                issue.get("url", ""),
                labels_to_text(issue.get("labels")),
                issue.get("updatedAt", ""),
                now,
                "unlinked",
                issue_number,
            ),
        )
    conn.commit()


def active_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT *
        FROM issues
        WHERE COALESCE(archive_reason, '') = ''
        ORDER BY topic, updated_at DESC, issue_number DESC
        """
    ).fetchall()


def status_rank(status: str) -> int:
    return {
        "selected": 0,
        "fixable": 1,
        "new": 2,
        "triage": 3,
        "learning": 4,
        "needs_repro": 5,
    }.get(status, 99)


def learning_rank(value: str) -> int:
    return {
        "high": 0,
        "medium": 1,
        "low": 2,
    }.get(value.lower(), 3)


def action_queue_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    rows = [
        row
        for row in active_rows(conn)
        if row["my_status"] in ACTION_QUEUE_STATUSES
    ]
    rows.sort(key=lambda row: row["updated_at"] or "", reverse=True)
    rows.sort(key=lambda row: learning_rank(row["learning_value"] or ""))
    rows.sort(key=lambda row: status_rank(row["my_status"]))
    return rows


def escape_markdown_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", "<br>")


def markdown_row(row: sqlite3.Row, include_topic: bool = False) -> str:
    number = f"[#{display_issue_number(row['issue_number'])}]({row['url']})"
    values = [
        number,
        row["title"],
        row["labels"],
        row["updated_at"],
        row["my_status"],
        row["learning_value"],
        row["fixability"],
        row["next_action"],
        row["url"],
    ]
    if include_topic:
        values.insert(0, row["topic"])
    return "| " + " | ".join(escape_markdown_cell(value) for value in values) + " |"


def markdown_table(rows: list[sqlite3.Row], include_topic: bool = False) -> list[str]:
    headers = [
        "issue",
        "title",
        "labels",
        "updated_at",
        "my_status",
        "learning_value",
        "fixability",
        "next_action",
        "url",
    ]
    if include_topic:
        headers.insert(0, "topic")
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend(markdown_row(row, include_topic=include_topic) for row in rows)
    return lines


def render_markdown(
    conn: sqlite3.Connection,
    output_path: Path = MARKDOWN_PATH,
    topics: dict[str, dict[str, Any]] | None = None,
    generated_at: str | None = None,
) -> None:
    topics = topics or {}
    generated_at = generated_at or utc_now()
    rows_by_topic: dict[str, list[sqlite3.Row]] = {name: [] for name in topics}
    for row in active_rows(conn):
        rows_by_topic.setdefault(row["topic"], []).append(row)

    lines = [
        "# vLLM Issue Tracker",
        "",
        f"Generated at: {generated_at}",
        "",
        "## Action Queue",
        "",
    ]
    queue = action_queue_rows(conn)
    if queue:
        lines.extend(markdown_table(queue, include_topic=True))
    else:
        lines.append("_No active action items._")

    lines.extend(["", "## Topics", ""])
    for topic_name, topic in topics.items():
        lines.extend([f"### {topic_name}", "", topic.get("description", ""), ""])
        topic_rows = rows_by_topic.get(topic_name, [])
        if topic_rows:
            lines.extend(markdown_table(topic_rows))
        else:
            lines.append("_No active issues._")
        lines.append("")

    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def export_csv(conn: sqlite3.Connection, output_path: Path = CSV_PATH) -> None:
    rows = conn.execute(
        f"SELECT {', '.join(ISSUE_COLUMNS)} FROM issues ORDER BY topic, issue_number"
    ).fetchall()
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=ISSUE_COLUMNS,
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row[column] for column in ISSUE_COLUMNS})


def sync(
    topics_path: Path = TOPICS_PATH,
    db_path: Path = DB_PATH,
    markdown_path: Path = MARKDOWN_PATH,
    csv_path: Path = CSV_PATH,
    search_delay_seconds: float = DEFAULT_SEARCH_DELAY_SECONDS,
    progress: Any | None = stderr_progress,
) -> None:
    started_at_monotonic = time.monotonic()
    now = utc_now()
    topics = load_topics(topics_path)
    rate_status = search_rate_limit_status()
    ensure_search_rate_available(rate_status)
    wait_for_search_rate_reset(rate_status, progress=progress)
    search_limiter = SearchRateLimiter(search_delay_seconds)
    with connect_db(db_path) as conn:
        ensure_schema(conn)
        active_count = len(active_issue_numbers(conn))
        search_request_count = count_topic_queries(topics) + active_count
        minimum_wait = max(0, search_request_count - 1) * search_delay_seconds
        remaining = rate_status.get("remaining", "unknown")
        reset = format_reset_time(rate_status.get("reset"))
        emit_progress(
            progress,
            f"GitHub search bucket remaining: {remaining}; reset: {reset}",
        )
        emit_progress(
            progress,
            "Sync will make "
            f"{count_topic_queries(topics)} topic searches and up to "
            f"{active_count} linked-PR searches. Minimum rate-limit wait: "
            f"{format_seconds(minimum_wait)}.",
        )
        sync_search_results(
            conn,
            topics,
            now,
            search_limiter=search_limiter,
            progress=progress,
        )
        sync_issue_subissues(conn, RFC_SUBISSUE_SOURCES, now, progress=progress)
        refresh_active_issues(
            conn,
            now,
            linked_pr_limiter=search_limiter,
            progress=progress,
        )
        render_markdown(conn, markdown_path, topics, generated_at=now)
        export_csv(conn, csv_path)
        emit_progress(progress, f"Regenerated {markdown_path} and {csv_path}.")
        elapsed = time.monotonic() - started_at_monotonic
        emit_progress(
            progress,
            f"Finished sync at {utc_now()} (elapsed: {format_seconds(elapsed)}).",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topics", type=Path, default=TOPICS_PATH)
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--markdown", type=Path, default=MARKDOWN_PATH)
    parser.add_argument("--csv", type=Path, default=CSV_PATH)
    parser.add_argument(
        "--search-delay-seconds",
        type=float,
        default=DEFAULT_SEARCH_DELAY_SECONDS,
        help=(
            "Minimum delay between GitHub search-category requests. "
            "Defaults to GH_SEARCH_DELAY_SECONDS or 2.2 seconds."
        ),
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress sync progress output.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        sync(
            topics_path=args.topics,
            db_path=args.db,
            markdown_path=args.markdown,
            csv_path=args.csv,
            search_delay_seconds=args.search_delay_seconds,
            progress=None if args.quiet else stderr_progress,
        )
    except GhCommandError as exc:
        raise SystemExit(
            f"{exc}\n\nCheck GitHub CLI authentication with: gh auth status"
        ) from None


if __name__ == "__main__":
    main()
