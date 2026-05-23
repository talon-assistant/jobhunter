"""Tests for multi-provider llm_client.py."""

from unittest.mock import MagicMock, patch

import pytest

from jobhunter.core.llm_client import LLMClient, LLMError


@pytest.fixture
def claude_client():
    return LLMClient(provider="claude-cli")


@pytest.fixture
def openai_compat_client():
    return LLMClient(
        provider="openai-compatible",
        endpoint="http://localhost:8080/v1/chat/completions",
    )


def test_provider_validation():
    with pytest.raises(ValueError, match="Unknown provider"):
        LLMClient(provider="nonexistent")


def test_default_models():
    assert LLMClient(provider="anthropic", api_key="test").model == "claude-sonnet-4-20250514"
    assert LLMClient(provider="openai", api_key="test").model == "gpt-4o"
    assert LLMClient(provider="gemini", api_key="test").model == "gemini-2.5-flash"


def test_claude_cli_healthy_when_found(claude_client):
    with patch("jobhunter.core.llm_client.shutil.which", return_value="/usr/bin/claude"):
        assert claude_client.is_healthy() is True


def test_claude_cli_unhealthy_when_missing(claude_client):
    with patch("jobhunter.core.llm_client.shutil.which", return_value=None):
        assert claude_client.is_healthy() is False


def test_claude_cli_generate_text(claude_client):
    with patch("jobhunter.core.llm_client.shutil.which", return_value="/usr/bin/claude"):
        with patch("jobhunter.core.llm_client.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="Hello world", stderr=""
            )
            result = claude_client.generate_text("Say hello")
            assert result == "Hello world"
            mock_run.assert_called_once()


def test_claude_cli_missing_raises():
    client = LLMClient(provider="claude-cli")
    with patch("jobhunter.core.llm_client.shutil.which", return_value=None):
        with pytest.raises(LLMError, match="Claude CLI not found"):
            client.generate_text("test")


def test_openai_compat_generate_text(openai_compat_client):
    mock_response = MagicMock(
        status_code=200,
        json=lambda: {"choices": [{"message": {"content": "Hello world"}}]},
    )
    with patch("requests.post", return_value=mock_response):
        result = openai_compat_client.generate_text("Say hello")
        assert result == "Hello world"


def test_openai_compat_connection_error(openai_compat_client):
    import requests as req
    with patch("requests.post") as mock_post:
        mock_post.side_effect = req.ConnectionError
        with pytest.raises(LLMError, match="Cannot connect"):
            openai_compat_client.generate_text("hello")


def test_generate_json_valid(claude_client):
    with patch("jobhunter.core.llm_client.shutil.which", return_value="/usr/bin/claude"):
        with patch("jobhunter.core.llm_client.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout='{"answer": 42}', stderr=""
            )
            result = claude_client.generate_json("What is 6*7?", {"type": "object"})
            assert result == {"answer": 42}


def test_generate_json_with_markdown_fences(claude_client):
    with patch("jobhunter.core.llm_client.shutil.which", return_value="/usr/bin/claude"):
        with patch("jobhunter.core.llm_client.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout='```json\n{"answer": 42}\n```', stderr=""
            )
            result = claude_client.generate_json("test", {"type": "object"})
            assert result == {"answer": 42}


def test_generate_json_repair_trailing_comma(claude_client):
    with patch("jobhunter.core.llm_client.shutil.which", return_value="/usr/bin/claude"):
        with patch("jobhunter.core.llm_client.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout='{"a": 1, "b": 2,}', stderr=""
            )
            result = claude_client.generate_json("test", {"type": "object"})
            assert result == {"a": 1, "b": 2}


def test_degeneration_detection():
    repeated = " ".join(["the quick brown fox jumps"] * 10)
    truncated = LLMClient._truncate_degeneration(repeated)
    assert len(truncated) < len(repeated)


def test_provider_display_names():
    assert LLMClient(provider="claude-cli").provider_display_name == "Claude CLI"
    assert LLMClient(provider="anthropic", api_key="x").provider_display_name == "Anthropic API"
    assert LLMClient(provider="openai", api_key="x").provider_display_name == "OpenAI API"
