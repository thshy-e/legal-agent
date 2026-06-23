import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from legal_ai_agent.config.settings import BASE_DIR


DEFAULT_STATE_PATH = BASE_DIR / "db" / "conversation_state.json"
MAX_TURNS_PER_SESSION = 12


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean_session_id(session_id: str | None) -> str:
    cleaned = str(session_id or "user_web").strip()
    return cleaned or "user_web"


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except TypeError:
        return str(value)


def _has_value(value: Any) -> bool:
    if value is False:
        return True
    return value not in (None, "", 0, [], {})


class ConversationStateStore:
    """Persistent local state for session-scoped agent collaboration."""

    def __init__(self, path: str | Path = DEFAULT_STATE_PATH, max_turns: int = MAX_TURNS_PER_SESSION):
        self.path = Path(path)
        self.max_turns = max_turns
        self._lock = RLock()
        self._state: dict[str, dict[str, Any]] | None = None

    def _empty_session(self) -> dict[str, Any]:
        return {
            "facts": {},
            "last_route": "",
            "last_calculation": {},
            "last_answer_preview": "",
            "turns": [],
            "updated_at": "",
        }

    def _load_unlocked(self) -> dict[str, dict[str, Any]]:
        if self._state is not None:
            return self._state

        if not self.path.exists():
            self._state = {}
            return self._state

        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = {}

        self._state = loaded if isinstance(loaded, dict) else {}
        return self._state

    def _save_unlocked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = json.dumps(self._state or {}, ensure_ascii=False, indent=2)
        tmp_path.write_text(payload, encoding="utf-8")
        os.replace(tmp_path, self.path)

    def get(self, session_id: str | None) -> dict[str, Any]:
        with self._lock:
            state = self._load_unlocked()
            session = state.get(_clean_session_id(session_id), self._empty_session())
            return deepcopy(session)

    def update_facts(self, session_id: str | None, facts: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            state = self._load_unlocked()
            key = _clean_session_id(session_id)
            session = state.setdefault(key, self._empty_session())
            session_facts = session.setdefault("facts", {})
            for fact_key, value in (facts or {}).items():
                if _has_value(value):
                    session_facts[fact_key] = _json_safe(value)
            session["updated_at"] = _utc_now_iso()
            self._save_unlocked()
            return deepcopy(session)

    def record_turn(
        self,
        session_id: str | None,
        *,
        query: str,
        route: str,
        answer_preview: str,
        facts: dict[str, Any] | None = None,
        calculation: dict[str, Any] | None = None,
        structured_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            state = self._load_unlocked()
            key = _clean_session_id(session_id)
            session = state.setdefault(key, self._empty_session())
            session_facts = session.setdefault("facts", {})

            for fact_key, value in (facts or {}).items():
                if _has_value(value):
                    session_facts[fact_key] = _json_safe(value)

            if calculation and calculation.get("show"):
                session["last_calculation"] = _json_safe(calculation)

            session["last_route"] = route or ""
            session["last_answer_preview"] = str(answer_preview or "")[:240]
            session["updated_at"] = _utc_now_iso()

            turns = session.setdefault("turns", [])
            turns.append(
                {
                    "query": str(query or "")[:500],
                    "route": route or "",
                    "answer_preview": str(answer_preview or "")[:240],
                    "calculation_status": (calculation or {}).get("status", ""),
                    "structured_summary": _json_safe(structured_summary or {}),
                    "created_at": session["updated_at"],
                }
            )
            if len(turns) > self.max_turns:
                del turns[:-self.max_turns]

            self._save_unlocked()
            return deepcopy(session)

    def reset(self, session_id: str | None) -> None:
        with self._lock:
            state = self._load_unlocked()
            state.pop(_clean_session_id(session_id), None)
            self._save_unlocked()

    def build_summary(self, session_id: str | None, state: dict[str, Any] | None = None) -> dict[str, Any]:
        current = deepcopy(state) if state is not None else self.get(session_id)
        facts = current.get("facts") or {}
        last_calculation = current.get("last_calculation") or {}
        turns = current.get("turns") or []
        return {
            "session_id": _clean_session_id(session_id),
            "is_continuation": bool(turns or facts or last_calculation),
            "turn_count": len(turns),
            "last_route": current.get("last_route") or "",
            "known_facts": facts,
            "last_calculation": last_calculation,
            "last_answer_preview": current.get("last_answer_preview") or "",
            "used_previous_calculation": False,
        }


conversation_store = ConversationStateStore()
