"""Install only the dependencies declared in pyproject.toml (for Docker layer caching).

Usage: python docker/install_deps.py dev,stt-faster-whisper
The dependency layer is rebuilt only when pyproject.toml changes, not on every code edit.
"""

import subprocess
import sys
import tomllib

extras = [e.strip() for e in (sys.argv[1] if len(sys.argv) > 1 else "").split(",") if e.strip()]
with open("pyproject.toml", "rb") as fh:
    project = tomllib.load(fh)["project"]
deps = list(project.get("dependencies", []))
optional = project.get("optional-dependencies", {})
unknown = [e for e in extras if e not in optional]
if unknown:
    sys.exit(f"Unknown extras {unknown}; available: {sorted(optional)}")
for extra in extras:
    deps += optional[extra]
if deps:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--no-cache-dir", *deps])
print(f"installed {len(deps)} dependency spec(s) for extras={extras or '[]'}")
