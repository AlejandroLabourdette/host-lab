# 0010 - Reach the container runtime through a read-only proxy

> Status: accepted
> Date: 2026-09-23

## Context

Three earlier decisions meet here and produce a problem none of them saw.

[ADR 0005](0005-describe-titles-with-a-declarative-manifest.md) established that the platform's
control operations must come from the container runtime rather than from the game, because two of
the five titles surveyed expose no control interface at all.
[ADR 0008](0008-implementation-stack-and-manifest-syntax.md) put the machinery itself inside a
container, so the host stays clean. Together those mean **a container has to talk to the Docker
API**.

[ADR 0006](0006-give-friends-a-control-plane.md) consequence 5 says something else:

> The state reader and the action executor are separate components, and only the executor has
> authority. Stage 1 ships the reader alone, which is what makes stage 1 safe.

**Mounting the Docker socket into the reader's container makes that sentence false.** The socket is
not an interface with permissions; it is the whole API. A container holding it can start, stop,
delete and create any container on the host, and mount any host path into a new one. The reader's
*code* cannot do those things and there are tests asserting so, but the reader's *container* could,
and "safe because nobody wrote that function yet" is a different and much weaker claim than the one
ADR 0006 makes.

This was found while building the image, not while designing it, which is the honest reason it has
its own record.

## Options considered

### A. Mount the socket directly, and amend ADR 0006 to be honest about it

- **For:** one line of compose, no extra component, nothing to keep patched.
- **Against:** the guarantee becomes a matter of discipline. It holds exactly as long as nobody
  adds a convenience later, and the thing they would add is a restart button, which is the single
  most tempting addition to a status tool.
- **Verdict:** rejected, but it is the honest alternative and it would have been acceptable if the
  cost of B were higher than it is.

### B. A read-only socket proxy (chosen)

An off-the-shelf proxy holds the real socket and exposes, over an internal network, only the
endpoints it is configured to allow. The reader is pointed at that and never sees the socket.

- **For:** the refusal stops being a matter of what our code chooses to call. A destructive request
  is **not rejected by us, it is not reachable**, which is the difference between a rule and a
  boundary. ADR 0006's sentence becomes structurally true.
- **For:** it costs no code of ours. It is configuration plus a maintained image.
- **Against:** one more container to keep patched, and a third-party image in the arrangement.
- **Against, and this is the real one:** [ADR 0009](0009-reach-the-server-without-a-router-we-control.md)
  chose the relay specifically because it added nothing to a host already carrying more moving
  parts than the design intended. Adding a container here runs against that reasoning and the
  tension deserves naming rather than glossing.
- **Why it is accepted anyway:** the proxy is in the **observability** path, not the
  **availability** path. If it stops, `hostlab status` stops and the game server keeps running and
  keeps saving. The components ADR 0009 was anxious about, Docker Desktop and auto-logon, sit
  between the machine powering on and the world existing. This one does not.

### C. Run the machinery natively on Windows

- **For:** no socket question at all; the Docker CLI talks to the local daemon as the logged-in
  user.
- **Against:** contradicts ADR 0008, and puts Python, uv and a checkout of this repository on a
  machine that is somebody's daily driver, which is what ADR 0004's "the host stays clean and
  rebuildable" argument exists to prevent.
- **Verdict:** rejected. It also would not actually reduce authority: the machinery would then run
  as a user who can do anything to Docker.

## Decision

**The machinery reaches Docker through `tecnativa/docker-socket-proxy`, configured to allow
container reads and refuse every mutating call.** `CONTAINERS=1` admits the endpoints behind
`docker inspect` and `docker logs`; `POST=0`, which is the default, refuses every request that
changes anything. The proxy holds the socket; the reader holds only an address on an internal
network.

The image tag is pinned, per [ADR 0004](0004-run-game-servers-as-containers.md) consequence 5.

### Verified rather than assumed

Measured 2026-09-23 against a running proxy, which matters because a security boundary that has
only been read about is a boundary nobody has tested:

| Through the proxy | Result |
|---|---|
| `docker ps` | works |
| `docker inspect <container>` | works, including `RestartCount` |
| `docker logs <container>` | works, which the join code reader needs |
| `docker stop` | **403 Forbidden** |
| `docker kill` | **403 Forbidden** |
| `docker rm -f` | **403 Forbidden** |
| `docker restart` | **403 Forbidden** |
| `docker run` (create a new container) | **403 Forbidden** |

The target container was still running afterwards. A test in the suite reproduces this, so the
boundary is checked rather than believed.

## Consequences

1. **ADR 0006 consequence 5 is now structurally true rather than aspirational.** Stage 1's reader
   cannot act, because the verbs are not reachable, not because it declines to use them.
2. **Stage 2 will have to change this deliberately.** Adding start and stop means granting specific
   endpoints through the proxy, which is a visible, reviewable line in a compose file rather than a
   quiet new function. That is a better place for that decision to be made than inside a Python
   module, and it is the main reason this is worth the extra container.
3. **`DOCKER_HOST` is how the CLI is pointed at the proxy**, so ADR 0008's choice of the CLI over
   the SDK survives unchanged: the command is still the one an operator would type, with one
   environment variable different.
4. **If the proxy stops, status stops and nothing else does.** Worth knowing when diagnosing a
   silent channel: the absence of a status update means the reader or the proxy, not the game.
5. **A third-party image is now in the arrangement**, and it is one whose entire job is to refuse
   things. It is pinned, and its behaviour is asserted by a test rather than trusted.
6. **The reader's container runs unprivileged and mounts the game's state read-only.** Neither is
   required by this decision, both are cheap, and together they mean the component holding the
   backup credentials is also the one that can do least.

## Revisit if

- **Stage 2 arrives.** The proxy's configuration becomes part of that decision, and the endpoints
  granted should be the smallest set that the executor genuinely needs.
- **The proxy stops being maintained.** The alternatives are writing an equivalent, which is more
  machinery than this deserves, or falling back to option A with ADR 0006 amended honestly.
- **Docker gains real per-connection authorization**, which would make an external proxy
  unnecessary.
