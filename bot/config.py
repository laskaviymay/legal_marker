from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BotConfig:
    token: str
    db_dir: Path
    db_url: str | None = None
    github_token: str | None = None
    admin_ids: tuple[int, ...] = ()
    poll_timeout: int = 20

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None, default_root: Path | None = None) -> "BotConfig":
        root = default_root or Path.cwd()
        file_values = _load_env_file(root / ".env")
        values = dict(file_values)
        if env is not None:
            values.update(env)
        else:
            values.update(os.environ)
        token = (values.get("TELEGRAM_BOT_TOKEN") or "").strip()
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")

        db_dir_value = (values.get("LEGAL_MARKER_DB_DIR") or "").strip()
        db_dir = Path(db_dir_value) if db_dir_value else root / "bot_runtime" / "db"
        db_url = (values.get("LEGAL_MARKER_DB_URL") or "").strip() or None
        github_token = (values.get("LEGAL_MARKER_GITHUB_TOKEN") or "").strip() or None
        admin_ids = _parse_admin_ids(values.get("LEGAL_MARKER_ADMIN_IDS", ""))
        poll_timeout = _parse_poll_timeout(values.get("LEGAL_MARKER_POLL_TIMEOUT", "20"))
        return cls(
            token=token,
            db_dir=db_dir,
            db_url=db_url,
            github_token=github_token,
            admin_ids=admin_ids,
            poll_timeout=poll_timeout,
        )


def _parse_admin_ids(raw_value: str) -> tuple[int, ...]:
    values: list[int] = []
    for chunk in raw_value.split(","):
        stripped = chunk.strip()
        if not stripped:
            continue
        values.append(int(stripped))
    return tuple(values)


def _parse_poll_timeout(raw_value: str) -> int:
    try:
        return max(1, int(raw_value))
    except ValueError:
        return 20


def _load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values
