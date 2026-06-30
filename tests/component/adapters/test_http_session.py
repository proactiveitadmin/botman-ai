import requests

from src.adapters.http_session import (
    close_pooled_sessions,
    get_pooled_session,
    session_key_for_url,
)


def test_session_key_for_url_normalizes_host_and_prefix():
    assert session_key_for_url("https://Example.COM/path", prefix="pg") == "pg:example.com"
    assert session_key_for_url("example.com/api") == "example.com"


def test_get_pooled_session_reuses_session_for_same_key():
    close_pooled_sessions()
    try:
        first = get_pooled_session("pinecone:example")
        second = get_pooled_session("pinecone:example")
        other = get_pooled_session("perfectgym:example")

        assert isinstance(first, requests.Session)
        assert first is second
        assert other is not first
    finally:
        close_pooled_sessions()


def test_close_pooled_sessions_clears_current_thread_cache():
    close_pooled_sessions()
    first = get_pooled_session("jira:example")
    close_pooled_sessions()
    second = get_pooled_session("jira:example")
    try:
        assert second is not first
    finally:
        close_pooled_sessions()
