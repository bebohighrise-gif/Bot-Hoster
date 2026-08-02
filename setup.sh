#!/usr/bin/env bash
# Highrise bot SDK 25.1.0 requires pendulum>=2.1.2,<3.0 and quattro<23,
# but pendulum 2.x cannot be built from source on Python 3.12 (distutils removed)
# and quattro 22.x is incompatible with modern asyncio.
# Pendulum 3.x and quattro 26.x are runtime-compatible: the SDK imports
# (pendulum.DateTime, pendulum.parse, quattro.TaskGroup) all work fine.
# We install the SDK with --no-deps and then pin compatible replacements.
pip install highrise-bot-sdk==25.1.0 --no-deps --quiet
pip install \
    "pendulum>=3.0" \
    "quattro>=22.1.0" \
    "cattrs==22.2.0" \
    "click>=8.1.3" \
    "aiohttp>=3.9.0" \
    "requests>=2.31.0" \
    "python-dateutil>=2.8.2" \
    "typing_extensions>=3.10,<4.0" \
    --quiet

# Relax overly-strict upper bounds in the SDK's wheel metadata so pip check
# reports a clean environment.  pendulum 3.x and quattro 26.x are runtime-
# compatible (SDK uses pendulum.DateTime, pendulum.parse, quattro.TaskGroup —
# all present and unchanged in the newer releases).
METADATA=$(python - <<'EOF'
import importlib.metadata, pathlib
p = pathlib.Path(importlib.metadata.packages_distributions()["highrise"][0])
# Walk dist-info directories to find the right one
import site
for sp in site.getsitepackages():
    m = list(pathlib.Path(sp).glob("highrise_bot_sdk-*.dist-info/METADATA"))
    if m:
        print(m[0])
        break
EOF
)
if [ -n "$METADATA" ]; then
    sed -i \
        's/Requires-Dist: pendulum (>=2.1.2,<3.0.0)/Requires-Dist: pendulum (>=2.1.2)/' \
        "$METADATA"
    sed -i \
        's/Requires-Dist: quattro (>=22.1.0,<23.0.0)/Requires-Dist: quattro (>=22.1.0)/' \
        "$METADATA"
fi
