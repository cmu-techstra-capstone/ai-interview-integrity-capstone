# Docker

The image packages the existing CLI: code, Python dependencies, ffmpeg and curl. It holds
**no data**: datasets, media, model weights and caches are never baked in. Host folders
are bind-mounted at run time. There are no databases, web servers or named volumes.

| File | Purpose |
|---|---|
| `Dockerfile` | `python:3.12-slim` + ffmpeg/curl; dependency layer cached on `pyproject.toml`; non-root user |
| `.dockerignore` | excludes `.git`, `.venv`, `data/`, `processed/`, media, archives, model files, credentials |
| `compose.yaml` | one `app` service; bind mounts for `data/`, `processed/`, `manifests/`, optional shared storage; temp cache on tmpfs (RAM, 1 GB) |
| `docker/install_deps.py` | installs only the dependencies for the requested extras |
| `docker/certs/` | optional extra CA certificates (`*.crt`) |

**Expected size:** roughly 500–700 MB with the default `EXTRAS=dev`, mostly ffmpeg and its
libraries. This is an estimate; the image has not been built yet (see
[teammate-validation.md](teammate-validation.md)). STT extras add several GB. Install
them only on a machine with space.

## Commands

```bash
docker compose build                                   # EXTRAS=dev by default
docker compose run --rm app pytest                     # full test suite in the container
docker compose run --rm app interview-integrity --help
docker compose run --rm app interview-integrity datasets status

# Linux hosts: let the container write to bind-mounted folders as you
export HOST_UID=$(id -u) HOST_GID=$(id -g)

# Shared storage (e.g. a Drive for Desktop folder) mounted at /shared
SHARED_ROOT="/path/to/AI Interview Integrity Capstone" docker compose run --rm app \
  interview-integrity process-remote --dataset staged_interviews --root /shared

# STT candidates (heavy; machine with disk space only)
EXTRAS=dev,stt-faster-whisper docker compose build
```

Settings can also come from `INTERVIEW_INTEGRITY_*` environment variables (see
`src/interview_integrity/config.py`). Command-line flags take precedence.

## Known issue: Michigan source over TLS inside Linux containers

`web.eecs.umich.edu` doesn't send its intermediate certificate (InCommon RSA OV SSL CA 3).
macOS `curl` completes the chain from the system keychain, but Debian's `curl` in the
container usually can't, so `process-source` for Michigan may fail certificate
verification there. Options, without disabling verification:

- run `process-source` on the host, or
- place the intermediate certificate (PEM, `.crt`) in `docker/certs/` and rebuild.
  `update-ca-certificates` adds it to the container's trust store.

## Inspecting and cleaning up disk usage

Look first. These commands only report:

```bash
docker system df            # space used by images, containers, build cache, volumes
docker image ls             # images (this project's is interview-integrity:dev)
docker container ls -a      # all containers, including stopped ones
```

Clean up selectively. These do **not** touch your project folders: bind mounts are
regular host directories.

```bash
docker container prune      # remove stopped containers (asks for confirmation)
docker image rm interview-integrity:dev   # remove just this project's image
docker image prune          # remove dangling (untagged) images
docker builder prune        # remove unused build cache (often the largest item)
```

Use with care. These affect *all* Docker projects on the machine:

```bash
docker image prune -a       # remove every image not used by a container
docker system prune         # stopped containers + dangling images + unused networks + build cache
```

Avoid `docker system prune --volumes` and `docker volume prune` unless you know what's in
your volumes. This project creates no named volumes, but other projects on the machine
may keep data there.
