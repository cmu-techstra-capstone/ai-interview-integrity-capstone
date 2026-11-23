"""Static sanity checks for the Docker scaffolding (no image is built here)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _lines(name):
    return [l.strip() for l in (ROOT / name).read_text().splitlines() if l.strip() and not l.strip().startswith("#")]


def test_dockerfile_basics():
    text = (ROOT / "Dockerfile").read_text()
    assert "FROM python:3.12-slim" in text
    assert "ffmpeg" in text and "curl" in text and "--no-install-recommends" in text
    assert "rm -rf /var/lib/apt/lists/*" in text
    assert "\nUSER app" in text  # non-root
    # dependency layer is installed before the source is copied (layer caching)
    assert text.index("install_deps.py") < text.index("COPY src ./src")
    sources = [l.split()[1] for l in _lines("Dockerfile") if l.startswith("COPY")]
    for src in sources:
        assert src not in (".", "./"), "never COPY the whole build context"
        assert not src.startswith(("data", "processed", ".git", ".venv", "notebooks")), src


def test_dockerignore_excludes_data_media_and_secrets():
    patterns = set(_lines(".dockerignore"))
    required = {".git", ".venv", "data", "processed", ".env", "**/*.mp4", "**/*.wav", "**/*.zip",
                "**/*.safetensors", "**/__pycache__", ".pytest_cache", "ai-interview-integrity-capstone"}
    assert required <= patterns, required - patterns
    assert "README.md" not in patterns  # needed by pyproject at build time


def test_compose_has_no_named_volumes_or_extra_services():
    text = (ROOT / "compose.yaml").read_text()
    top_level = [l for l in text.splitlines() if l and not l.startswith((" ", "#"))]
    assert top_level == ["services:"], "only the app service; no top-level volumes/networks"
    assert "  app:" in text and "tmpfs:" in text
    for forbidden in ("postgres", "redis", "mysql", "mongo", "gpus", "deploy:"):
        assert forbidden not in text.lower()


def test_install_deps_script_knows_all_extras():
    import tomllib

    extras = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["optional-dependencies"]
    assert {"dev", "stt-faster-whisper", "stt-whisperx"} <= set(extras)
    assert (ROOT / "docker" / "install_deps.py").is_file()
