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


def test_real_topics_include_expanded_learning_components():
    topics = daily_update.load_topics()

    expected_topics = {
        "multimodal_input_processing": [
            "multimodal -linked:pr",
            "prompt embedding -linked:pr",
        ],
        "sampling_logits_output": [
            "sampling -linked:pr",
            "logprobs -linked:pr",
        ],
        "pooling_embeddings": [
            "pooling -linked:pr",
            "embedding model -linked:pr",
        ],
        "compilation_runtime": [
            "torch.compile -linked:pr",
            "compile cache -linked:pr",
        ],
        "observability_metrics": [
            "metrics -linked:pr",
            "prometheus -linked:pr",
        ],
        "tokenization_chat_templates": [
            "tokenizer -linked:pr",
            "chat template -linked:pr",
        ],
        "model_loading_hf": [
            "model loading -linked:pr",
            "safetensors -linked:pr",
        ],
    }

    for topic_name, required_queries in expected_topics.items():
        assert topic_name in topics
        for query in required_queries:
            assert query in topics[topic_name]["queries"]


def test_real_topics_include_prioritized_model_family_buckets():
    topics = daily_update.load_topics()

    expected_model_topics = {
        "model_family_gemma4": [
            "Gemma4 -linked:pr",
            '"Gemma 4" -linked:pr',
        ],
        "model_family_deepseek_v4": [
            "DeepSeek-V4 -linked:pr",
            '"DeepSeek V4" -linked:pr',
        ],
        "model_family_gpt_oss": [
            "gpt-oss -linked:pr",
            "gptoss -linked:pr",
            "gpt_oss -linked:pr",
            "openai/gpt-oss -linked:pr",
        ],
    }

    assert list(topics)[: len(expected_model_topics)] == list(expected_model_topics)
    for topic_name, required_queries in expected_model_topics.items():
        assert topic_name in topics
        for query in required_queries:
            assert query in topics[topic_name]["queries"]


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


def test_active_issue_numbers_excludes_synthetic_subissues():
    conn = make_conn()
    daily_update.upsert_issue(conn, "kv_cache", make_issue(), "2026-05-01T12:00:00Z")
    daily_update.upsert_issue(
        conn,
        "model_family_gpt_oss",
        make_issue(
            daily_update.synthetic_subissue_number(28262, 1),
            "[Subissue #28262.1] Reasoning channel metadata",
        ),
        "2026-05-01T12:00:00Z",
    )

    assert daily_update.active_issue_numbers(conn) == [123]


def test_refresh_active_issues_keeps_rfc_parent_active_when_pr_is_linked(monkeypatch):
    conn = make_conn()
    daily_update.upsert_issue(
        conn,
        "model_family_gpt_oss",
        make_issue(27653, "[RFC]: include past-reasoning"),
        "2026-05-01T12:00:00Z",
    )

    monkeypatch.setattr(
        daily_update,
        "fetch_issue",
        lambda issue_number: {
            "state": "open",
            "title": "[RFC]: include past-reasoning",
            "url": f"https://github.com/vllm-project/vllm/issues/{issue_number}",
            "labels": [{"name": "RFC"}],
            "updatedAt": "2026-05-01T13:00:00Z",
        },
    )
    monkeypatch.setattr(
        daily_update,
        "find_linked_prs",
        lambda issue_number: [{"number": 35907, "title": "Partial Harmony fix"}],
    )

    daily_update.refresh_active_issues(conn, "2026-05-01T14:00:00Z")

    row = fetch_issue(conn, 27653)
    assert row["archive_reason"] == ""
    assert row["archived_at"] == ""
    assert row["linked_pr_status"] == "linked_partial"
    assert row["my_status"] == "new"


def test_refresh_active_issues_keeps_decomposed_parent_active_when_pr_is_linked(monkeypatch):
    conn = make_conn()
    daily_update.upsert_issue(
        conn,
        "model_family_gpt_oss",
        make_issue(28262, "[Bug]: [gpt-oss] Responses API incorrect input/output handling"),
        "2026-05-01T12:00:00Z",
    )

    monkeypatch.setattr(
        daily_update,
        "fetch_issue",
        lambda issue_number: {
            "state": "open",
            "title": "[Bug]: [gpt-oss] Responses API incorrect input/output handling",
            "url": f"https://github.com/vllm-project/vllm/issues/{issue_number}",
            "labels": [{"name": "bug"}],
            "updatedAt": "2026-05-01T13:00:00Z",
        },
    )
    monkeypatch.setattr(
        daily_update,
        "find_linked_prs",
        lambda issue_number: [{"number": 28355, "title": "Partial metadata fix"}],
    )

    daily_update.refresh_active_issues(conn, "2026-05-01T14:00:00Z")

    row = fetch_issue(conn, 28262)
    assert row["archive_reason"] == ""
    assert row["linked_pr_status"] == "linked_partial"


def test_markdown_displays_synthetic_subissue_parent_and_index(tmp_path):
    conn = make_conn()
    subissue_number = daily_update.synthetic_subissue_number(28262, 1)
    subissue = make_issue(subissue_number, "[Subissue #28262.1] Reasoning channel metadata")
    subissue["url"] = "https://github.com/vllm-project/vllm/issues/28262"
    daily_update.upsert_issue(
        conn,
        "model_family_gpt_oss",
        subissue,
        "2026-05-01T12:00:00Z",
    )
    output_file = tmp_path / "ISSUES.md"

    daily_update.render_markdown(
        conn,
        output_file,
        {
            "model_family_gpt_oss": {
                "description": "gpt-oss model-family issues.",
                "queries": [],
            },
        },
        generated_at="2026-05-04T09:00:00Z",
    )

    markdown = output_file.read_text(encoding="utf-8")
    assert "[#28262.1](https://github.com/vllm-project/vllm/issues/28262)" in markdown


def test_extract_issue_subissues_parses_unchecked_tasks_and_top_level_bullets():
    body = """
### TODOs

- [x] create Parser class
- [ ] use parser class in other entrypoints
- [ ] move GPT-OSS Harmony to the Parser class
  - nested detail should not become its own row

### Feedback Period.
"""

    subissues = daily_update.extract_issue_subissues(body, ["### TODOs"])

    assert subissues == [
        "use parser class in other entrypoints",
        "move GPT-OSS Harmony to the Parser class",
    ]


def test_sync_issue_subissues_reactivates_parent_and_tracks_children(monkeypatch):
    conn = make_conn()
    parent = make_issue(28262, "[Bug]: [gpt-oss] Responses API incorrect input/output handling")
    parent["labels"] = [{"name": "bug"}, {"name": "stale"}]
    parent["body"] = """
The changes we can make are:
- A reasoning message should use the channel of the message that follows it.
  - The reasoning message prior to a function tool call should be on the commentary channel
- Set the content_type for function tools to be `<|constrain|>json` always
"""
    daily_update.upsert_issue(
        conn,
        "model_family_gpt_oss",
        parent,
        "2026-05-01T12:00:00Z",
    )
    daily_update.archive_issue(conn, 28262, "linked_pr", "2026-05-01T13:00:00Z")

    monkeypatch.setattr(daily_update, "fetch_issue_with_body", lambda issue_number: parent)
    source = {
        "topic": "model_family_gpt_oss",
        "component": "gpt-oss/responses api harmony",
        "learning_value": "high",
        "fixability": "medium",
        "labels": "rfc-subissue, gpt-oss, harmony",
        "markers": ["The changes we can make are:"],
        "parent_next_action": "Track parsed subissues instead of treating linked PRs as complete coverage",
    }

    daily_update.sync_issue_subissues(
        conn,
        {28262: source},
        "2026-05-01T14:00:00Z",
    )

    parent_row = fetch_issue(conn, 28262)
    assert parent_row["archive_reason"] == ""
    assert parent_row["linked_pr_status"] == "linked_partial"
    assert parent_row["my_status"] == "triage"
    assert parent_row["next_action"] == source["parent_next_action"]

    first_child = fetch_issue(conn, daily_update.synthetic_subissue_number(28262, 1))
    assert first_child["topic"] == "model_family_gpt_oss"
    assert first_child["url"] == "https://github.com/vllm-project/vllm/issues/28262"
    assert first_child["labels"] == "rfc-subissue, gpt-oss, harmony"
    assert first_child["component"] == "gpt-oss/responses api harmony"
    assert first_child["learning_value"] == "high"
    assert first_child["fixability"] == "medium"
    assert first_child["my_status"] == "triage"
    assert first_child["next_action"] == "Check linked PR coverage, then reproduce this slice if uncovered"


def test_sync_outputs_finished_time_and_elapsed(monkeypatch, tmp_path):
    topics_file = tmp_path / "topics.yaml"
    topics_file.write_text(
        """
topics:
  kv_cache:
    description: KV cache behavior.
    queries: []
""".lstrip(),
        encoding="utf-8",
    )
    progress_messages = []
    ticks = iter([10.0, 15.4])

    monkeypatch.setattr(
        daily_update,
        "search_rate_limit_status",
        lambda: {"remaining": 30, "reset": 1770000000},
    )
    monkeypatch.setattr(daily_update, "fetch_issue_with_body", lambda issue_number: None)
    monkeypatch.setattr(daily_update.time, "monotonic", lambda: next(ticks))

    daily_update.sync(
        topics_path=topics_file,
        db_path=tmp_path / "issues.sqlite",
        markdown_path=tmp_path / "ISSUES.md",
        csv_path=tmp_path / "issues.csv",
        progress=progress_messages.append,
    )

    assert any(
        message.startswith("Finished sync at ") and "elapsed: 5s" in message
        for message in progress_messages
    )


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


def test_search_rate_limiter_sleeps_between_calls():
    now = [100.0]
    sleeps = []

    def clock():
        return now[0]

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    limiter = daily_update.SearchRateLimiter(
        min_interval_seconds=2.0,
        clock=clock,
        sleep=sleep,
    )

    limiter.wait()
    limiter.wait()

    assert sleeps == [2.0]


def test_sync_search_results_rate_limits_each_search_query(monkeypatch):
    conn = make_conn()
    waits = []
    queries = []
    progress_messages = []

    class FakeLimiter:
        def wait(self):
            waits.append("wait")

    def fake_search_issues(query, limit=10):
        queries.append((query, limit))
        return []

    monkeypatch.setattr(daily_update, "search_issues", fake_search_issues)

    daily_update.sync_search_results(
        conn,
        {
            "kv_cache": {
                "description": "KV cache behavior.",
                "queries": ["kv cache -linked:pr", "prefix cache -linked:pr"],
            }
        },
        "2026-05-01T12:00:00Z",
        search_limiter=FakeLimiter(),
        progress=progress_messages.append,
    )

    assert waits == ["wait", "wait"]
    assert queries == [
        ("kv cache -linked:pr", 10),
        ("prefix cache -linked:pr", 10),
    ]
    assert progress_messages == [
        "Searching 1/2 [kv_cache]: kv cache -linked:pr",
        "Searching 2/2 [kv_cache]: prefix cache -linked:pr",
    ]


def test_refresh_active_issues_rate_limits_linked_pr_search(monkeypatch):
    conn = make_conn()
    daily_update.upsert_issue(conn, "kv_cache", make_issue(), "2026-05-01T12:00:00Z")
    waits = []

    class FakeLimiter:
        def wait(self):
            waits.append("wait")

    monkeypatch.setattr(
        daily_update,
        "fetch_issue",
        lambda issue_number: {
            "state": "open",
            "title": "KV cache blocks",
            "url": f"https://github.com/vllm-project/vllm/issues/{issue_number}",
            "labels": [],
            "updatedAt": "2026-05-01T13:00:00Z",
        },
    )
    monkeypatch.setattr(daily_update, "find_linked_prs", lambda issue_number: [])

    daily_update.refresh_active_issues(
        conn,
        "2026-05-01T14:00:00Z",
        linked_pr_limiter=FakeLimiter(),
    )

    assert waits == ["wait"]


def test_sync_raises_clear_error_when_search_bucket_is_empty(monkeypatch, tmp_path):
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
    monkeypatch.setattr(
        daily_update,
        "search_rate_limit_status",
        lambda: {"remaining": 0, "reset": 1770000000},
    )

    with pytest.raises(daily_update.GhRateLimitError) as exc_info:
        daily_update.sync(
            topics_path=topics_file,
            db_path=tmp_path / "issues.sqlite",
            markdown_path=tmp_path / "ISSUES.md",
            csv_path=tmp_path / "issues.csv",
        )

    message = str(exc_info.value)
    assert "GitHub search rate limit is exhausted" in message
    assert "1770000000" in message


def test_wait_for_search_rate_reset_sleeps_when_remaining_is_low():
    sleeps = []

    daily_update.wait_for_search_rate_reset(
        {"remaining": 3, "reset": 120},
        min_remaining=10,
        now=lambda: 100,
        sleep=sleeps.append,
    )

    assert sleeps == [25]


def test_wait_for_search_rate_reset_does_not_sleep_when_budget_is_available():
    sleeps = []

    daily_update.wait_for_search_rate_reset(
        {"remaining": 12, "reset": 120},
        min_remaining=10,
        now=lambda: 100,
        sleep=sleeps.append,
    )

    assert sleeps == []


def test_export_csv_writes_all_schema_columns(tmp_path):
    conn = make_conn()
    daily_update.upsert_issue(conn, "kv_cache", make_issue(), "2026-05-01T12:00:00Z")
    output_file = tmp_path / "issues.csv"

    daily_update.export_csv(conn, output_file)

    assert b"\r\n" not in output_file.read_bytes()

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


def test_run_gh_json_reports_rate_limit_guidance(monkeypatch):
    def fail_run(*args, **kwargs):
        raise subprocess.CalledProcessError(
            returncode=1,
            cmd=["gh", "search", "issues", "kv cache"],
            stderr="HTTP 403: API rate limit exceeded for user ID 123",
        )

    monkeypatch.setattr(daily_update.subprocess, "run", fail_run)

    with pytest.raises(daily_update.GhRateLimitError) as exc_info:
        daily_update.run_gh_json(["search", "issues", "kv cache"])

    message = str(exc_info.value)
    assert "API rate limit exceeded" in message
    assert "GitHub search requests are limited separately" in message
    assert "GH_SEARCH_DELAY_SECONDS" in message
