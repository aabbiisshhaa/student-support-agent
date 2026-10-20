"""Main Streamlit application shell for the Student Support Case Agent."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from src.agent.memory import SessionMemoryManager
from src.agent.orchestrator import DEFAULT_STUDENT_ID, SupportAgentOrchestrator
from src.ui.components.chat import append_message, render_chat_history, render_chat_input
from src.ui.components.inspector import render_inspector_panel
from src.ui.components.scenarios import Scenario, render_scenario_runner

ACTIVE_STUDENT_ID = "2300712345"


def initialize_session() -> None:
    """Set up initial session state keys."""
    if "memory" not in st.session_state:
        st.session_state["memory"] = SessionMemoryManager()
    if "student_id" not in st.session_state:
        st.session_state["student_id"] = ACTIVE_STUDENT_ID
    if "session_token" not in st.session_state:
        st.session_state["session_token"] = st.session_state["memory"].create_session(
            student_ref=st.session_state["student_id"]
        )
    if "messages" not in st.session_state:
        st.session_state["messages"] = []
    if "telemetry_events" not in st.session_state:
        st.session_state["telemetry_events"] = []
    if "latest_agent_state" not in st.session_state:
        st.session_state["latest_agent_state"] = None
    if "pending_prompt" not in st.session_state:
        st.session_state["pending_prompt"] = None


def execute_agent_turn(user_query: str) -> None:
    """Execute a single turn with the orchestrator, capturing traces live."""
    append_message("user", user_query)

    events: list[dict] = []

    def on_event(ev: dict) -> None:
        events.append(ev)

    memory: SessionMemoryManager = st.session_state["memory"]
    orchestrator = SupportAgentOrchestrator(memory_manager=memory)

    try:
        with st.spinner("Agent reasoning in progress..."):
            result = orchestrator.run(
                session_id=st.session_state["session_token"],
                user_query=user_query,
                student_id=st.session_state["student_id"],
                on_event=on_event,
            )

        response_text = result.get("response", "No response generated.")
        if result.get("escalation_required"):
            response_text += "\n\n_Note: This issue has been flagged for human staff review._"

        append_message("assistant", response_text)
        st.session_state["latest_agent_state"] = result.get("state_snapshot") or {}
    except Exception as exc:
        append_message("assistant", f"⚠️ Error executing query: {exc}")
    finally:
        st.session_state["telemetry_events"].extend(events)


def handle_scenario_launch(scenario: Scenario) -> None:
    """Queue scenario execution via session state."""
    st.session_state["student_id"] = scenario.student_id
    st.session_state["pending_prompt"] = scenario.prompt
    st.rerun()


def main() -> None:
    st.set_page_config(
        page_title="University Student Support Agent",
        page_icon="🎓",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    initialize_session()

    # --- Sidebar Controls ---
    st.sidebar.title("🎓 Student Portal")
    st.sidebar.markdown("---")

    student_id_input = st.sidebar.text_input(
        "Student ID",
        value=st.session_state["student_id"],
        help="Unique university registration/student ID",
    )
    if student_id_input != st.session_state["student_id"]:
        st.session_state["student_id"] = student_id_input

    st.sidebar.caption(f"**Session Token:** `{st.session_state['session_token']}`")

    if st.sidebar.button("🔄 New Session", use_container_width=True):
        st.session_state["session_token"] = st.session_state["memory"].create_session(
            student_ref=st.session_state["student_id"]
        )
        st.session_state["messages"] = []
        st.session_state["telemetry_events"] = []
        st.session_state["latest_agent_state"] = None
        st.session_state["pending_prompt"] = None
        st.rerun()

    st.sidebar.markdown("---")
    render_scenario_runner(on_select=handle_scenario_launch)

    # Process queued prompt from scenario selection
    if st.session_state.get("pending_prompt"):
        prompt_to_run = st.session_state["pending_prompt"]
        st.session_state["pending_prompt"] = None
        execute_agent_turn(prompt_to_run)
        st.rerun()

    # --- Main Split Screen Layout ---
    show_inspector = st.sidebar.toggle("🔬 Show Orchestrator Inspector", value=True)

    if show_inspector:
        chat_col, inspector_col = st.columns([1, 1], gap="medium")
        with chat_col:
            st.subheader("💬 Student Support Chat", divider="blue")
            render_chat_history()
            user_input = render_chat_input()
            if user_input:
                execute_agent_turn(user_input)
                st.rerun()

        with inspector_col:
            render_inspector_panel(
                events=st.session_state["telemetry_events"],
                latest_state=st.session_state["latest_agent_state"],
            )
    else:
        st.subheader("💬 Student Support Chat", divider="blue")
        render_chat_history()
        user_input = render_chat_input()
        if user_input:
            execute_agent_turn(user_input)
            st.rerun()


if __name__ == "__main__":
    main()