import csv
import sqlite3
import subprocess

import pytest
import daily_update


def make_issue(number=123, title="KV cache blocks"):
    return {
        "number": number,
        "title": title,
        "url": f"https://github.com/vllm-project/vllm/issues/{number}",
        "state": "open",
        "labels": [{"name": "bug"}, {"name": "help wanted"}],
        "createdAt": "2026-04-01T10:00:00Z",
        "updatedAt": "2026-04-02T11:00:00Z",
    }


def make_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    daily_update.ensure_schema(conn)
    return conn


def fetch_issue(conn, number):
    return conn.execute(
        "SELECT * FROM issues WHERE issue_number = ?", (number,)
    ).fetchone()


def test_load_topics_reads_topic_definitions(tmp_path):
    topics_file = tmp_path / "topics.yaml"
    topics_file.write_text(
        """
topics:
  kv_cache:
    description: KV cache behavior.
    queries:
      - 'kv cache -linked:pr'
""".lstrip(),
        encoding="utf-8",
    )

    topics = daily_update.load_topics(topics_file)

    assert topics == {
        "kv_cache": {
            "description": "KV cache behavior.",
            "queries": ["kv cache -linked:pr"],
        }
    }


def test_upsert_issue_preserves_personal_triage_fields():
    conn = make_conn()
    daily_update.upsert_issue(conn, "kv_cache", make_issue(), "2026-05-01T12:00:00Z")
    conn.execute(
        """
        UPDATE issues
        SET my_status = ?, notes = ?, learning_value = ?, fixability = ?
        WHERE issue_number = ?
        """,
        ("learning", "Read block_manager.py", "high", "medium", 123),
    )

    daily_update.upsert_issue(
        conn,
        "scheduler_batching",
        make_issue(title="KV cache blocks renamed"),
        "2026-05-02T12:00:00Z",
    )

    row = fetch_issue(conn, 123)
    assert row["topic"] == "kv_cache"
    assert row["title"] == "KV cache blocks renamed"
    assert row["labels"] == "bug, help wanted"
    assert row["last_seen_at"] == "2026-05-02T12:00:00Z"
    assert row["my_status"] == "learning"
    assert row["notes"] == "Read block_manager.py"
    assert row["learning_value"] == "high"
    assert row["fixability"] == "medium"


def test_archive_issue_records_closed_reason_and_status():
    conn = make_conn()
    daily_update.upsert_issue(conn, "kv_cache", make_issue(), "2026-05-01T12:00:00Z")

    daily_update.archive_issue(conn, 123, "closed", "2026-05-03T08:00:00Z")

    row = fetch_issue(conn, 123)
    assert row["state"] == "closed"
    assert row["archive_reason"] == "closed"
    assert row["archived_at"] == "2026-05-03T08:00:00Z"
    assert row["my_status"] == "archived_closed"


def test_render_markdown_groups_active_issues_and_excludes_archived(tmp_path):
    conn = make_conn()
    daily_update.upsert_issue(conn, "kv_cache", make_issue(), "2026-05-01T12:00:00Z")
    daily_update.upsert_issue(conn, "kv_cache", make_issue(124, "Closed issue"), "2026-05-01T12:00:00Z")
    conn.execute(
        """
        UPDATE issues
        SET my_status = ?, learning_value = ?, fixability = ?, next_action = ?
        WHERE issue_number = ?
        """,
        ("fixable", "high", "medium", "Reproduce locally", 123),
    )
    daily_update.archive_issue(conn, 124, "linked_pr", "2026-05-03T08:00:00Z")
    output_file = tmp_path / "ISSUES.md"

    daily_update.render_markdown(
        conn,
        output_file,
        {
            "kv_cache": {"description": "KV cache behavior.", "queries": []},
            "scheduler_batching": {"description": "Scheduler behavior.", "queries": []},
        },
        generated_at="2026-05-04T09:00:00Z",
    )

    markdown = output_file.read_text(encoding="utf-8")
    assert "# vLLM Issue Tracker" in markdown
    assert "Generated at: 2026-05-04T09:00:00Z" in markdown
    assert "## Action Queue" in markdown
    assert "KV cache blocks" in markdown
    assert "Reproduce locally" in markdown
    assert "### kv_cache" in markdown
    assert "KV cache behavior." in markdown
    assert "Closed issue" not in markdown
    assert "### scheduler_batching" in markdown
    assert "_No active issues._" in markdown


def test_action_queue_sorts_by_status_learning_value_and_recent_updates():
    conn = make_conn()
    daily_update.upsert_issue(
        conn,
        "kv_cache",
        make_issue(123, "Older fixable issue"),
        "2026-05-01T12:00:00Z",
    )
    daily_update.upsert_issue(
        conn,
        "kv_cache",
        make_issue(124, "Selected issue"),
        "2026-05-01T12:00:00Z",
    )
    daily_update.upsert_issue(
        conn,
        "kv_cache",
        make_issue(125, "Newer fixable issue"),
        "2026-05-01T12:00:00Z",
    )
    conn.execute(
        "UPDATE issues SET my_status = ?, learning_value = ?, updated_at = ? WHERE issue_number = ?",
        ("fixable", "high", "2026-04-02T11:00:00Z", 123),
    )
    conn.execute(
        "UPDATE issues SET my_status = ?, learning_value = ?, updated_at = ? WHERE issue_number = ?",
        ("selected", "low", "2026-04-01T11:00:00Z", 124),
    )
    conn.execute(
        "UPDATE issues SET my_status = ?, learning_value = ?, updated_at = ? WHERE issue_number = ?",
        ("fixable", "high", "2026-04-03T11:00:00Z", 125),
    )

    rows = daily_update.action_queue_rows(conn)

    assert [row["issue_number"] for row in rows] == [124, 125, 123]


def test_export_csv_writes_all_schema_columns(tmp_path):
    conn = make_conn()
    daily_update.upsert_issue(conn, "kv_cache", make_issue(), "2026-05-01T12:00:00Z")
    output_file = tmp_path / "issues.csv"

    daily_update.export_csv(conn, output_file)

    with output_file.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert rows == [
        {
            "topic": "kv_cache",
            "issue_number": "123",
            "title": "KV cache blocks",
            "url": "https://github.com/vllm-project/vllm/issues/123",
            "state": "open",
            "labels": "bug, help wanted",
            "created_at": "2026-04-01T10:00:00Z",
            "updated_at": "2026-04-02T11:00:00Z",
            "last_seen_at": "2026-05-01T12:00:00Z",
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
    ]


def test_run_gh_json_reports_cli_failures(monkeypatch):
    def fail_run(*args, **kwargs):
        raise subprocess.CalledProcessError(
            returncode=1,
            cmd=["gh", "auth", "status"],
            stderr="token is invalid",
        )

    monkeypatch.setattr(daily_update.subprocess, "run", fail_run)

    with pytest.raises(daily_update.GhCommandError) as exc_info:
        daily_update.run_gh_json(["auth", "status"])

    message = str(exc_info.value)
    assert "gh auth status" in message
    assert "token is invalid" in message
