"""Main Streamlit application shell for the Student Support Case Agent.

Provides a dual-mode interface:
1. Student Portal View: Clean, distraction-free student workflow.
2. Evaluation & Demo Mode: Split-screen inspector showing FSM state badges,
   execution traces, token utilization, and memory snapshots in real time.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure project root is available in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from src.agent.memory import SessionMemoryManager
from src.agent.orchestrator import DEFAULT_STUDENT_ID, SupportAgentOrchestrator
from src.ui.components.chat import append_message, render_chat_history, render_chat_input
from src.ui.components.inspector import render_inspector_panel
from src.ui.components.scenarios import Scenario, render_scenario_runner

DEFAULT_ACTIVE_STUDENT = "2300712345"


def initialize_session() -> None:
    """Initialize persistent session state attributes."""
    if "memory" not in st.session_state:
        st.session_state["memory"] = SessionMemoryManager()
    if "student_id" not in st.session_state:
        st.session_state["student_id"] = DEFAULT_ACTIVE_STUDENT
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
    if "orchestrator" not in st.session_state:
        # Re-use orchestrator instance to maintain HTTP keep-alive connection pool
        st.session_state["orchestrator"] = SupportAgentOrchestrator(
            memory_manager=st.session_state["memory"]
        )


def execute_agent_turn(user_query: str) -> None:
    """Execute a single agentic turn, streaming telemetry live into session state."""
    append_message("user", user_query)

    events: list[dict] = []

    def on_event(ev: dict) -> None:
        events.append(ev)

    orchestrator: SupportAgentOrchestrator = st.session_state["orchestrator"]

    try:
        with st.spinner("Agent executing bounded loop (Sense-Plan-Act-Observe)..."):
            result = orchestrator.run(
                session_id=st.session_state["session_token"],
                user_query=user_query,
                student_id=st.session_state["student_id"],
                on_event=on_event,
            )

        response_text = result.get("response", "No response generated.")
        if result.get("escalation_required"):
            response_text += "\n\n_Note: This inquiry has been routed to human support staff for review._"

        append_message("assistant", response_text)
        st.session_state["latest_agent_state"] = result.get("state_snapshot") or {}
    except Exception as exc:
        append_message("assistant", f"⚠️ System Exception: {exc}")
    finally:
        st.session_state["telemetry_events"].extend(events)


def handle_scenario_launch(scenario: Scenario) -> None:
    """Queue a scenario execution asynchronously through session state."""
    st.session_state["student_id"] = scenario.student_id
    st.session_state["pending_prompt"] = scenario.prompt
    st.rerun()


def main() -> None:
    st.set_page_config(
        page_title="Makerere Student Support Case Agent",
        page_icon="🎓",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    initialize_session()

    # =========================================================================
    # SIDEBAR: Portal Controls & Evaluation Scenarios
    # =========================================================================
    with st.sidebar:
        st.title("🎓 Student Portal")
        st.caption("Makerere University • CoCIS / BSE4104")
        st.markdown("---")

        # UI View Mode Selector
        view_mode = st.radio(
            "Interface Mode",
            options=["Student Portal View", "Evaluation & Demo Mode"],
            index=1,
            help="Toggle between the student-facing view and the split-screen observability inspector.",
        )

        st.markdown("---")
        st.markdown("#### 👤 Student Identity")
        student_id_input = st.text_input(
            "Active Student ID",
            value=st.session_state["student_id"],
            help="10-digit university student identifier.",
        )
        if student_id_input != st.session_state["student_id"]:
            st.session_state["student_id"] = student_id_input

        st.caption(f"**Session:** `{st.session_state['session_token']}`")

        col_reset, col_clear = st.columns(2)
        with col_reset:
            if st.button("🔄 New Session", use_container_width=True):
                st.session_state["session_token"] = st.session_state["memory"].create_session(
                    student_ref=st.session_state["student_id"]
                )
                st.session_state["messages"] = []
                st.session_state["telemetry_events"] = []
                st.session_state["latest_agent_state"] = None
                st.session_state["pending_prompt"] = None
                st.rerun()

        with col_clear:
            if st.button("🧹 Clear Chat", use_container_width=True):
                st.session_state["messages"] = []
                st.rerun()

        st.markdown("---")
        render_scenario_runner(on_select=handle_scenario_launch)

    # Process queued prompt from scenario selection
    if st.session_state.get("pending_prompt"):
        prompt_to_run = st.session_state["pending_prompt"]
        st.session_state["pending_prompt"] = None
        execute_agent_turn(prompt_to_run)
        st.rerun()

    # =========================================================================
    # MAIN WORKSPACE
    # =========================================================================
    if view_mode == "Evaluation & Demo Mode":
        # Split-screen: Left = Student Chat, Right = Orchestrator Inspector
        chat_col, inspector_col = st.columns([1, 1], gap="medium")

        with chat_col:
            st.subheader("💬 Student Portal Dialogue", divider="blue")
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
        # Full-width single-column Student Portal View
        _, center_col, _ = st.columns([1, 4, 1])
        with center_col:
            st.subheader("🎓 Makerere Academic Advisory Desk", divider="blue")
            st.info(
                "Welcome to the Academic Advisory Portal. You can check your weekly timetable, "
                "ask about academic policies (retakes, pass marks, appeals), or request human staff escalation.",
                icon="ℹ️",
            )
            render_chat_history()
            user_input = render_chat_input()
            if user_input:
                execute_agent_turn(user_input)
                st.rerun()


if __name__ == "__main__":
    main()