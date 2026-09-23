# The Valheim image's plumbing, with a stub in place of the game.
#
# sources.md ranks "SIGINT as the graceful stop signal" as its second
# highest-risk claim and says to verify it rather than assume it, because
# getting it wrong loses up to save_interval_seconds of play on every stop.
#
# Verifying it fully needs the real server and a world, which is a host job.
# But the claim splits in two, and only one half needs the game:
#
#   1. Does the container plumbing deliver SIGINT to the process? Ours.
#   2. Does the server save cleanly when it gets one? Iron Gate's.
#
# This image tests (1), which is where our bugs would be: an entrypoint that
# spawns instead of execs, a STOPSIGNAL left at Docker's SIGTERM default, or a
# privilege drop that loses the signal on the way. It deliberately mirrors the
# real Dockerfile's last stage, and uses the real scripts rather than copies.
FROM debian:bookworm-slim

ARG VALHEIM_UID=10000
ARG VALHEIM_GID=10000
RUN groupadd --gid "${VALHEIM_GID}" valheim \
    && useradd --uid "${VALHEIM_UID}" --gid "${VALHEIM_GID}" --no-create-home --shell /usr/sbin/nologin valheim

# The real scripts, not stand-ins. A test against a copy tests the copy, so the
# build context is the repository root and these are the very files the shipped
# image uses.
#
#   docker build -f tests/fixtures/stub-image/Dockerfile .
COPY images/valheim/fix-permissions.sh images/valheim/entrypoint.sh /usr/local/bin/
COPY tests/fixtures/stub-image/stub-server.sh /opt/valheim/valheim_server.x86_64
RUN chmod 0755 /usr/local/bin/fix-permissions.sh /usr/local/bin/entrypoint.sh \
        /opt/valheim/valheim_server.x86_64

ENV VALHEIM_STATE_DIR=/data \
    VALHEIM_UID=${VALHEIM_UID} \
    VALHEIM_GID=${VALHEIM_GID}

STOPSIGNAL SIGINT
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
