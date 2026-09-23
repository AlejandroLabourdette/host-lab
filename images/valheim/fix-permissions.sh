#!/bin/sh
# Set ownership and permissions on a state directory, distinguishing files from
# directories.
#
# This script is three lines long and it exists because of a real incident.
# valheim-server-docker issue #802: after Valheim 1.0 turned each world into a
# directory, a permission-fixing routine applied 0644 to everything under
# worlds_local/, the new per-world directories included. A directory without
# the execute bit cannot have entries created in it, so every autosave failed,
# silently, while the container reported healthy. The migration had already
# renamed the old save aside, so there was no fallback either.
#
# The lesson generalises past that one container: a blanket chmod is always
# wrong on a tree that contains both. Hence two passes, each with -type.
#
#   usage: fix-permissions.sh <dir> [uid:gid]
#
# Ownership is only attempted as root, so the chmod half can be tested
# anywhere. That is deliberate: this logic is the kind that is never exercised
# until the day it destroys something.

set -eu

dir=${1:?usage: fix-permissions.sh <dir> [uid:gid]}
owner=${2:-}

if [ ! -d "$dir" ]; then
    echo "fix-permissions: $dir does not exist yet, nothing to do"
    exit 0
fi

if [ -n "$owner" ]; then
    if [ "$(id -u)" = "0" ]; then
        chown -R "$owner" "$dir"
    else
        echo "fix-permissions: not root, leaving ownership alone" >&2
    fi
fi

# Two passes, and the order is not interchangeable.
#
# PASS 1 repairs traversal. A directory without the execute bit cannot be
# opened, and that includes being opened by the tool sent to repair it: find
# reads a directory's contents before it runs any action on it, so
# `find -type d -exec chmod ...` fails with "Permission denied" and fixes
# nothing. It cannot be the repair mechanism. `chmod -R` can, because it
# applies the mode to a directory and then descends into it, so each level
# becomes traversable just before it is needed.
#
# The capital X grants execute to directories and leaves data files alone,
# which is the whole distinction this script exists to make.
chmod -R u+rwX,go+rX "$dir"

# PASS 2 normalises. Pass 1 only adds permissions, so anything already too
# permissive would stay that way. Now that the tree is traversable, find can
# set exact modes.
find "$dir" -type d -exec chmod 0755 {} +
find "$dir" -type f -exec chmod 0644 {} +
