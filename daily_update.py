#!/usr/bin/env python3
"""Sync open vLLM issues into a local SQLite tracker."""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


REPO = "vllm-project/vllm"
TOPICS_PATH = Path("topics.yaml")
DB_PATH = Path("issues.sqlite")
MARKDOWN_PATH = Path("ISSUES.md")
CSV_PATH = Path("issues.csv")

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


class GhCommandError(RuntimeError):
    """Raised when the GitHub CLI exits unsuccessfully."""


def format_command(command: Any) -> str:
    if isinstance(command, list):
        return " ".join(str(part) for part in command)
    return str(command)


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
        raise GhCommandError(message) from exc
    if not completed.stdout.strip():
        return None
    return json.loads(completed.stdout)


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
    return run_gh_json(
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


def sync_search_results(
    conn: sqlite3.Connection,
    topics: dict[str, dict[str, Any]],
    now: str,
) -> None:
    seen: set[int] = set()
    for topic_name, topic in topics.items():
        for query in topic["queries"]:
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
        ORDER BY issue_number
        """
    ).fetchall()
    return [int(row["issue_number"]) for row in rows]


def refresh_active_issues(conn: sqlite3.Connection, now: str) -> None:
    for issue_number in active_issue_numbers(conn):
        issue = fetch_issue(issue_number)
        state = (issue.get("state") or "").lower()
        if state == "closed":
            archive_issue(conn, issue_number, "closed", now)
            continue

        linked_prs = find_linked_prs(issue_number)
        if linked_prs:
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
    number = f"[#{row['issue_number']}]({row['url']})"
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
        writer = csv.DictWriter(handle, fieldnames=ISSUE_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row[column] for column in ISSUE_COLUMNS})


def sync(
    topics_path: Path = TOPICS_PATH,
    db_path: Path = DB_PATH,
    markdown_path: Path = MARKDOWN_PATH,
    csv_path: Path = CSV_PATH,
) -> None:
    now = utc_now()
    topics = load_topics(topics_path)
    with connect_db(db_path) as conn:
        ensure_schema(conn)
        sync_search_results(conn, topics, now)
        refresh_active_issues(conn, now)
        render_markdown(conn, markdown_path, topics, generated_at=now)
        export_csv(conn, csv_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topics", type=Path, default=TOPICS_PATH)
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--markdown", type=Path, default=MARKDOWN_PATH)
    parser.add_argument("--csv", type=Path, default=CSV_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        sync(
            topics_path=args.topics,
            db_path=args.db,
            markdown_path=args.markdown,
            csv_path=args.csv,
        )
    except GhCommandError as exc:
        raise SystemExit(
            f"{exc}\n\nCheck GitHub CLI authentication with: gh auth status"
        ) from None


if __name__ == "__main__":
    main()
