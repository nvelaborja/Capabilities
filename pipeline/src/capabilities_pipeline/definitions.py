"""What Dagster loads: the build's assets for this repository, built into build/ (or $CAPABILITIES_BUILD_DIR).

    cd pipeline && uv run dg dev                       # the UI, at http://localhost:3000
    cd pipeline && uv run dg launch --assets '*'       # one full build from the command line
"""

from capabilities.built import build_dir_for
from capabilities.graph import find_root

from .assets import definitions

ROOT = find_root()
defs = definitions(ROOT, build_dir_for(ROOT))
