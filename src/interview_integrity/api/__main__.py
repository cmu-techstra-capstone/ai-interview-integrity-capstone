"""Run the localhost development API: ``python -m interview_integrity.api``."""

from __future__ import annotations

import logging
import sys

from .config import ALLOWED_BIND_HOSTS, ApiConfigError, ApiSettings


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr)

    try:
        settings = ApiSettings.from_env()
    except ApiConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    # Refuse any attempt to bind non-loopback even if somehow injected later.
    if settings.host not in ALLOWED_BIND_HOSTS:
        print(f"refusing to bind non-loopback host {settings.host!r}", file=sys.stderr)
        return 2

    try:
        import uvicorn
    except ImportError:
        print(
            "uvicorn is required for the local API. Install with:\n"
            '  pip install -e ".[api]"\n',
            file=sys.stderr,
        )
        return 2

    print(
        f"Starting Interview Integrity local API on http://{settings.host}:{settings.port}\n"
        f"  recordings dir: {settings.recordings_dir}\n"
        f"  allowed origins: {settings.allowed_origins or '(none configured — set API_ALLOWED_ORIGINS)'}\n"
        "  detection model: unavailable\n"
        "  This is offline analysis only — not live Google Meet monitoring.\n",
        file=sys.stderr,
    )

    # Import app factory after config validation.
    from .app import create_app

    app = create_app(settings)
    # Explicit loopback bind — never 0.0.0.0.
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
