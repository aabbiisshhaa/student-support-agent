"""Real-time inspection view displaying FSM phase badges, telemetry snapshots, and guardrail alerts."""

from __future__ import annotations

import json
from typing import Any
import streamlit as st


FSM_BADGES = {
    "sense": "🔍 SENSE",
    "plan": "📋 PLAN",
    "act": "⚡ ACT",
    "observe": "👁 OBSERVE",
    "replan": "🔄 REPLAN",
    "stop": "🛑 STOP",
}


def render_fsm_badge_row(current_step: str) -> None:
    """Render the active FSM lifecycle badge row."""
    step_lower = current_step.lower() if current_step else "sense"
    cols = st.columns(6)
    steps = ["sense", "plan", "act", "observe", "replan", "stop"]
    
    for col, step in zip(cols, steps):
        badge_text = FSM_BADGES[step]
        if step == step_lower:
            col.markdown(f"**`:blue-background[{badge_text}]`**")
        else:
            col.markdown(f"<span style='color: gray;'>{badge_text}</span>", unsafe_allow_html=True)


def render_inspector_panel(events: list[dict[str, Any]], latest_state: dict[str, Any] | None) -> None:
    """Render the inspection side panel."""
    st.subheader("🔬 Orchestrator Inspector", divider="rainbow")

    current_step = "sense"
    if latest_state and "current_step" in latest_state:
        current_step = str(latest_state["current_step"]).lower()
    elif events:
        for ev in reversed(events):
            if ev.get("event") == "state_transition":
                current_step = ev.get("to_step", "sense").lower()
                break

    st.markdown("**Active FSM Phase:**")
    render_fsm_badge_row(current_step)

    # Metrics Row
    col_iter, col_replans, col_events = st.columns(3)
    iter_count = latest_state.get("iteration_count", 0) if latest_state else 0
    replan_count = sum(1 for e in events if e.get("to_step") == "replan")
    col_iter.metric("Iterations", f"{iter_count} / 5")
    col_replans.metric("Replans", f"{replan_count} / 2")
    col_events.metric("Telemetry Events", len(events))

    # Guardrail Intercept Alerts
    intercepts = [
        e for e in events
        if e.get("event") in {"output_guardrail_check", "guardrail_intercept", "safety_refusal"}
    ]
    if intercepts:
        st.markdown("### 🛡️ Guardrail Telemetry")
        for idx, inter in enumerate(intercepts):
            ev_name = inter.get("event")
            if ev_name == "output_guardrail_check":
                if inter.get("hallucinated_citations") or inter.get("leaked"):
                    st.error(f" **Output Sanitized:** Flagged citations: `{inter.get('hallucinated_citations')}`")
                else:
                    st.success(" **Output Verified:** Grounded citations verified; no prompt leakage.")
            else:
                st.warning(f" **Guardrail Halt:** Rule `{inter.get('rule', 'BLOCKED')}` triggered.")

    # Expandable Snapshots & Traces
    st.markdown("### Real-time Traces & State Snapshots")
    if not events:
        st.info("No telemetry traces recorded yet. Submit a message or run a scenario to inspect execution.")
        return

    for i, event in enumerate(reversed(events)):
        ev_type = event.get("event", "event")
        header = f"{len(events) - i}. [{ev_type.upper()}]"
        
        if ev_type == "state_transition":
            header += f" {event.get('from_step')} ➔ {event.get('to_step')}"
        elif ev_type in {"tool_start", "tool_call", "tool_end"}:
            header += f" {event.get('tool', 'tool')}"

        with st.expander(header, expanded=(i == 0)):
            st.json(event)