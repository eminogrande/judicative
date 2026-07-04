#!/usr/bin/env python3
"""Unit tests for cloud-only model tournament guardrails."""

from bench.model_tournament import validate_cloud_models, validate_ollama_cloud_base_url


def test_validate_cloud_models_accepts_cloud_names():
    validate_cloud_models(["glm-5.2:cloud", "kimi-k2.7-code:cloud", "model-cloud"])


def test_validate_cloud_models_accepts_cloud_catalog_names():
    validate_cloud_models(["glm-5.2", "kimi-k2.7-code"], {"glm-5.2", "kimi-k2.7-code"})


def test_validate_cloud_models_rejects_local_names():
    try:
        validate_cloud_models(["glm-5.2:cloud", "qwen3.6:27b"])
    except ValueError as exc:
        assert "qwen3.6:27b" in str(exc)
    else:
        raise AssertionError("expected non-cloud model to be rejected")


def test_validate_ollama_cloud_base_url_accepts_cloud_api():
    validate_ollama_cloud_base_url("https://ollama.com")


def test_validate_ollama_cloud_base_url_rejects_local_api():
    try:
        validate_ollama_cloud_base_url("http://localhost:11434/v1")
    except ValueError as exc:
        assert "non-cloud Ollama base URL" in str(exc)
    else:
        raise AssertionError("expected local Ollama API to be rejected")


if __name__ == "__main__":
    tests = [
        test_validate_cloud_models_accepts_cloud_names,
        test_validate_cloud_models_accepts_cloud_catalog_names,
        test_validate_cloud_models_rejects_local_names,
        test_validate_ollama_cloud_base_url_accepts_cloud_api,
        test_validate_ollama_cloud_base_url_rejects_local_api,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
