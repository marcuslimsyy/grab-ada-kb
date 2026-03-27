"""
Tests for create_ada_article_with_status() retry + backoff logic.
"""
from unittest.mock import MagicMock, patch, call
import pytest
import requests

import app


INSTANCE = "test-instance"
API_KEY = "test-api-key"


def _mock_response(status_code, json_data=None, headers=None):
    """Helper to build a mock requests.Response."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.headers = headers or {}
    mock.json.return_value = json_data or {"id": "created-123"}
    mock.text = str(json_data or "")
    return mock


class TestCreateArticleSuccess:

    def test_returns_true_on_201(self, mock_st_container, sample_article):
        with patch("app.requests.post", return_value=_mock_response(201)):
            with patch("app.time.sleep"):
                success, result = app.create_ada_article_with_status(
                    INSTANCE, API_KEY, sample_article, mock_st_container, 1, 1
                )
        assert success is True

    def test_returns_true_on_200(self, mock_st_container, sample_article):
        with patch("app.requests.post", return_value=_mock_response(200)):
            with patch("app.time.sleep"):
                success, _ = app.create_ada_article_with_status(
                    INSTANCE, API_KEY, sample_article, mock_st_container, 1, 1
                )
        assert success is True

    def test_no_retry_on_success(self, mock_st_container, sample_article):
        with patch("app.requests.post", return_value=_mock_response(201)) as mock_post:
            with patch("app.time.sleep"):
                app.create_ada_article_with_status(
                    INSTANCE, API_KEY, sample_article, mock_st_container, 1, 1
                )
        assert mock_post.call_count == 1


class TestCreateArticleValidation:

    def test_fails_on_missing_instance(self, mock_st_container, sample_article):
        success, msg = app.create_ada_article_with_status(
            "", API_KEY, sample_article, mock_st_container, 1, 1
        )
        assert success is False
        assert "Missing" in msg

    def test_fails_on_missing_api_key(self, mock_st_container, sample_article):
        success, msg = app.create_ada_article_with_status(
            INSTANCE, "", sample_article, mock_st_container, 1, 1
        )
        assert success is False

    def test_fails_on_invalid_api_key_chars(self, mock_st_container, sample_article):
        success, msg = app.create_ada_article_with_status(
            INSTANCE, "\xff\xfe", sample_article, mock_st_container, 1, 1
        )
        assert success is False
        assert "invalid" in msg.lower()


class TestCreateArticleRetryOn429:

    def test_retries_on_429_then_succeeds(self, mock_st_container, sample_article):
        responses = [
            _mock_response(429),
            _mock_response(201),
        ]
        with patch("app.requests.post", side_effect=responses) as mock_post:
            with patch("app.time.sleep"):
                success, _ = app.create_ada_article_with_status(
                    INSTANCE, API_KEY, sample_article, mock_st_container, 1, 1
                )
        assert success is True
        assert mock_post.call_count == 2

    def test_exhausts_retries_on_repeated_429(self, mock_st_container, sample_article):
        with patch("app.requests.post", return_value=_mock_response(429)):
            with patch("app.time.sleep"):
                success, msg = app.create_ada_article_with_status(
                    INSTANCE, API_KEY, sample_article, mock_st_container, 1, 1
                )
        assert success is False
        assert "429" in str(msg)

    def test_respects_retry_after_header(self, mock_st_container, sample_article):
        responses = [
            _mock_response(429, headers={"Retry-After": "5"}),
            _mock_response(201),
        ]
        with patch("app.requests.post", side_effect=responses):
            with patch("app.time.sleep") as mock_sleep:
                app.create_ada_article_with_status(
                    INSTANCE, API_KEY, sample_article, mock_st_container, 1, 1
                )
        # First sleep should be 5s (from Retry-After header)
        first_sleep = mock_sleep.call_args_list[0][0][0]
        assert first_sleep == 5.0

    def test_retry_after_date_string_falls_back_to_backoff(self, mock_st_container, sample_article):
        """Retry-After as HTTP date string should not crash - falls back to backoff."""
        responses = [
            _mock_response(429, headers={"Retry-After": "Fri, 28 Mar 2026 00:00:00 GMT"}),
            _mock_response(201),
        ]
        with patch("app.requests.post", side_effect=responses):
            with patch("app.time.sleep") as mock_sleep:
                success, _ = app.create_ada_article_with_status(
                    INSTANCE, API_KEY, sample_article, mock_st_container, 1, 1
                )
        assert success is True
        # Should have slept with backoff (not crashed)
        assert mock_sleep.called


class TestCreateArticleRetryOn5xx:

    @pytest.mark.parametrize("status_code", [500, 502, 503, 504])
    def test_retries_on_server_error(self, status_code, mock_st_container, sample_article):
        responses = [_mock_response(status_code), _mock_response(201)]
        with patch("app.requests.post", side_effect=responses) as mock_post:
            with patch("app.time.sleep"):
                success, _ = app.create_ada_article_with_status(
                    INSTANCE, API_KEY, sample_article, mock_st_container, 1, 1
                )
        assert success is True
        assert mock_post.call_count == 2

    def test_max_retries_on_500(self, mock_st_container, sample_article):
        with patch("app.requests.post", return_value=_mock_response(500)):
            with patch("app.time.sleep"):
                success, msg = app.create_ada_article_with_status(
                    INSTANCE, API_KEY, sample_article, mock_st_container, 1, 1
                )
        assert success is False

    def test_retry_count_equals_max_retries_plus_one(self, mock_st_container, sample_article):
        with patch("app.requests.post", return_value=_mock_response(500)) as mock_post:
            with patch("app.time.sleep"):
                app.create_ada_article_with_status(
                    INSTANCE, API_KEY, sample_article, mock_st_container, 1, 1
                )
        assert mock_post.call_count == app.MAX_RETRIES + 1


class TestCreateArticleNoRetryOn4xx:

    @pytest.mark.parametrize("status_code", [400, 401, 403, 404])
    def test_no_retry_on_client_error(self, status_code, mock_st_container, sample_article):
        with patch("app.requests.post", return_value=_mock_response(status_code)) as mock_post:
            with patch("app.time.sleep"):
                success, _ = app.create_ada_article_with_status(
                    INSTANCE, API_KEY, sample_article, mock_st_container, 1, 1
                )
        assert success is False
        assert mock_post.call_count == 1  # no retries


class TestCreateArticleRetryOnTimeout:

    def test_retries_on_timeout_then_succeeds(self, mock_st_container, sample_article):
        with patch("app.requests.post", side_effect=[
            requests.exceptions.Timeout(),
            _mock_response(201),
        ]) as mock_post:
            with patch("app.time.sleep"):
                success, _ = app.create_ada_article_with_status(
                    INSTANCE, API_KEY, sample_article, mock_st_container, 1, 1
                )
        assert success is True
        assert mock_post.call_count == 2

    def test_fails_after_max_timeouts(self, mock_st_container, sample_article):
        with patch("app.requests.post", side_effect=requests.exceptions.Timeout()):
            with patch("app.time.sleep"):
                success, msg = app.create_ada_article_with_status(
                    INSTANCE, API_KEY, sample_article, mock_st_container, 1, 1
                )
        assert success is False
        assert "timed out" in msg.lower()


class TestBackoffTiming:

    def test_backoff_increases_with_each_attempt(self, mock_st_container, sample_article):
        """Sleep durations should increase across retries (exponential)."""
        with patch("app.requests.post", return_value=_mock_response(500)):
            with patch("app.time.sleep") as mock_sleep:
                with patch("app.random.uniform", return_value=0.0):  # remove jitter
                    app.create_ada_article_with_status(
                        INSTANCE, API_KEY, sample_article, mock_st_container, 1, 1
                    )
        sleeps = [c[0][0] for c in mock_sleep.call_args_list]
        # With jitter=0: attempt 0 → 1s, attempt 1 → 2s, attempt 2 → 4s
        assert len(sleeps) == app.MAX_RETRIES
        assert sleeps[0] < sleeps[1] < sleeps[2]

    def test_backoff_capped_at_max_delay(self, mock_st_container, sample_article):
        """Sleep never exceeds RETRY_MAX_DELAY even with high attempt count."""
        original_max_retries = app.MAX_RETRIES
        app.MAX_RETRIES = 10  # force many retries
        try:
            with patch("app.requests.post", return_value=_mock_response(500)):
                with patch("app.time.sleep") as mock_sleep:
                    with patch("app.random.uniform", return_value=0.0):
                        app.create_ada_article_with_status(
                            INSTANCE, API_KEY, sample_article, mock_st_container, 1, 1
                        )
            sleeps = [c[0][0] for c in mock_sleep.call_args_list]
            assert all(s <= app.RETRY_MAX_DELAY for s in sleeps)
        finally:
            app.MAX_RETRIES = original_max_retries
