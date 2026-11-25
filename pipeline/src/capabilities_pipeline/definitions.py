"""What Dagster loads: the build's assets for this repository, built into build/ (or $CAPABILITIES_BUILD_DIR).

    cd pipeline && uv run dg dev                       # the UI, at http://localhost:3000
    cd pipeline && uv run dg launch --assets '*'       # one full build from the command line
"""

from pathlib import Path

from capabilities.built import build_dir_for
from capabilities.graph import find_root
from dotenv import load_dotenv

from .assets import definitions

# Keys that stay out of git (OPENALEX_API_KEY), in pipeline/.env, read before anything downloads. A variable already set
# in the environment wins over the file.
load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

ROOT = find_root()
defs = definitions(ROOT, build_dir_for(ROOT))
