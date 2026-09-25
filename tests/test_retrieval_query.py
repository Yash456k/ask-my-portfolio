from __future__ import annotations

from app.retrieval_query import build_retrieval_query


def test_retrieval_query_uses_only_recent_user_history() -> None:
    history = [
        ("user", "old user context"),
        ("assistant", "untrusted assistant claim"),
        ("user", "AIVID Techvision"),
        ("assistant", "another assistant claim"),
        ("user", "database scale"),
    ]

    query = build_retrieval_query("What did he do there?", history)

    assert "old user context" not in query
    assert "untrusted assistant claim" not in query
    assert "another assistant claim" not in query
    assert "AIVID Techvision" in query
    assert "database scale" in query
    assert query.endswith("Current question:\nWhat did he do there?")


def test_retrieval_query_can_disable_history() -> None:
    assert (
        build_retrieval_query(
            "Current question",
            [("user", "prior context")],
            use_history=False,
        )
        == "Current question"
    )


def test_questions_about_this_project_mean_the_chat_itself() -> None:
    from app.retrieval_query import SELF_REFERENCE_NOTE

    assert build_retrieval_query("What is this project?").endswith(SELF_REFERENCE_NOTE)
    assert SELF_REFERENCE_NOTE in build_retrieval_query("tell me about this site", [("user", "hi")])
    assert build_retrieval_query("What projects has Yash built?") == "What projects has Yash built?"
