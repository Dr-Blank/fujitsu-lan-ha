#!/usr/bin/env bash
# Link the integration into the Home Assistant devcontainer's config directory
# and install aioayla-lan editable into the container's venv.
#
# Requires the devcontainer to bind mount this repository at
# /workspaces/fujitsu-lan-ha and the library at /workspaces/aioayla-lan. Edits
# on the host are then live; Home Assistant still needs a restart to pick up
# changed Python.
set -euo pipefail

DEST="${HA_CORE:-$HOME/projects/ha-core}/config/custom_components"
CONTAINER="${HA_CONTAINER:-$(docker ps --filter label=devcontainer.local_folder="${HA_CORE:-$HOME/projects/ha-core}" --format '{{.Names}}' | head -n1)}"

mkdir -p "$DEST"
rm -rf "${DEST:?}/fglair_local"
ln -s /workspaces/fujitsu-lan-ha/custom_components/fglair_local "$DEST/fglair_local"
echo "linked $DEST/fglair_local -> /workspaces/fujitsu-lan-ha/custom_components/fglair_local"

if [ -z "$CONTAINER" ]; then
  echo "devcontainer not running; install the library later with:" >&2
  echo "  uv pip install --python /home/vscode/.local/ha-venv/bin/python -e /workspaces/aioayla-lan" >&2
  exit 0
fi
docker exec "$CONTAINER" uv pip install --python /home/vscode/.local/ha-venv/bin/python -e /workspaces/aioayla-lan
echo "installed aioayla-lan editable in $CONTAINER"
