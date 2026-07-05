#!/usr/bin/env python3
"""Unit tests for OpenRouter panel helper functions."""

from openrouter_panel import extract_json_object, submission_labels, validate_panel_response


def test_extract_json_object_from_fenced_text():
    text = '```json\n{"judge_id": "x", "reviews": {}, "ranking": []}\n```'
    assert extract_json_object(text)["judge_id"] == "x"


def test_extract_json_object_from_extra_text():
    text = 'Here is the verdict:\n{"judge_id": "x", "reviews": {}, "ranking": []}\nThanks'
    assert extract_json_object(text)["judge_id"] == "x"


def test_submission_labels():
    packet = "# Packet\n\n### SUBMISSION-B\ncode\n\n### SUBMISSION-A\ncode\n"
    assert submission_labels(packet) == ["SUBMISSION-A", "SUBMISSION-B"]


def test_validate_panel_response_accepts_complete_response():
    labels = ["SUBMISSION-A", "SUBMISSION-B"]
    data = {
        "judge_id": "model",
        "reviews": {
            "SUBMISSION-A": {"holistic_score": 80, "verdict": "PASS"},
            "SUBMISSION-B": {"holistic_score": 30, "verdict": "FAIL"},
        },
        "ranking": ["SUBMISSION-A", "SUBMISSION-B"],
    }
    validate_panel_response(data, labels)


def test_validate_panel_response_rejects_missing_review():
    labels = ["SUBMISSION-A", "SUBMISSION-B"]
    data = {
        "judge_id": "model",
        "reviews": {"SUBMISSION-A": {"holistic_score": 80, "verdict": "PASS"}},
        "ranking": ["SUBMISSION-A", "SUBMISSION-B"],
    }
    try:
        validate_panel_response(data, labels)
    except ValueError as exc:
        assert "SUBMISSION-B" in str(exc)
    else:
        raise AssertionError("expected ValueError")


if __name__ == "__main__":
    tests = [
        test_extract_json_object_from_fenced_text,
        test_extract_json_object_from_extra_text,
        test_submission_labels,
        test_validate_panel_response_accepts_complete_response,
        test_validate_panel_response_rejects_missing_review,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
