from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from pathlib import Path

from local_vllm_dashboard.upload import UploadPreview

SESSION_TTL_SECONDS = 3600


@dataclass
class UploadSession:
    preview: UploadPreview
    created_at: float


class UploadSessionStore:
    def __init__(self, staging_root: Path) -> None:
        self.staging_root = staging_root
        self._sessions: dict[str, UploadSession] = {}

    def create(self, preview: UploadPreview) -> str:
        self.cleanup()
        token = secrets.token_urlsafe(24)
        self._sessions[token] = UploadSession(preview=preview, created_at=time.time())
        return token

    def pop(self, token: str) -> UploadPreview | None:
        self.cleanup()
        session = self._sessions.pop(token, None)
        return session.preview if session else None

    def cleanup(self) -> None:
        cutoff = time.time() - SESSION_TTL_SECONDS
        expired = [
            token for token, session in self._sessions.items() if session.created_at < cutoff
        ]
        for token in expired:
            self._sessions.pop(token, None)
