#!/bin/sh
# Start the Valheim dedicated server.
#
# Two properties matter more than anything else this script does.
#
# 1. The server must be PID 1, so SIGINT reaches it directly. Valheim saves
#    cleanly on SIGINT and Iron Gate's own guidance is to stop it with Ctrl+C;
#    SIGKILL loses everything since the last autosave. A shell that forwards
#    signals is a shell that can fail to, so this execs instead.
#
# 2. Permissions are fixed before the server starts, and files and directories
#    are treated differently. See fix-permissions.sh for the incident.
#
# Configuration arrives as the container's command, rendered from the manifest.
# Nothing is written to start_server.sh, which Steam overwrites on every
# update: that is the config_hazard the manifest declares, and avoiding it is
# structural here rather than a rule someone has to remember.

set -eu

: "${VALHEIM_STATE_DIR:=/data}"
: "${VALHEIM_UID:=10000}"
: "${VALHEIM_GID:=10000}"

mkdir -p "$VALHEIM_STATE_DIR"
/usr/local/bin/fix-permissions.sh "$VALHEIM_STATE_DIR" "${VALHEIM_UID}:${VALHEIM_GID}"

# Iron Gate's own launch script sets both of these. SteamAppId is the game's
# app id (892970), not the dedicated server's (896660), and the server does not
# start correctly without it.
export SteamAppId=892970
export LD_LIBRARY_PATH="/opt/valheim/linux64:${LD_LIBRARY_PATH:-}"

echo "valheim: starting as ${VALHEIM_UID}:${VALHEIM_GID}, state at ${VALHEIM_STATE_DIR}"

# setpriv comes from util-linux, which is already in the base image, so this
# needs no gosu. --init-groups sets the supplementary groups; without it the
# process keeps root's, which would defeat dropping privilege at all.
exec setpriv \
    --reuid "$VALHEIM_UID" \
    --regid "$VALHEIM_GID" \
    --init-groups \
    -- /opt/valheim/valheim_server.x86_64 "$@"
