from __future__ import annotations

from dataclasses import dataclass
import os


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    max_file_mb: int = 48
    max_duration_seconds: int = 3600
    max_concurrent_downloads: int = 2
    hourly_user_limit: int = 5
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            telegram_keys = [key for key in os.environ if "TELEGRAM" in key.upper()]
            raise RuntimeError(
                "TELEGRAM_BOT_TOKEN is required "
                f"(exact_key_present={'TELEGRAM_BOT_TOKEN' in os.environ}, "
                f"deploy_nonce_present={'DEPLOY_NONCE' in os.environ}, "
                f"telegram_key_count={len(telegram_keys)})"
            )
        return cls(
            bot_token=token,
            max_file_mb=_int_env("MAX_FILE_MB", 48),
            max_duration_seconds=_int_env("MAX_DURATION_SECONDS", 3600),
            max_concurrent_downloads=_int_env("MAX_CONCURRENT_DOWNLOADS", 2),
            hourly_user_limit=_int_env("HOURLY_USER_LIMIT", 5),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )
