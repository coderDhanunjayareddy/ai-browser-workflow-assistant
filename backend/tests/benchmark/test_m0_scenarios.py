"""M0 unit tests — scenario dataset well-formedness + website profiles."""
from benchmark import m0_scenarios, website_profiles
from benchmark.m0_models import Difficulty


def test_27_scenarios():
    tasks = m0_scenarios.build_m0_scenarios()
    assert len(tasks) == 27


def test_ids_unique_and_kebab():
    tasks = m0_scenarios.build_m0_scenarios()
    ids = [t.task_id for t in tasks]
    assert len(ids) == len(set(ids))
    assert all("__" in tid for tid in ids)


def test_every_task_valid():
    for t in m0_scenarios.build_m0_scenarios():
        assert t.goal and t.start_url
        assert t.success_criteria, f"{t.task_id} has no success criteria"
        assert t.max_steps > 0 and t.timeout_ms > 0
        assert t.difficulty in (Difficulty.simple, Difficulty.medium, Difficulty.complex)
        assert isinstance(t.to_dict(), dict)


def test_fixture_tasks_have_placeholder():
    for t in m0_scenarios.build_m0_scenarios():
        if t.is_fixture:
            assert "{fixture_base}" in t.start_url


def test_tier_distribution_reasonable():
    tasks = m0_scenarios.build_m0_scenarios()
    simple = sum(1 for t in tasks if t.difficulty == Difficulty.simple)
    medium = sum(1 for t in tasks if t.difficulty == Difficulty.medium)
    complex_ = sum(1 for t in tasks if t.difficulty == Difficulty.complex)
    assert simple >= 8 and medium >= 8 and complex_ >= 5


def test_expected_failures_documented():
    tasks = m0_scenarios.build_m0_scenarios()
    ef = {t.task_id for t in tasks if t.expect_failure}
    assert "cross_site__amazon_search_github_compare" in ef
    assert "sheets_google_com__enter_data" in ef


def test_every_task_site_has_profile():
    for t in m0_scenarios.build_m0_scenarios():
        assert website_profiles.get_profile(t.site_id) is not None, t.site_id


def test_auth_tasks_have_state_file():
    for t in m0_scenarios.build_m0_scenarios():
        prof = website_profiles.get_profile(t.site_id)
        if prof and prof.auth_required:
            assert t.preconditions.auth_required
            assert t.preconditions.auth_state_file
