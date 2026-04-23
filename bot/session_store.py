from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, replace

from core.gui_service import (
    PaginatedValidationRows,
    ValidationCandidate,
    default_selected_candidate_ids,
    paginate_validation_candidates,
    toggle_validation_candidate,
)


@dataclass(frozen=True)
class BotSession:
    session_id: str
    chat_id: int
    analysis_text: str
    candidates: tuple[ValidationCandidate, ...]
    selected_candidate_ids: set[str]
    page: int
    expires_at: float


class SessionStore:
    def __init__(self, page_size: int = 5, ttl_seconds: int = 1800) -> None:
        self.page_size = page_size
        self.ttl_seconds = ttl_seconds
        self._sessions: dict[str, BotSession] = {}

    def create(
        self,
        chat_id: int,
        analysis_text: str,
        candidates: tuple[ValidationCandidate, ...],
    ) -> BotSession:
        session = BotSession(
            session_id=uuid.uuid4().hex[:8],
            chat_id=chat_id,
            analysis_text=analysis_text,
            candidates=candidates,
            selected_candidate_ids=default_selected_candidate_ids(candidates),
            page=1,
            expires_at=time.time() + self.ttl_seconds,
        )
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> BotSession | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.expires_at < time.time():
            self._sessions.pop(session_id, None)
            return None
        return session

    def toggle(self, session_id: str, candidate_id: str) -> BotSession:
        session = self._require(session_id)
        updated = replace(
            session,
            selected_candidate_ids=toggle_validation_candidate(
                session.candidates,
                session.selected_candidate_ids,
                candidate_id,
            ),
            expires_at=time.time() + self.ttl_seconds,
        )
        self._sessions[session_id] = updated
        return updated

    def toggle_index(self, session_id: str, candidate_index: int) -> BotSession:
        session = self._require(session_id)
        if not (0 <= candidate_index < len(session.candidates)):
            raise IndexError(candidate_index)
        return self.toggle(session_id, session.candidates[candidate_index].candidate_id)

    def page(self, session_id: str, page_number: int) -> PaginatedValidationRows:
        session = self._require(session_id)
        updated = replace(session, page=page_number, expires_at=time.time() + self.ttl_seconds)
        self._sessions[session_id] = updated
        return paginate_validation_candidates(
            updated.candidates,
            updated.selected_candidate_ids,
            page=updated.page,
            page_size=self.page_size,
        )

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def _require(self, session_id: str) -> BotSession:
        session = self.get(session_id)
        if session is None:
            raise KeyError(f"Unknown session: {session_id}")
        return session
