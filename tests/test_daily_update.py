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
        "assignees": [],
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


def test_default_vllm_output_paths_are_prefixed():
    assert daily_update.MARKDOWN_PATH == daily_update.Path("VLLM_ISSUES.md")
    assert daily_update.CSV_PATH == daily_update.Path("vllm_issues.csv")
    assert daily_update.DB_PATH == daily_update.Path("vllm_issues.sqlite")


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


def test_real_topics_include_focused_contribution_components():
    topics = daily_update.load_topics()

    expected_topics = {
        "multimodal_input_processing": [
            "multimodal -linked:pr",
            "prompt embedding -linked:pr",
        ],
        "tokenization_chat_templates": [
            "tokenizer -linked:pr",
            "chat template -linked:pr",
        ],
        "hardware_b200_b300": [
            "B200 -linked:pr",
            "B300 -linked:pr",
            "GB200 -linked:pr",
            "GB300 -linked:pr",
        ],
    }
    removed_topics = {
        "model_loading_hf",
        "observability_metrics",
        "compilation_runtime",
        "pooling_embeddings",
        "sampling_logits_output",
        "lora_adapters",
        "quantization",
    }

    for topic_name, required_queries in expected_topics.items():
        assert topic_name in topics
        for query in required_queries:
            assert query in topics[topic_name]["queries"]
    for topic_name in removed_topics:
        assert topic_name not in topics
    assert "Blackwell -linked:pr" not in topics["hardware_b200_b300"]["queries"]
    assert '"Blackwell GPU" -linked:pr' not in topics["hardware_b200_b300"]["queries"]


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


def test_vllm_omni_topics_track_selected_buckets_without_hardware():
    topics = daily_update.load_topics(daily_update.Path("topics_vllm_omni.yaml"))

    expected_topics = {
        "diffusion_image_video",
        "tts_audio_voice",
        "qwen3_omni",
        "ci_testing_regressions",
        "orchestrator_engine_pipeline",
        "serving_api_entrypoints",
        "disaggregated_transfer_memory",
        "quantization",
        "robotics_world_models",
        "metrics_observability",
        "attention_cache_kernels",
        "docs_devex_release",
        "new_model_requests",
        "performance_latency",
        "config_deployment",
        "lora_adapters",
        "rl_training_rollout",
        "other_general",
    }

    assert set(topics) == expected_topics
    assert "hardware_accelerators" not in topics
    assert "NPU -linked:pr" not in str(topics)


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


def test_upsert_issue_retargets_removed_topic_archive_when_seen_again():
    conn = make_conn()
    daily_update.upsert_issue(
        conn,
        "quantization",
        make_issue(41360, "B200 old topic issue"),
        "2026-05-01T12:00:00Z",
    )
    conn.execute(
        """
        UPDATE issues
        SET my_status = ?, notes = ?, archive_reason = ?, archived_at = ?
        WHERE issue_number = ?
        """,
        (
            "archived_removed_topic",
            "Keep repro notes",
            "removed_topic",
            "2026-05-02T12:00:00Z",
            41360,
        ),
    )
    conn.commit()

    daily_update.upsert_issue(
        conn,
        "hardware_b200_b300",
        make_issue(41360, "B200 current topic issue"),
        "2026-05-03T12:00:00Z",
    )

    row = fetch_issue(conn, 41360)
    assert row["topic"] == "hardware_b200_b300"
    assert row["title"] == "B200 current topic issue"
    assert row["archive_reason"] == ""
    assert row["archived_at"] == ""
    assert row["linked_pr_status"] == "unlinked"
    assert row["my_status"] == "triage"
    assert row["notes"] == "Keep repro notes"


def test_upsert_issue_reactivates_assigned_archive_when_seen_unassigned():
    conn = make_conn()
    assigned_issue = make_issue(41360, "Previously assigned issue")
    assigned_issue["assignees"] = [{"login": "maintainer"}]
    daily_update.upsert_issue(
        conn,
        "kv_cache",
        assigned_issue,
        "2026-05-01T12:00:00Z",
    )
    daily_update.archive_issue(conn, 41360, "assigned", "2026-05-02T12:00:00Z")

    daily_update.upsert_issue(
        conn,
        "kv_cache",
        make_issue(41360, "Now unassigned issue"),
        "2026-05-03T12:00:00Z",
    )

    row = fetch_issue(conn, 41360)
    assert row["title"] == "Now unassigned issue"
    assert row["assignees"] == ""
    assert row["archive_reason"] == ""
    assert row["archived_at"] == ""
    assert row["my_status"] == "triage"


def test_archive_issue_records_closed_reason_and_status():
    conn = make_conn()
    daily_update.upsert_issue(conn, "kv_cache", make_issue(), "2026-05-01T12:00:00Z")

    daily_update.archive_issue(conn, 123, "closed", "2026-05-03T08:00:00Z")

    row = fetch_issue(conn, 123)
    assert row["state"] == "closed"
    assert row["archive_reason"] == "closed"
    assert row["archived_at"] == "2026-05-03T08:00:00Z"
    assert row["my_status"] == "archived_closed"


def test_archive_issue_records_assigned_reason_and_status():
    conn = make_conn()
    daily_update.upsert_issue(conn, "kv_cache", make_issue(), "2026-05-01T12:00:00Z")

    daily_update.archive_issue(conn, 123, "assigned", "2026-05-03T08:00:00Z")

    row = fetch_issue(conn, 123)
    assert row["state"] == "open"
    assert row["archive_reason"] == "assigned"
    assert row["archived_at"] == "2026-05-03T08:00:00Z"
    assert row["my_status"] == "archived_assigned"


def test_archive_excluded_hardware_issues_archives_stored_rocm_rows():
    conn = make_conn()
    rocm_issue = make_issue(123, "ROCm-only issue")
    rocm_issue["labels"] = [{"name": "bug"}, {"name": "rocm"}]
    cuda_issue = make_issue(124, "CUDA issue")
    daily_update.upsert_issue(conn, "kv_cache", rocm_issue, "2026-05-01T12:00:00Z")
    daily_update.upsert_issue(conn, "kv_cache", cuda_issue, "2026-05-01T12:00:00Z")

    daily_update.archive_excluded_hardware_issues(conn, "2026-05-03T08:00:00Z")

    rocm_row = fetch_issue(conn, 123)
    cuda_row = fetch_issue(conn, 124)
    assert rocm_row["archive_reason"] == "excluded_amd_rocm"
    assert rocm_row["archived_at"] == "2026-05-03T08:00:00Z"
    assert rocm_row["my_status"] == "archived_excluded_amd_rocm"
    assert cuda_row["archive_reason"] == ""


def test_archive_excluded_hardware_issues_archives_stored_amd_gpu_titles():
    conn = make_conn()
    daily_update.upsert_issue(
        conn,
        "kv_cache",
        make_issue(123, "[CI Failure]: mi300_1: V1 Core + KV + Metrics"),
        "2026-05-01T12:00:00Z",
    )

    daily_update.archive_excluded_hardware_issues(conn, "2026-05-03T08:00:00Z")

    row = fetch_issue(conn, 123)
    assert row["archive_reason"] == "excluded_amd_rocm"
    assert row["my_status"] == "archived_excluded_amd_rocm"


def test_refresh_active_issues_archives_unresolvable_issue(monkeypatch):
    conn = make_conn()
    daily_update.upsert_issue(conn, "kv_cache", make_issue(), "2026-05-01T12:00:00Z")

    def missing_issue(issue_number):
        raise daily_update.GhNotFoundError("issue no longer exists")

    monkeypatch.setattr(daily_update, "fetch_issue", missing_issue)

    daily_update.refresh_active_issues(conn, "2026-05-05T06:00:00Z")

    row = fetch_issue(conn, 123)
    assert row["archive_reason"] == "not_found"
    assert row["archived_at"] == "2026-05-05T06:00:00Z"
    assert row["my_status"] == "archived_not_found"


def test_refresh_active_issues_archives_excluded_hardware_label(monkeypatch):
    conn = make_conn()
    daily_update.upsert_issue(conn, "kv_cache", make_issue(), "2026-05-01T12:00:00Z")

    monkeypatch.setattr(
        daily_update,
        "fetch_issue",
        lambda issue_number: {
            "state": "open",
            "title": "ROCm-only issue",
            "url": f"https://github.com/vllm-project/vllm/issues/{issue_number}",
            "labels": [{"name": "ROCm"}],
            "updatedAt": "2026-05-01T13:00:00Z",
        },
    )

    def fail_linked_pr_search(issue_number):
        raise AssertionError("excluded hardware issues should not search linked PRs")

    monkeypatch.setattr(daily_update, "find_linked_prs", fail_linked_pr_search)

    daily_update.refresh_active_issues(conn, "2026-05-05T06:00:00Z")

    row = fetch_issue(conn, 123)
    assert row["title"] == "ROCm-only issue"
    assert row["labels"] == "ROCm"
    assert row["archive_reason"] == "excluded_amd_rocm"
    assert row["archived_at"] == "2026-05-05T06:00:00Z"
    assert row["my_status"] == "archived_excluded_amd_rocm"


def test_refresh_active_issues_archives_assigned_issue(monkeypatch):
    conn = make_conn()
    daily_update.upsert_issue(conn, "kv_cache", make_issue(), "2026-05-01T12:00:00Z")

    monkeypatch.setattr(
        daily_update,
        "fetch_issue",
        lambda issue_number: {
            "state": "open",
            "title": "Assigned issue",
            "url": f"https://github.com/vllm-project/vllm/issues/{issue_number}",
            "labels": [{"name": "bug"}],
            "assignees": [{"login": "maintainer"}],
            "updatedAt": "2026-05-01T13:00:00Z",
        },
    )

    def fail_linked_pr_search(issue_number):
        raise AssertionError("assigned issues should not search linked PRs")

    monkeypatch.setattr(daily_update, "find_linked_prs", fail_linked_pr_search)

    daily_update.refresh_active_issues(conn, "2026-05-05T06:00:00Z")

    row = fetch_issue(conn, 123)
    assert row["title"] == "Assigned issue"
    assert row["assignees"] == "maintainer"
    assert row["archive_reason"] == "assigned"
    assert row["archived_at"] == "2026-05-05T06:00:00Z"
    assert row["my_status"] == "archived_assigned"


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


def test_refresh_active_issues_keeps_decomposed_parent_active_when_pr_is_linked(
    monkeypatch,
):
    conn = make_conn()
    daily_update.upsert_issue(
        conn,
        "model_family_gpt_oss",
        make_issue(
            28262, "[Bug]: [gpt-oss] Responses API incorrect input/output handling"
        ),
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
    subissue = make_issue(
        subissue_number, "[Subissue #28262.1] Reasoning channel metadata"
    )
    subissue["url"] = "https://github.com/vllm-project/vllm/issues/28262"
    daily_update.upsert_issue(
        conn,
        "model_family_gpt_oss",
        subissue,
        "2026-05-01T12:00:00Z",
    )
    output_file = tmp_path / "VLLM_ISSUES.md"

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
    parent = make_issue(
        28262, "[Bug]: [gpt-oss] Responses API incorrect input/output handling"
    )
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

    monkeypatch.setattr(
        daily_update, "fetch_issue_with_body", lambda issue_number: parent
    )
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
    assert (
        first_child["next_action"]
        == "Check linked PR coverage, then reproduce this slice if uncovered"
    )


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
    monkeypatch.setattr(
        daily_update, "fetch_issue_with_body", lambda issue_number: None
    )
    monkeypatch.setattr(daily_update.time, "monotonic", lambda: next(ticks))

    daily_update.sync(
        topics_path=topics_file,
        db_path=tmp_path / "vllm_issues.sqlite",
        markdown_path=tmp_path / "VLLM_ISSUES.md",
        csv_path=tmp_path / "vllm_issues.csv",
        progress=progress_messages.append,
    )

    assert any(
        message.startswith("Finished sync at ") and "elapsed: 5s" in message
        for message in progress_messages
    )


def test_sync_skips_vllm_subissue_sources_for_other_repos(monkeypatch, tmp_path):
    topics_file = tmp_path / "topics.yaml"
    topics_file.write_text(
        """
topics:
  qwen3_omni:
    description: Qwen3-Omni issues.
    queries: []
""".lstrip(),
        encoding="utf-8",
    )
    subissue_calls = []

    monkeypatch.setattr(
        daily_update,
        "search_rate_limit_status",
        lambda: {"remaining": 30, "reset": 1770000000},
    )
    monkeypatch.setattr(
        daily_update,
        "sync_issue_subissues",
        lambda *args, **kwargs: subissue_calls.append((args, kwargs)),
    )

    daily_update.sync(
        topics_path=topics_file,
        db_path=tmp_path / "vllm_issues.sqlite",
        markdown_path=tmp_path / "VLLM_ISSUES.md",
        csv_path=tmp_path / "vllm_issues.csv",
        progress=None,
        repo="vllm-project/vllm-omni",
    )

    assert subissue_calls == []


def test_sync_archives_issues_from_removed_topics(monkeypatch, tmp_path):
    topics_file = tmp_path / "topics.yaml"
    db_file = tmp_path / "vllm_issues.sqlite"
    topics_file.write_text(
        """
topics:
  kv_cache:
    description: KV cache behavior.
    queries: []
""".lstrip(),
        encoding="utf-8",
    )
    with daily_update.connect_db(db_file) as conn:
        daily_update.ensure_schema(conn)
        daily_update.upsert_issue(
            conn,
            "model_loading_hf",
            make_issue(321, "Removed topic issue"),
            "2026-05-01T12:00:00Z",
        )

    monkeypatch.setattr(
        daily_update,
        "search_rate_limit_status",
        lambda: {"remaining": 30, "reset": 1770000000},
    )
    monkeypatch.setattr(
        daily_update, "fetch_issue_with_body", lambda issue_number: None
    )
    monkeypatch.setattr(
        daily_update,
        "fetch_issue",
        lambda issue_number: {
            "state": "open",
            "title": "Removed topic issue",
            "url": f"https://github.com/vllm-project/vllm/issues/{issue_number}",
            "labels": [],
            "updatedAt": "2026-05-01T13:00:00Z",
        },
    )
    monkeypatch.setattr(daily_update, "find_linked_prs", lambda issue_number: [])

    daily_update.sync(
        topics_path=topics_file,
        db_path=db_file,
        markdown_path=tmp_path / "VLLM_ISSUES.md",
        csv_path=tmp_path / "vllm_issues.csv",
        progress=None,
    )

    with daily_update.connect_db(db_file) as conn:
        row = fetch_issue(conn, 321)
    assert row["archive_reason"] == "removed_topic"
    assert row["my_status"] == "archived_removed_topic"


def test_render_markdown_groups_active_issues_and_excludes_archived(tmp_path):
    conn = make_conn()
    daily_update.upsert_issue(conn, "kv_cache", make_issue(), "2026-05-01T12:00:00Z")
    daily_update.upsert_issue(
        conn, "kv_cache", make_issue(124, "Closed issue"), "2026-05-01T12:00:00Z"
    )
    conn.execute(
        """
        UPDATE issues
        SET my_status = ?, learning_value = ?, fixability = ?, next_action = ?
        WHERE issue_number = ?
        """,
        ("fixable", "high", "medium", "Reproduce locally", 123),
    )
    daily_update.archive_issue(conn, 124, "linked_pr", "2026-05-03T08:00:00Z")
    output_file = tmp_path / "VLLM_ISSUES.md"

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


def test_render_markdown_orders_topics_by_non_stale_counts_and_hides_stale(tmp_path):
    conn = make_conn()
    scheduler_one = make_issue(201, "Scheduler first issue")
    scheduler_two = make_issue(202, "Scheduler second issue")
    stale_scheduler = make_issue(203, "Stale scheduler issue")
    stale_scheduler["labels"] = [{"name": "bug"}, {"name": "stale"}]
    kv_issue = make_issue(204, "KV cache issue")
    unstale_issue = make_issue(205, "Unstale label issue")
    unstale_issue["labels"] = [{"name": "unstale"}]
    stale_model = make_issue(206, "Only stale model issue")
    stale_model["labels"] = [{"name": "Stale"}]

    daily_update.upsert_issue(
        conn,
        "scheduler_batching",
        scheduler_one,
        "2026-05-01T12:00:00Z",
    )
    daily_update.upsert_issue(
        conn,
        "scheduler_batching",
        scheduler_two,
        "2026-05-01T12:00:00Z",
    )
    daily_update.upsert_issue(
        conn,
        "scheduler_batching",
        stale_scheduler,
        "2026-05-01T12:00:00Z",
    )
    daily_update.upsert_issue(conn, "kv_cache", kv_issue, "2026-05-01T12:00:00Z")
    daily_update.upsert_issue(
        conn,
        "attention_kernels",
        unstale_issue,
        "2026-05-01T12:00:00Z",
    )
    daily_update.upsert_issue(
        conn,
        "model_family_gpt_oss",
        stale_model,
        "2026-05-01T12:00:00Z",
    )
    output_file = tmp_path / "VLLM_ISSUES.md"

    daily_update.render_markdown(
        conn,
        output_file,
        {
            "kv_cache": {"description": "KV cache behavior.", "queries": []},
            "scheduler_batching": {"description": "Scheduler behavior.", "queries": []},
            "attention_kernels": {"description": "Attention behavior.", "queries": []},
            "model_family_gpt_oss": {
                "description": "gpt-oss model-family issues.",
                "queries": [],
            },
        },
        generated_at="2026-05-04T09:00:00Z",
    )

    markdown = output_file.read_text(encoding="utf-8")
    assert "Stale scheduler issue" not in markdown
    assert "Only stale model issue" not in markdown
    assert "Unstale label issue" in markdown
    assert markdown.index("### scheduler_batching") < markdown.index("### kv_cache")
    assert markdown.index("### kv_cache") < markdown.index("### attention_kernels")
    assert markdown.index("### attention_kernels") < markdown.index(
        "### model_family_gpt_oss"
    )


def test_render_markdown_groups_action_queue_by_topic(tmp_path):
    conn = make_conn()
    scheduler_one = make_issue(301, "Scheduler selected issue")
    scheduler_two = make_issue(302, "Scheduler new issue")
    kv_issue = make_issue(303, "KV fixable issue")
    attention_issue = make_issue(304, "Attention issue")
    daily_update.upsert_issue(
        conn,
        "scheduler_batching",
        scheduler_one,
        "2026-05-01T12:00:00Z",
    )
    daily_update.upsert_issue(
        conn,
        "scheduler_batching",
        scheduler_two,
        "2026-05-01T12:00:00Z",
    )
    daily_update.upsert_issue(conn, "kv_cache", kv_issue, "2026-05-01T12:00:00Z")
    daily_update.upsert_issue(
        conn,
        "attention_kernels",
        attention_issue,
        "2026-05-01T12:00:00Z",
    )
    conn.execute(
        "UPDATE issues SET my_status = ?, learning_value = ? WHERE issue_number = ?",
        ("selected", "low", 301),
    )
    conn.execute(
        "UPDATE issues SET my_status = ?, learning_value = ? WHERE issue_number = ?",
        ("new", "high", 302),
    )
    conn.execute(
        "UPDATE issues SET my_status = ?, learning_value = ? WHERE issue_number = ?",
        ("fixable", "high", 303),
    )
    conn.execute(
        "UPDATE issues SET my_status = ?, learning_value = ? WHERE issue_number = ?",
        ("new", "low", 304),
    )
    output_file = tmp_path / "VLLM_ISSUES.md"

    daily_update.render_markdown(
        conn,
        output_file,
        {
            "kv_cache": {"description": "KV cache behavior.", "queries": []},
            "scheduler_batching": {"description": "Scheduler behavior.", "queries": []},
            "attention_kernels": {"description": "Attention behavior.", "queries": []},
        },
        generated_at="2026-05-04T09:00:00Z",
    )

    markdown = output_file.read_text(encoding="utf-8")
    action_queue = markdown.split("## Topics", maxsplit=1)[0]
    assert action_queue.index("### scheduler_batching") < action_queue.index(
        "### kv_cache"
    )
    assert action_queue.index("### kv_cache") < action_queue.index(
        "### attention_kernels"
    )
    scheduler_group = action_queue.split("### scheduler_batching", maxsplit=1)[1].split(
        "### kv_cache", maxsplit=1
    )[0]
    assert "Scheduler selected issue" in scheduler_group
    assert "Scheduler new issue" in scheduler_group
    assert "KV fixable issue" not in scheduler_group


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


def test_sync_search_results_skips_excluded_hardware_labels(monkeypatch):
    conn = make_conn()

    def fake_search_issues(query, limit=10):
        rocm_issue = make_issue(123, "ROCm-only issue")
        rocm_issue["labels"] = [{"name": "bug"}, {"name": "rocm"}]
        amd_issue = make_issue(124, "AMD-only issue")
        amd_issue["labels"] = [{"name": "AMD"}]
        cuda_issue = make_issue(125, "CUDA issue")
        return [rocm_issue, amd_issue, cuda_issue]

    monkeypatch.setattr(daily_update, "search_issues", fake_search_issues)

    daily_update.sync_search_results(
        conn,
        {
            "kv_cache": {
                "description": "KV cache behavior.",
                "queries": ["kv cache -linked:pr"],
            }
        },
        "2026-05-01T12:00:00Z",
    )

    assert fetch_issue(conn, 123) is None
    assert fetch_issue(conn, 124) is None
    assert fetch_issue(conn, 125)["title"] == "CUDA issue"


def test_sync_search_results_skips_obvious_amd_gpu_titles(monkeypatch):
    conn = make_conn()

    def fake_search_issues(query, limit=10):
        mi300_issue = make_issue(123, "[CI Failure]: mi300_1: V1 Core + KV")
        mi300_issue["labels"] = [{"name": "ci-failure"}]
        cuda_issue = make_issue(124, "CUDA issue")
        return [mi300_issue, cuda_issue]

    monkeypatch.setattr(daily_update, "search_issues", fake_search_issues)

    daily_update.sync_search_results(
        conn,
        {
            "kv_cache": {
                "description": "KV cache behavior.",
                "queries": ["kv cache -linked:pr"],
            }
        },
        "2026-05-01T12:00:00Z",
    )

    assert fetch_issue(conn, 123) is None
    assert fetch_issue(conn, 124)["title"] == "CUDA issue"


def test_sync_search_results_skips_assigned_issues(monkeypatch):
    conn = make_conn()

    def fake_search_issues(query, limit=10):
        assigned_issue = make_issue(123, "Assigned issue")
        assigned_issue["assignees"] = [{"login": "maintainer"}]
        unassigned_issue = make_issue(124, "Unassigned issue")
        return [assigned_issue, unassigned_issue]

    monkeypatch.setattr(daily_update, "search_issues", fake_search_issues)

    daily_update.sync_search_results(
        conn,
        {
            "kv_cache": {
                "description": "KV cache behavior.",
                "queries": ["kv cache -linked:pr"],
            }
        },
        "2026-05-01T12:00:00Z",
    )

    assert fetch_issue(conn, 123) is None
    assert fetch_issue(conn, 124)["title"] == "Unassigned issue"


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
            db_path=tmp_path / "vllm_issues.sqlite",
            markdown_path=tmp_path / "VLLM_ISSUES.md",
            csv_path=tmp_path / "vllm_issues.csv",
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


def test_search_issues_uses_configured_repo(monkeypatch):
    commands = []

    def fake_run_gh_json(command):
        commands.append(command)
        return []

    monkeypatch.setattr(daily_update, "run_gh_json", fake_run_gh_json)

    daily_update.search_issues(
        "qwen3 omni -linked:pr",
        repo="vllm-project/vllm-omni",
    )

    assert commands[0][commands[0].index("--repo") + 1] == "vllm-project/vllm-omni"


def test_export_csv_writes_all_schema_columns(tmp_path):
    conn = make_conn()
    daily_update.upsert_issue(conn, "kv_cache", make_issue(), "2026-05-01T12:00:00Z")
    output_file = tmp_path / "vllm_issues.csv"

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
            "assignees": "",
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


def test_export_csv_excludes_linked_pr_archives(tmp_path):
    conn = make_conn()
    daily_update.upsert_issue(
        conn,
        "attention_kernels",
        make_issue(34444, "[RFC]: Decoupled Attention/FFN Parallelism"),
        "2026-05-01T12:00:00Z",
    )
    daily_update.archive_issue(conn, 34444, "linked_pr", "2026-05-02T12:00:00Z")
    daily_update.upsert_issue(
        conn,
        "kv_cache",
        make_issue(34555, "Active issue"),
        "2026-05-01T12:00:00Z",
    )
    output_file = tmp_path / "vllm_issues.csv"

    daily_update.export_csv(conn, output_file)

    with output_file.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert [row["issue_number"] for row in rows] == ["34555"]


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


def test_run_gh_json_retries_transient_github_failures(monkeypatch):
    calls = []
    sleeps = []

    def flaky_run(*args, **kwargs):
        calls.append(args[0])
        if len(calls) == 1:
            raise subprocess.CalledProcessError(
                returncode=1,
                cmd=["gh", "issue", "view", "40544"],
                stderr="HTTP 504: 504 Gateway Timeout (https://api.github.com/graphql)",
            )
        return subprocess.CompletedProcess(
            args=["gh", "issue", "view", "40544"],
            returncode=0,
            stdout='{"state":"open"}',
            stderr="",
        )

    monkeypatch.setattr(daily_update.subprocess, "run", flaky_run)
    monkeypatch.setattr(daily_update.time, "sleep", sleeps.append)

    payload = daily_update.run_gh_json(["issue", "view", "40544"])

    assert payload == {"state": "open"}
    assert len(calls) == 2
    assert sleeps == [5.0]


def test_run_gh_json_reports_unresolvable_issue(monkeypatch):
    def fail_run(*args, **kwargs):
        raise subprocess.CalledProcessError(
            returncode=1,
            cmd=["gh", "issue", "view", "41144"],
            stderr=(
                "GraphQL: Could not resolve to an issue or pull request with "
                "the number of 41144. (repository.issue)"
            ),
        )

    monkeypatch.setattr(daily_update.subprocess, "run", fail_run)

    with pytest.raises(daily_update.GhNotFoundError):
        daily_update.run_gh_json(["issue", "view", "41144"])


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
