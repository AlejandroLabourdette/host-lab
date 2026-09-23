#!/bin/sh
# Stands in for valheim_server.x86_64.
#
# Reports what the real server cannot be asked about on a machine that cannot
# run it: which signal arrived, which uid it arrived as, and whether the state
# directory was actually writable at the moment it mattered.
set -eu

echo "stub: pid=$$ uid=$(id -u) gid=$(id -g)"
echo "stub: args: $*"

on_sigint() {
    echo "stub: received SIGINT"
    # The real server writes a save here. Writing anything at all proves the
    # permission fix ran and the dropped-privilege user can use the volume,
    # which is the failure mode of issue #802.
    echo "clean shutdown" > "${VALHEIM_STATE_DIR:-/data}/stub-shutdown.marker"
    echo "stub: wrote shutdown marker"
    exit 0
}

on_sigterm() {
    # Recorded so a test can prove SIGTERM was NOT what arrived. Docker's
    # default is SIGTERM, and inheriting it is the bug being guarded against.
    echo "stub: received SIGTERM"
    exit 1
}

trap on_sigint INT
trap on_sigterm TERM

echo "stub: ready"
# Short sleeps so a trap is handled promptly: a shell runs traps between
# commands, not during them.
while true; do
    sleep 0.2
done
