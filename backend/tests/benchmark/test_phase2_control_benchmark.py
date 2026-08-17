from benchmark.phase2_control_benchmark import run


def test_hybrid_trusted_input_eliminates_controlled_no_effects():
    report = run(headless=True)
    assert report["surface_count"] == 4
    assert report["synthetic_no_effect_count"] == 4
    assert report["hybrid_no_effect_count"] == 0
    assert report["relative_no_effect_reduction"] == 1.0
    assert {item["surface"] for item in report["results"]} == {
        "controlled_input", "iframe", "popup", "complex_widget",
    }
