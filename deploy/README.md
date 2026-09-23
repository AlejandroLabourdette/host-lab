# Deploying

Two files describe a running server, and they are separate because they change
for different reasons:

| File | Says | Changes when |
|---|---|---|
| [`../titles/valheim.yaml`](../titles/valheim.yaml) | What Valheim **is** | Iron Gate changes the game |
| [`valheim/valheim.yaml`](valheim/valheim.yaml) | What **this** server is | The group decides something |
| `.env` | The secrets, referenced by both | A credential rotates |

## First time

```bash
cp deploy/.env.example deploy/.env      # then fill it in. It is gitignored.

# The game. x86-64 only, because the server is.
docker build --platform linux/amd64 -t hostlab/valheim:1.0.15 images/valheim

# The platform's own machinery. Context is the repository root.
docker build -f images/hostlab/Dockerfile -t hostlab:0.1.0 .
```

Tag the game image with the version you actually built, never `latest`. See
[`../images/valheim/README.md`](../images/valheim/README.md).

## Every time

```bash
# 1. Check. Writes nothing, runs every refusal.
uv run hostlab plan valheim --instance deploy/valheim/valheim.yaml

# 2. Generate the compose file.
uv run hostlab compose valheim --instance deploy/valheim/valheim.yaml \
    --out deploy/valheim/compose.yaml

# 3. Start it.
docker compose --env-file deploy/.env -f deploy/valheim/compose.yaml up -d
```

**Run `plan` first and read it.** It is the cheap way to find out that a
password breaks a rule, because the server's way of telling you is to exit in a
way that looks like a crash. Every refusal names the field and says why the
rule exists.

The generated compose file is **gitignored and regenerated**, not edited. It
contains no secrets: a secret appears as `${PLACEHOLDER}` and `docker compose`
substitutes it from `.env` at run time, so the file is safe to read over
someone's shoulder. Editing it directly means the next regeneration silently
reverts you, which is the same trap as putting configuration in
`start_server.sh`.

## The platform services

Separate from the game, and hand-written rather than generated, because they are
not per-title: they would exist if there were five games or none.

```bash
cd deploy/platform
docker compose --env-file ../.env up -d docker-socket
```

That starts the socket proxy. Then the reader runs on demand against it:

```bash
docker compose --env-file ../.env --profile tools run --rm hostlab     status valheim --container valheim --state-dir /data
```

```bash
docker compose --env-file ../.env --profile tools run --rm hostlab     publish valheim --container valheim --state-dir /data
```

**The proxy is the point, not plumbing.**
[ADR 0010](../docs/decisions/0010-reach-the-runtime-through-a-read-only-proxy.md): the Docker
socket is not an interface with permissions, it is the whole API, so a container holding it could
stop or delete anything on the host. The proxy allows container reads and refuses every mutating
call, which is what makes
[ADR 0006](../docs/decisions/0006-give-friends-a-control-plane.md) consequence 5 true by
construction rather than because our code happens to lack the function.

Verified, not assumed: through the proxy, `docker stop`, `kill`, `rm`, `restart` and `run` all
return **403 Forbidden**, and `tests/test_runtime_boundary.py` asserts it on every run.

## After it starts

Work down the ladder in
[`../docs/titles/valheim.md`](../docs/titles/valheim.md#verify-it-worked),
stopping at the first failure. Rung 1 is the one this tooling can still get
wrong in a way nothing else would show:

```bash
docker exec valheim sh -c 'ss -tulpn | grep 245' || \
  docker compose -f deploy/valheim/compose.yaml exec valheim sh -c 'ss -tulpn | grep 245'
```

Both ports must appear as **udp**. If they show as `tcp`, something published
them without `/udp` and the server is unreachable no matter what the router
says.

## What this deliberately does not do

**No restart rate cap.** `restart: unless-stopped` retries with backoff but
neither caps nor reports.
[`../docs/always-on-operation.md`](../docs/always-on-operation.md) wants a
server that restarted eleven times overnight treated as broken even though it
is currently running. Compose's `restart_policy.max_attempts` only applies
under Swarm, so writing it here would look like a limit and be nothing. That
check belongs to the status reader, which can see the restart count.

**No container healthcheck.** The manifest's liveness check is an A2S query,
and putting a query client inside the game image would couple the container's
health to a protocol that breaks against game updates, which is exactly what
happened to LinuxGSM's Valheim monitor. The status reader does it from outside.

**No start, stop or restart authority for anyone but the owner.**
[ADR 0006](../docs/decisions/0006-give-friends-a-control-plane.md) stages that,
and this is stage 1.
