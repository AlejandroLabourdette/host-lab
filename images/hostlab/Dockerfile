# The platform's own machinery, as a container.
#
# ADR 0008 decided the shared machinery runs "inside a container on the host".
# That costs an indirection and buys the thing ADR 0004 argued for: the host
# stays clean and rebuildable. It matters more here than it would on a server,
# because this host is somebody's daily-driver laptop (ADR 0007) and will be
# reinstalled one day with no thought given to what the game server needed.
#
# What goes in, and why each one is here:
#
#   the hostlab package   what this image exists to run
#   the docker CLI        ADR 0008 chose the CLI over the SDK, so the platform
#                         runs the same command an operator would type at 2am
#   restic                ADR 0008 chose it for the off-site backup: encryption,
#                         retention and a real verify in one static binary
#
# Built for whichever architecture you build it on. The Valheim image is
# x86-64-only because the game is; this one has no such constraint, so it can
# be built and exercised on a developer's machine as well as on the host.
#
# The build context is the REPOSITORY ROOT, because the package and the title
# manifests both live there:
#
#   docker build -f images/hostlab/Dockerfile -t hostlab:<version> .

FROM python:3.13-slim AS build

# uv resolves and installs from the lockfile, so the image gets exactly the
# dependency versions the tests ran against rather than whatever resolves today.
COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /usr/local/bin/uv

WORKDIR /src
COPY pyproject.toml uv.lock README.md ./
COPY hostlab ./hostlab

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/hostlab/.venv

# Built at the path it will finally live at. A virtualenv's console scripts
# carry an absolute shebang, so creating it somewhere else and copying it in
# produces an image whose entrypoint does not exist, and the error says
# "no such file or directory" about a file that is plainly there.
RUN uv sync --frozen --no-dev --no-editable

# --------------------------------------------------------------------------

FROM python:3.13-slim

ARG TARGETARCH
# Pinned rather than floating. ADR 0004 consequence 5 makes a moving tag a
# thing that changes underneath you, and that applies to the tools inside an
# image as much as to the image itself.
ARG RESTIC_VERSION=0.19.1

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install --yes --no-install-recommends \
        ca-certificates \
        bzip2 \
        curl \
    && rm -rf /var/lib/apt/lists/*

# The docker CLI, taken from Docker's own multi-arch image rather than built
# here. It never talks to a real socket: the compose file points it at a
# read-only proxy (ADR 0010).
COPY --from=docker:28-cli /usr/local/bin/docker /usr/local/bin/docker

RUN curl -fsSL \
        "https://github.com/restic/restic/releases/download/v${RESTIC_VERSION}/restic_${RESTIC_VERSION}_linux_${TARGETARCH}.bz2" \
        -o /tmp/restic.bz2 \
    && bunzip2 /tmp/restic.bz2 \
    && mv /tmp/restic /usr/local/bin/restic \
    && chmod 0755 /usr/local/bin/restic \
    && restic version

COPY --from=build /opt/hostlab/.venv /opt/hostlab/.venv
ENV PATH="/opt/hostlab/.venv/bin:$PATH"

# The manifests and the title data. Read-only at runtime: this image describes
# titles, it does not accumulate state.
COPY titles /opt/hostlab/titles
WORKDIR /opt/hostlab

# Runs unprivileged. It reads container state through a proxy that offers no
# way to change anything, and it reads a game's save directory. Neither needs
# root, and this process is the one holding the backup credentials.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin hostlab
USER hostlab

ENTRYPOINT ["hostlab"]
CMD ["--help"]
