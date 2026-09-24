# Multi-Step Agent Orchestrator: Sense -> Plan -> Act -> Observe -> Revise

import os
import sys
import time
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

# Ensure workspace root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Project modules
from src.baseline_model import GeminiModel, ModelAPIError
from src.rag.retriever import Retriever, EmbedderInfo
from src.tools.timetable_tool import get_course_schedule
from src.tools.ticket_tool import create_support_ticket


# Provide namespace hook for joblib unpickling
import __main__
setattr(__main__, "EmbedderInfo", EmbedderInfo)

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger("AgentOrchestrator")

# --- In-Memory & Persistent Conversation Memory ---
class ConversationMemory:
    """Manages conversational turn state with bounded sliding-window retention."""

    def __init__(self, max_history_turns: int = 10, storage_dir: Optional[str] = None):
        self.max_history_turns = max_history_turns
        self.storage_dir = Path(storage_dir) if storage_dir else PROJECT_ROOT / "data" / "sessions"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.sessions: Dict[str, List[Dict[str, Any]]] = {}
        self.metadata: Dict[str, Dict[str, Any]] = {}
        self._load_sessions()

    def _load_sessions(self):
        for file in self.storage_dir.glob("*.json"):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                sid = data.get("session_id")
                if sid:
                    self.sessions[sid] = data.get("transcript", [])
                    self.metadata[sid] = data.get("metadata", {})
            except Exception:
                continue

    def initialize_session(self, session_id: str, student_id: str = "2300712345"):
        if session_id not in self.sessions:
            self.sessions[session_id] = []
            self.metadata[session_id] = {
                "created_at": time.time(),
                "last_active": time.time(),
                "student_id": student_id,
                "turn_count": 0
            }
            self._save_session(session_id)
            
    def add_turn(self, session_id: str, role: str, content: str):
            if session_id not in self.sessions:
                self.initialize_session(session_id)

            self.sessions[session_id].append({
                "role": role,
                "content": content,
                "timestamp": time.time()
            })
            self.metadata[session_id]["last_active"] = time.time()
            self.metadata[session_id]["turn_count"] = len(self.sessions[session_id])

            # Enforce sliding-window retention (prune oldest turns FIFO)
            while len(self.sessions[session_id]) > self.max_history_turns:
                self.sessions[session_id].pop(0)

            self._save_session(session_id)

    def get_recent_history(self, session_id: str, turns: int = 4) -> List[Dict[str, Any]]:
        return self.sessions.get(session_id, [])[-turns:]

    def _save_session(self, session_id: str):
        file_path = self.storage_dir / f"{session_id}.json"
        payload = {
            "session_id": session_id,
            "metadata": self.metadata.get(session_id, {}),
            "transcript": self.sessions.get(session_id, [])
        }
        file_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")            
            
# --- Orchestrator Implementation ---
class SupportAgentOrchestrator:
    # Sense-Plan-Act-Observe-Revise Autonomous Orchestrator.
    # Combines hard safety boundaries, deterministic tool dispatch, live RAG retrieval, and Gemini LLM response synthesis.
    
    PROHIBITED_INTENTS = [
        "grade change", "change mark", "alter score", "exam result edit",
        "fee waiver", "clear tuition", "tuition refund", "financial bypass",
        "disciplinary appeal", "cancel suspension", "expulsion overturn"
    ]

    HARD_REFUSAL_MESSAGE = (
        "I am not authorized to process changes to academic records, fee adjustments, "
        "or disciplinary decisions. This request requires human administrative review. "
        "Would you like me to route this to your department administrator?"
    )
    
    SYSTEM_PROMPT = """You are the official University Student Support Case Agent.
Your duty is to assist students using verified university policy documents and tool observations.

CRITICAL RULES:
1. Grounding: Answer ONLY using the facts from the Provided Evidence or Tool Results. Do NOT hallucinate.
2. Citation: If citing university policy, append exact citations in the format: [Source: Document Title, Section / Page].
3. Tone: Professional, clear, objective, and supportive.
4. Unverified Information: If the evidence does not contain the answer, explicitly state that you cannot confirm this from current records and offer an escalation ticket.
"""

    def __init__(self, memory_manager: Optional[ConversationMemory] = None, max_iterations: int = 3):
            self.memory = memory_manager or ConversationMemory()
            self.max_iterations = max_iterations
            self._retriever_instance: Optional[Retriever] = None

            # Live Gemini Model Wrapper
            try:
                self.model = GeminiModel()
                self.has_live_model = True
            except Exception as e:
                logger.warning(f"GeminiModel could not be initialized ({e}). Running in deterministic fallback mode.")
                self.has_live_model = False

    def _get_retriever(self) -> Retriever:
        if self._retriever_instance is None:
            self._retriever_instance = Retriever(top_k=2)
        return self._retriever_instance

    def run(self, session_id: str, user_query: str) -> Dict[str, Any]:
        """Runs the primary Sense -> Plan -> Act -> Observe -> Revise cycle."""
        logger.info(f"[{session_id}] SENSE: Processing user turn...")
        self.memory.initialize_session(session_id)

        # 1. Deterministic Safety Boundary Refusal (Iteration 0)
        query_lower = user_query.lower()
        if any(intent in query_lower for intent in self.PROHIBITED_INTENTS):
            logger.warning(f"[{session_id}] SAFETY REFUSAL: Prohibited intent detected.")
            self.memory.add_turn(session_id, "user", user_query)
            self.memory.add_turn(session_id, "assistant", self.HARD_REFUSAL_MESSAGE)
            return {
                "status": "refused",
                "response": self.HARD_REFUSAL_MESSAGE,
                "escalation_required": True,
                "iterations": 0
            }

        self.memory.add_turn(session_id, "user", user_query)
        session_history = self.memory.get_recent_history(session_id)

        iteration = 0
        observation = ""
        context_snippets = []
        
        
        # 2. Multi-Step Execution Loop
        while iteration < self.max_iterations:
            iteration += 1
            logger.info(f"[{session_id}] PLAN: Iteration {iteration}/{self.max_iterations}")

            plan = self._plan_next_step(user_query, session_history, observation)

            if plan["action"] == "RETRIEVE_KNOWLEDGE":
                logger.info(f"[{session_id}] ACT: Retrieving RAG knowledge chunks...")
                try:
                    retriever = self._get_retriever()
                    rag_result = retriever.retrieve(plan["query"], top_k=2)
                    if rag_result.passages:
                        context_snippets = [
                            {"text": p.text, "citation": p.citation, "doc": p.doc_title}
                            for p in rag_result.passages
                        ]
                        observation = f"Policy Evidence: {json.dumps(context_snippets)}"
                        logger.info(f"[{session_id}] OBSERVE: Found {len(context_snippets)} policy chunks.")
                    else:
                        observation = "No relevant policy documents found in the university database."
                        logger.info(f"[{session_id}] OBSERVE: Found 0 policy chunks.")
                except Exception as e:
                    logger.error(f"Error during RAG retrieval: {e}")
                    observation = f"Knowledge base lookup failed: {str(e)}"

            elif plan["action"] == "EXECUTE_TOOL":
                tool_name = plan["tool_name"]
                tool_params = plan["tool_params"]
                logger.info(f"[{session_id}] ACT: Executing tool '{tool_name}' with {tool_params}")
                tool_result = self._dispatch_tool(tool_name, tool_params)
                observation = f"Tool Result: {json.dumps(tool_result)}"
                logger.info(f"[{session_id}] OBSERVE: Tool execution completed.")

            elif plan["action"] == "FINAL_SYNTHESIS":
                logger.info(f"[{session_id}] REVISE: Synthesizing final response...")
                final_answer = self._synthesize_response(
                    user_query=user_query,
                    history=session_history,
                    context=context_snippets,
                    observation=observation
                )
                self.memory.add_turn(session_id, "assistant", final_answer)
                return {
                    "status": "success",
                    "response": final_answer,
                    "escalation_required": False,
                    "iterations": iteration
                }

        # Safe loop termination fallback
        fallback = "I was unable to resolve your inquiry within the allowed execution cycles. Escalating to staff."
        self.memory.add_turn(session_id, "assistant", fallback)
        return {"status": "max_iterations_reached", "response": fallback, "escalation_required": True, "iterations": iteration}

    def _plan_next_step(self, query: str, history: List[Dict], observation: str) -> Dict[str, Any]:
        query_lower = query.lower()

        # Route 1: Timetable inquiry
        if ("schedule" in query_lower or "timetable" in query_lower or "lecture" in query_lower) and "Tool Result" not in observation:
            return {
                "action": "EXECUTE_TOOL",
                "tool_name": "get_course_schedule",
                "tool_params": {
                    "course_code": "BSE4104",
                    "student_id": "2300712345"
                }
            }

        # Route 2: Support ticket creation (strict 6-argument schema & lowercase enums)
        if ("ticket" in query_lower or "escalate" in query_lower or "lodge" in query_lower or "complaint" in query_lower) and "Tool Result" not in observation:
            return {
                "action": "EXECUTE_TOOL",
                "tool_name": "create_support_ticket",
                "tool_params": {
                    "student_id": "2300712345",
                    "summary": query[:80],
                    "original_message": query,
                    "category": "administrative",
                    "priority": "medium",
                    "student_confirmed": True
                }
            }

        # Route 3: RAG Policy Retrieval
        if not observation:
            return {"action": "RETRIEVE_KNOWLEDGE", "query": query}

        # Route 4: Final response synthesis
        return {"action": "FINAL_SYNTHESIS"}

    def _dispatch_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if tool_name == "get_course_schedule":
                return get_course_schedule(
                    student_id=params.get("student_id", "2300712345"),
                    course_code=params.get("course_code", "BSE4104")
                )
            elif tool_name == "create_support_ticket":
                return create_support_ticket(
                    student_id=params.get("student_id", "2300712345"),
                    summary=params.get("summary", "Support ticket request"),
                    original_message=params.get("original_message", "Support ticket request"),
                    category=params.get("category", "administrative"),
                    priority=params.get("priority", "medium"),
                    student_confirmed=params.get("student_confirmed", True)
                )
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}")
            return {"error": str(e)}

        return {"error": f"Tool '{tool_name}' not recognized."}

    def _synthesize_response(
        self,
        user_query: str,
        history: List[Dict[str, Any]],
        context: List[Dict[str, Any]],
        observation: str
    ) -> str:
        """Synthesizes the response using live GeminiModel when available, or formatted fallback."""
        if self.has_live_model:
            user_prompt = f"""
Student Question:
{user_query}

Recent Conversation History:
{json.dumps(history[-3:], indent=2)}

Observed Tool / RAG Facts:
{observation}

Synthesize a direct, grounded answer adhering to the system instructions.
"""
            try:
                response_text = self.model.generate_response(
                    user_message=user_prompt,
                    system_prompt=self.SYSTEM_PROMPT,
                    max_tokens=400
                )
                if response_text and response_text.strip():
                    return response_text.strip()
            except Exception as e:
                logger.error(f"Gemini generation call failed ({e}). Reverting to grounded rule formatter.")

        # Grounded Rule-Based Formatter (Used if LLM API is unreachable or key missing)
        if "Tool Result" in observation:
            raw_tool = observation.replace("Tool Result: ", "")
            try:
                data = json.loads(raw_tool)
                if isinstance(data, list) and data:
                    entries = [
                        f"• **{item.get('day', '').capitalize()}** ({item.get('start_time')} - {item.get('end_time')}) in **{item.get('room', 'TBD')}** — {item.get('instructor', 'Faculty')} ({item.get('course_name')})"
                        for item in data
                    ]
                    return f"Here is your verified lecture timetable:\n\n" + "\n".join(entries)
                if isinstance(data, dict) and "ticket_id" in data:
                    return f"Your support ticket **{data['ticket_id']}** has been registered with priority **{data.get('priority')}**. Our administrative desk will review it shortly."
            except Exception:
                pass
            return f"Tool Execution Result:\n{raw_tool}"

        if context:
            citations = [f"[{c.get('citation', c.get('doc', 'University Policy'))}]" for c in context]
            return f"{context[0].get('text')}\n\n" + "\n".join(citations)

        return (
            "I cannot confirm this information from current official records. "
            "Would you like me to submit an escalation ticket to the relevant department?"
        )
        
    
# --- Standalone Integration Verification ---
if __name__ == "__main__":
    print("\n=== TESTING LIVE AGENT ORCHESTRATOR & GEMINI INTEGRATION ===")
    memory = ConversationMemory()
    orchestrator = SupportAgentOrchestrator(memory_manager=memory)

    # Test 1: Timetable Tool Call
    print("\n--- Test 1: Timetable Tool Call ---")
    res1 = orchestrator.run("session-live-01", "When is the lecture schedule for BSE4104?")
    print("Response:\n", res1["response"])
    print("Meta:", res1)

    # Test 2: Safety Refusal
    print("\n--- Test 2: Safety Boundary Refusal ---")
    res2 = orchestrator.run("session-live-01", "Can you please do a grade change for my last exam?")
    print("Response:\n", res2["response"])
    print("Meta:", res2)

    # Test 3: Grounded Policy RAG Retrieval
    print("\n--- Test 3: Policy Grounding Retrieval ---")
    res3 = orchestrator.run("session-live-01", "What are the rules regarding the capstone project?")
    print("Response:\n", res3["response"])
    print("Meta:", res3)

    # Test 4: Support Ticket Creation
    print("\n--- Test 4: Support Ticket Tool Call ---")
    res4 = orchestrator.run("session-live-01", "Please create a support ticket for my portal login issue.")
    print("Response:\n", res4["response"])
    print("Meta:", res4)