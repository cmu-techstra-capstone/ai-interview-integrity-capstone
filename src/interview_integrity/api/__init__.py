"""Localhost-only FastAPI development surface for offline analysis.

Bind to loopback only. Do not treat CORS as authentication. Recording inputs must
resolve under a configured authorized directory.
"""

from .app import create_app

__all__ = ["create_app"]
