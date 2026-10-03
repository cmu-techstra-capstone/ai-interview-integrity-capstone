"""Runtime settings, overridable with environment variables (useful in Docker/CI).

| Setting         | Environment variable                 | Default           |
|-----------------|--------------------------------------|-------------------|
| interim_dir     | INTERVIEW_INTEGRITY_INTERIM_DIR      | data/interim      |
| out_dir         | INTERVIEW_INTEGRITY_OUT_DIR          | data/processed    |
| manifest_dir    | INTERVIEW_INTEGRITY_MANIFEST_DIR     | manifests         |
| cache_dir       | INTERVIEW_INTEGRITY_CACHE_DIR        | (system temp dir) |
| max_cache_mb    | INTERVIEW_INTEGRITY_MAX_CACHE_MB     | 500               |
| shared_root     | INTERVIEW_INTEGRITY_SHARED_ROOT      | (unset)           |
| log_level       | INTERVIEW_INTEGRITY_LOG_LEVEL        | INFO              |

Command-line flags always take precedence over these values.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

PREFIX = "INTERVIEW_INTEGRITY_"


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    interim_dir: Path = Path("data/interim")
    out_dir: Path = Path("data/processed")
    manifest_dir: Path = Path("manifests")
    cache_dir: Path | None = None
    max_cache_mb: float = 500.0
    shared_root: Path | None = None
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env

        def get(name: str) -> str | None:
            value = env.get(PREFIX + name.upper())
            return value.strip() if value and value.strip() else None

        max_mb = get("max_cache_mb")
        try:
            max_cache_mb = float(max_mb) if max_mb else cls.max_cache_mb
        except ValueError:
            raise ConfigError(f"{PREFIX}MAX_CACHE_MB must be a number, got {max_mb!r}") from None
        if max_cache_mb <= 0:
            raise ConfigError(f"{PREFIX}MAX_CACHE_MB must be > 0, got {max_cache_mb}")

        level = (get("log_level") or cls.log_level).upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
            raise ConfigError(f"{PREFIX}LOG_LEVEL must be DEBUG/INFO/WARNING/ERROR, got {level!r}")

        return cls(
            interim_dir=Path(get("interim_dir") or cls.interim_dir),
            out_dir=Path(get("out_dir") or cls.out_dir),
            manifest_dir=Path(get("manifest_dir") or cls.manifest_dir),
            cache_dir=Path(p) if (p := get("cache_dir")) else None,
            max_cache_mb=max_cache_mb,
            shared_root=Path(p) if (p := get("shared_root")) else None,
            log_level=level,
        )
