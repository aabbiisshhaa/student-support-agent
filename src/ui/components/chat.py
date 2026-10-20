"""Conversational message container for the Streamlit UI."""

from __future__ import annotations

from typing import Any
import streamlit as st


def render_chat_history() -> None:
    """Render all turns currently stored in session state."""
    messages = st.session_state.get("messages", [])
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        with st.chat_message(role):
            st.markdown(content)


def append_message(role: str, content: str) -> None:
    """Append a message to the active session state and render it."""
    if "messages" not in st.session_state:
        st.session_state["messages"] = []
    st.session_state["messages"].append({"role": role, "content": content})


def render_chat_input() -> str | None:
    """Render the bottom chat input box."""
    return st.chat_input("Ask about timetable, policies, retakes, or tickets...")