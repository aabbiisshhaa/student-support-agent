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
    """Render the active FSM lifecycle badge row cleanly using HTML badges."""
    step_lower = (current_step or "sense").lower().strip()
    
    # Map any execution status aliases to standard FSM phases
    status_map = {
        "idle": "sense",
        "running": "act",
        "completed": "stop",
        "stopped": "stop",
        "error": "stop",
    }
    active_step = status_map.get(step_lower, step_lower)

    badges = [
        ("sense", "🔍 SENSE"),
        ("plan", "📋 PLAN"),
        ("act", "⚡ ACT"),
        ("observe", "👁 OBSERVE"),
        ("replan", "🔄 REPLAN"),
        ("stop", "🛑 STOP"),
    ]

    badge_html_items = []
    for step_key, badge_label in badges:
        if step_key == active_step:
            # Bright blue pill badge for the active phase
            badge_html_items.append(
                f'<span style="background-color: #1d4ed8; color: #ffffff; padding: 4px 10px; '
                f'border-radius: 9999px; font-weight: 600; font-size: 0.78rem; '
                f'display: inline-block; margin-right: 6px; box-shadow: 0 0 8px rgba(29, 78, 216, 0.4);">'
                f'{badge_label}</span>'
            )
        else:
            # Muted gray pill badge for inactive phases
            badge_html_items.append(
                f'<span style="background-color: #1e293b; color: #94a3b8; padding: 4px 10px; '
                f'border-radius: 9999px; font-weight: 500; font-size: 0.78rem; '
                f'display: inline-block; margin-right: 6px; border: 1px solid #334155;">'
                f'{badge_label}</span>'
            )

    row_container = f'<div style="display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 12px;">{"".join(badge_html_items)}</div>'
    st.markdown(row_container, unsafe_allow_html=True)            

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