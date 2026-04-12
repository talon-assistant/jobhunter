"""Tests for llm_client.py."""

from unittest.mock import MagicMock, patch

import pytest

from jobhunter.core.llm_client import LLMClient, LLMError


@pytest.fixture
def client():
    return LLMClient(endpoint="http://localhost:8080/v1/chat/completions")


def test_is_healthy_success(client):
    with patch("jobhunter.core.llm_client.requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"status": "ok"})
        assert client.is_healthy() is True


def test_is_healthy_failure(client):
    import requests as req
    with patch("jobhunter.core.llm_client.requests.get") as mock_get:
        mock_get.side_effect = req.ConnectionError
        assert client.is_healthy() is False


def test_generate_text(client):
    mock_response = MagicMock(
        status_code=200,
        json=lambda: {
            "choices": [{"message": {"content": "Hello world"}}]
        },
    )
    with patch("jobhunter.core.llm_client.requests.post", return_value=mock_response):
        result = client.generate_text("Say hello")
        assert result == "Hello world"


def test_generate_json_valid(client):
    mock_response = MagicMock(
        status_code=200,
        json=lambda: {
            "choices": [{"message": {"content": '{"answer": 42}'}}]
        },
    )
    with patch("jobhunter.core.llm_client.requests.post", return_value=mock_response):
        result = client.generate_json("What is 6*7?", {"type": "object"})
        assert result == {"answer": 42}


def test_generate_json_with_markdown_fences(client):
    mock_response = MagicMock(
        status_code=200,
        json=lambda: {
            "choices": [{"message": {"content": '```json\n{"answer": 42}\n```'}}]
        },
    )
    with patch("jobhunter.core.llm_client.requests.post", return_value=mock_response):
        result = client.generate_json("What is 6*7?", {"type": "object"})
        assert result == {"answer": 42}


def test_generate_json_repair_trailing_comma(client):
    mock_response = MagicMock(
        status_code=200,
        json=lambda: {
            "choices": [{"message": {"content": '{"a": 1, "b": 2,}'}}]
        },
    )
    with patch("jobhunter.core.llm_client.requests.post", return_value=mock_response):
        result = client.generate_json("test", {"type": "object"})
        assert result == {"a": 1, "b": 2}


def test_connection_error(client):
    import requests as req
    with patch("jobhunter.core.llm_client.requests.post") as mock_post:
        mock_post.side_effect = req.ConnectionError
        with pytest.raises(LLMError, match="Cannot connect"):
            client.generate_text("hello")


def test_degeneration_detection(client):
    repeated = " ".join(["the quick brown fox jumps"] * 10)
    truncated = client._truncate_degeneration(repeated)
    assert len(truncated) < len(repeated)
