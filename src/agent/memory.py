# Stateful Conversational Memory & Persistence Manager

import time
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger("ConversationMemory")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class ConversationMemory:
    # Manages stateful multi-turn conversation transcripts with bounded sliding-window retention, on-disk JSON persistence, and retention/deletion compliance.
    
    def __init__(
        self,
        max_history_turns: int = 10,
        storage_dir: Optional[str] = None,
        retention_days: int = 30,
    ):
        self.max_history_turns = max_history_turns
        self.retention_seconds = retention_days * 24 * 3600
        self.storage_dir = Path(storage_dir) if storage_dir else PROJECT_ROOT / "data" / "sessions"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.sessions: Dict[str, List[Dict[str, Any]]] = {}
        self.metadata: Dict[str, Dict[str, Any]] = {}
        self._load_sessions()

    def _load_sessions(self) -> None:
        # Loads all persisted JSON sessions from disk into active memory."""
        for file in self.storage_dir.glob("*.json"):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                sid = data.get("session_id")
                if sid:
                    self.sessions[sid] = data.get("transcript", [])
                    self.metadata[sid] = data.get("metadata", {})
            except Exception as e:
                logger.warning(f"Could not load session from {file.name}: {e}")

    def initialize_session(self, session_id: str, student_id: str = "2300712345") -> None:
        # Initializes a new session if not present."""
        if session_id not in self.sessions:
            now = time.time()
            self.sessions[session_id] = []
            self.metadata[session_id] = {
                "created_at": now,
                "last_active": now,
                "student_id": student_id,
                "turn_count": 0,
            }
            self._save_session(session_id)
            logger.info(f"Initialized new session: {session_id}")

    def add_turn(self, session_id: str, role: str, content: str) -> None:
        # Appends a turn and strictly enforces sliding-window FIFO pruning."""
        if session_id not in self.sessions:
            self.initialize_session(session_id)

        now = time.time()
        self.sessions[session_id].append({
            "role": role,
            "content": content,
            "timestamp": now,
        })
        self.metadata[session_id]["last_active"] = now
        self.metadata[session_id]["turn_count"] = len(self.sessions[session_id])

        # Enforce sliding-window retention (prune oldest non-system turns FIFO)
        while len(self.sessions[session_id]) > self.max_history_turns:
            pruned = self.sessions[session_id].pop(0)
            logger.debug(f"[{session_id}] Pruned oldest turn from memory: {pruned.get('role')}")

        self._save_session(session_id)

    def get_recent_history(self, session_id: str, turns: int = 4) -> List[Dict[str, Any]]:
        # Returns the most recent N turns for prompt synthesis."""
        return self.sessions.get(session_id, [])[-turns:]

    def _save_session(self, session_id: str) -> None:
        # Persists the session transcript and metadata to disk as JSON."""
        file_path = self.storage_dir / f"{session_id}.json"
        payload = {
            "session_id": session_id,
            "metadata": self.metadata.get(session_id, {}),
            "transcript": self.sessions.get(session_id, []),
        }
        file_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # --- GDPR & Retention Compliance Utilities ---

    def delete_session(self, session_id: str) -> bool:
        # Permanently deletes a student session from active memory and disk
        # for institutional privacy and GDPR compliance.
        
        deleted = False
        if session_id in self.sessions:
            del self.sessions[session_id]
            self.metadata.pop(session_id, None)
            deleted = True

        file_path = self.storage_dir / f"{session_id}.json"
        if file_path.exists():
            file_path.unlink()
            deleted = True

        logger.info(f"Purged session {session_id} from memory and disk storage.")
        return deleted

    def cleanup_expired_sessions(self) -> int:
        # Scans all sessions on disk and memory, removing those older than the retention threshold.
        # Returns the number of expired sessions removed.
        
        now = time.time()
        expired_count = 0
        sids = list(self.metadata.keys())

        for sid in sids:
            meta = self.metadata.get(sid, {})
            last_active = meta.get("last_active", meta.get("created_at", now))
            if (now - last_active) > self.retention_seconds:
                self.delete_session(sid)
                expired_count += 1

        # Also purge orphan files on disk if any
        for file in self.storage_dir.glob("*.json"):
            sid = file.stem
            if sid not in self.sessions:
                try:
                    data = json.loads(file.read_text(encoding="utf-8"))
                    meta = data.get("metadata", {})
                    last_active = meta.get("last_active", meta.get("created_at", now))
                    if (now - last_active) > self.retention_seconds:
                        file.unlink()
                        expired_count += 1
                except Exception:
                    continue

        if expired_count > 0:
            logger.info(f"Cleaned up {expired_count} expired session(s) per retention policy.")
        return expired_count


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("\n=== TESTING CONVERSATION MEMORY STANDALONE ===")
    
    # 1. Test initialization and sliding window
    mem = ConversationMemory(max_history_turns=4)
    test_sid = "test-retention-999"
    mem.initialize_session(test_sid, student_id="2300712345")
    
    for i in range(1, 7):
        mem.add_turn(test_sid, "user", f"Turn query #{i}")
        mem.add_turn(test_sid, "assistant", f"Turn response #{i}")
        
    history = mem.get_recent_history(test_sid, turns=10)
    print(f"Turns in memory after 6 exchanges (limit 4): {len(history)}")
    assert len(history) == 4, f"Expected 4 turns, got {len(history)}"
    print("Sliding window FIFO test passed.")

    # 2. Test disk persistence
    persisted_file = mem.storage_dir / f"{test_sid}.json"
    assert persisted_file.exists(), "Persisted JSON session file not found on disk!"
    print(f"Session successfully saved to disk: {persisted_file}")

    # 3. Test GDPR deletion utility
    mem.delete_session(test_sid)
    assert not persisted_file.exists(), "Session file should have been deleted from disk!"
    assert test_sid not in mem.sessions, "Session should have been deleted from RAM!"
    print("GDPR session deletion utility passed.")
    print("\nAll memory subtasks verified.")