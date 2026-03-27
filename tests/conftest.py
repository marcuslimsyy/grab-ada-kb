"""
Shared pytest fixtures.

app.py runs Streamlit code at module level (st.title, st.session_state, etc.).
We mock the entire streamlit module before any import so tests don't require
a running Streamlit server.
"""
import sys
from unittest.mock import MagicMock, patch
import pytest


# ---------------------------------------------------------------------------
# Mock streamlit at import time so app.py can be imported in tests
# ---------------------------------------------------------------------------

class _SessionState(dict):
    """Dict that also supports attribute-style access (st.session_state.foo = bar)."""
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)

    def __setattr__(self, key, value):
        self[key] = value

    def __delattr__(self, key):
        try:
            del self[key]
        except KeyError:
            raise AttributeError(key)


def _make_streamlit_mock():
    mock = MagicMock()
    mock.session_state = _SessionState()
    mock.sidebar = MagicMock()
    mock.sidebar.text_input.return_value = ""
    mock.sidebar.selectbox.return_value = "passenger"
    mock.sidebar.checkbox.return_value = True
    # st.columns(n) must return an iterable of n mocks
    mock.columns.side_effect = lambda n: [MagicMock() for _ in range(n)]
    return mock


_st_mock = _make_streamlit_mock()
sys.modules["streamlit"] = _st_mock


# ---------------------------------------------------------------------------
# Import app after mocking (order matters)
# ---------------------------------------------------------------------------
import app  # noqa: E402  (must come after mock)


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Clear the sliding-window deque before every test."""
    app._rate_limiter.clear()
    yield
    app._rate_limiter.clear()


@pytest.fixture
def mock_st_container():
    """Return a MagicMock that behaves like a Streamlit container."""
    container = MagicMock()
    container.container.return_value.__enter__ = MagicMock(return_value=MagicMock())
    container.container.return_value.__exit__ = MagicMock(return_value=False)
    return container


@pytest.fixture
def sample_article():
    return {
        "id": "test-001",
        "name": "Test Article",
        "body": "Some content",
        "external_id": "test-001",
        "language": "en",
        "url": "https://help.grab.com/articles/test-001",
        "knowledge_source_id": "ks-abc123",
        "external_updated": "2026-03-27T00:00:00.000000Z",
    }
