"""
FINDINGS SUMMARY TESTS: the write-up is complete, honest and traceable.
"""

import importlib.util
import re

import pytest

from conftest import ROOT

SUMMARY = ROOT / "output" / "findings_summary.md"


@pytest.fixture(scope="module")
def findings(db, config):
    spec = importlib.util.spec_from_file_location("write_summary", ROOT / "src" / "write_summary.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {f["department"]: f for f in module.build_findings(db, config)}


def test_summary_written_and_labeled_synthetic(pipeline_run):
    text = SUMMARY.read_text(encoding="utf-8")
    assert "SYNTHETIC DATA" in text


def test_every_department_covered(findings, config):
    assert set(findings) == {d["name"] for d in config["departments"]}


def test_every_action_comes_from_the_playbook(findings, config):
    allowed = {a for actions in config["playbook"].values() for a in actions}
    for f in findings.values():
        for action in f["actions"]:
            assert action in allowed, f"{f['department']}: action not in playbook: {action}"


def test_status_matches_colors(findings):
    for f in findings.values():
        colors = list(f["colors"].values())
        if "Red" in colors:
            assert f["status"] == "Needs action", f["department"]
        elif colors == ["Green"] * 4:
            assert f["status"] == "On track", f["department"]
        else:
            assert f["status"] == "Watch", f["department"]


def test_every_non_green_measure_is_explained(findings):
    # Any measure that isn't green must be mentioned in a problem or watch sentence.
    words = {"Reach": ["training"], "Readiness": ["favorable", "survey", "confidence"],
             "Adoption": ["heavy users", "minimum", "prompts"], "Outcomes": ["baseline"]}
    for f in findings.values():
        text = " ".join(f["problems"] + f["watch"]).lower()
        for measure, color in f["colors"].items():
            if color != "Green":
                assert any(w in text for w in words[measure]), f"{f['department']}: {measure} not explained"


def test_every_sentence_quotes_a_number(findings):
    for f in findings.values():
        for sentence in f["problems"] + f["watch"] + f["strengths"]:
            assert re.search(r"\d", sentence), f"{f['department']}: no number in: {sentence}"


# Planted-pattern checks (synthetic data only): the rules find each department's story.
@pytest.mark.parametrize("dept, phrase", [
    ("Branch Operations", "Training ran late"),
    ("Branch Operations", "answered the latest survey"),
    ("Branch Operations", "zero days"),
    ("Lending", "Box-checking"),
    ("Lending", "Confidence is low"),
    ("Deposit Operations", "Use isn't turning into results"),
])
def test_planted_story_detected(findings, dept, phrase):
    assert any(phrase in p for p in findings[dept]["problems"]), f"{dept}: missing '{phrase}'"


def test_on_track_department_has_no_problems(findings):
    assert findings["Contact Center"]["status"] == "On track"
    assert findings["Contact Center"]["problems"] == []
