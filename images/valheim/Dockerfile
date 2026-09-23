# The Valheim dedicated server, with the server baked into the image.
#
# ADR 0004 consequence 5 says "image tags become the version-pinning mechanism,
# which makes binary rollback easy", and always-on-operation.md leans on that
# again when it says rolling back binaries is trivial with containers and
# awkward with SteamCMD. That is only true if the server is IN the image. A
# container that runs SteamCMD at startup has a tag that pins the wrapper and
# not the game, and the advantage the ADR claimed is not actually held.
#
# One nuance worth being honest about: SteamCMD installs whatever is current,
# so the tag RECORDS a version rather than REQUESTS one. You cannot build
# yesterday's image today. What you can do is keep the image you built
# yesterday, which is what rollback needs. The exact build is recoverable from
# the image itself, in /opt/valheim/steamapps/appmanifest_896660.acf.
#
# Build:
#   docker build --platform linux/amd64 -t hostlab/valheim:<version> images/valheim
#
# There is no arm64 build of this server. ADR 0001 rejected a single-board
# computer for the same reason, and the platform line in titles/valheim.yaml
# declares it.

# --------------------------------------------------------------------------
# Stage 1: fetch the server with SteamCMD
# --------------------------------------------------------------------------
# Separated so the i386 runtime SteamCMD needs does not end up in the image
# that runs the game.
FROM debian:bookworm-slim AS fetch

ARG STEAM_APP_ID=896660

# SteamCMD is a 32-bit binary, so i386 has to be enabled to install it.
RUN dpkg --add-architecture i386 \
    && apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install --yes --no-install-recommends \
        ca-certificates \
        lib32gcc-s1 \
        wget \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /opt/steamcmd \
    && wget -qO- https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz \
       | tar -xz -C /opt/steamcmd

# +force_install_dir must come BEFORE +login. Omit it and SteamCMD patches its
# own steamapps tree instead, leaving the real install on the old build, and
# nothing fails: the old binary starts normally and the problem surfaces days
# later as players on updated clients being unable to join.
#
# validate re-checks the download against Steam's manifest. It costs seconds
# and catches a partial download, which otherwise presents as a server that
# starts and behaves strangely.
RUN /opt/steamcmd/steamcmd.sh \
        +force_install_dir /opt/valheim \
        +login anonymous \
        +app_update "${STEAM_APP_ID}" validate \
        +quit

# --------------------------------------------------------------------------
# Stage 2: the image that runs
# --------------------------------------------------------------------------
FROM debian:bookworm-slim

# Iron Gate lists these beyond the standard Steam client libraries, along with
# a floor of GLIBC 2.29 and GLIBCXX 3.4.26. Debian bookworm is well above both.
# If the server exits immediately with a symbol or version error rather than a
# game log, the base system is too old and no configuration change will help.
#
# libpulse is an audio library and this server is headless. It is still
# required, because the binary links against it regardless. Do not trim it.
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install --yes --no-install-recommends \
        ca-certificates \
        libatomic1 \
        libpulse0 \
        libsdl2-2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# A fixed, high, non-system uid and gid. Fixed because the state volume
# outlives the image and its ownership has to keep matching; high because it
# will not collide with a host user on a machine that is also somebody's
# desktop.
ARG VALHEIM_UID=10000
ARG VALHEIM_GID=10000
RUN groupadd --gid "${VALHEIM_GID}" valheim \
    && useradd --uid "${VALHEIM_UID}" --gid "${VALHEIM_GID}" --no-create-home --shell /usr/sbin/nologin valheim

COPY --from=fetch /opt/valheim /opt/valheim
COPY fix-permissions.sh entrypoint.sh /usr/local/bin/
RUN chmod 0755 /usr/local/bin/fix-permissions.sh /usr/local/bin/entrypoint.sh

ENV VALHEIM_STATE_DIR=/data \
    VALHEIM_UID=${VALHEIM_UID} \
    VALHEIM_GID=${VALHEIM_GID}

# Declared so the image is honest about it. The real mount is supplied by the
# deployment, deliberately placed per ADR 0003.
VOLUME ["/data"]

# Both UDP. Publishing these as TCP yields a server that looks correct and is
# unreachable, which is why the renderer never emits a bare port.
EXPOSE 2456/udp 2457/udp

# The single highest-consequence line in this file. Docker's default is
# SIGTERM after 10 seconds: the wrong signal, and a timeout shorter than a
# large world takes to write. The manifest carries the same two values, and the
# renderer passes them explicitly, so a container started by hand from this
# image still stops correctly.
STOPSIGNAL SIGINT

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

LABEL org.opencontainers.image.title="Valheim dedicated server" \
      org.opencontainers.image.source="https://github.com/community-valheim-tools" \
      org.opencontainers.image.description="Valheim dedicated server, built for the host-lab platform. The tag records the Steam build installed at image build time; see /opt/valheim/steamapps/appmanifest_896660.acf."
