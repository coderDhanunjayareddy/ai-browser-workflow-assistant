from benchmark.phase0_gate import MAX_TASKS, MIN_TASKS, build_manifest


def test_phase0_suite_is_frozen_and_valid():
    manifest = build_manifest()
    assert manifest["errors"] == []
    assert MIN_TASKS <= manifest["task_count"] <= MAX_TASKS
    assert len(manifest["dataset_sha256"]) == 64


def test_phase0_suite_has_broad_execution_coverage():
    manifest = build_manifest()
    categories = set(manifest["categories"])
    assert {"SEARCH", "FORM_SUBMIT", "UPLOAD", "DOWNLOAD", "CROSS_SITE"} <= categories
    assert manifest["fixture_count"] >= 10
    assert manifest["auth_required_count"] >= 4


def test_phase0_task_ids_are_unique():
    manifest = build_manifest()
    task_ids = [task["task_id"] for task in manifest["tasks"]]
    assert len(task_ids) == len(set(task_ids))

