# host-lab

Design and operations documentation for a **self-hosted game server platform**: one always-on
machine that owns the world save, so a group of friends never again has to wait for one particular
person to be at their computer before they can play.

Valheim is the first title documented, in depth. The platform is designed so that other titles
(Minecraft, Palworld, Satisfactory, Enshrouded) fit the same shape.

## Status

The design came first and is finished: seven documents and eight decision records in
[`docs/`](docs/). **The implementation is now in progress**, and it is a transcription of that
design rather than an improvisation, which was the point of doing it in that order.

The host is a Windows 11 Home machine that is also somebody's gaming PC, which the design did not
originally know. [ADR 0007](docs/decisions/0007-host-on-windows-with-docker-desktop-and-wsl2.md)
corrects that against evidence, and [`docs/windows-host.md`](docs/windows-host.md) is what it means
in practice. [ADR 0008](docs/decisions/0008-implementation-stack-and-manifest-syntax.md) records
the stack.

The layout it is being built into, so the map exists before all of it does:

| Where | What |
|---|---|
| `docs/` | The design, the decisions, and the operator documentation |
| `titles/` | One declarative manifest per game. Data, not code |
| `hostlab/` | The shared machinery that interprets a manifest |
| `images/` | One container image per title |
| `deploy/` | Host configuration and the compose files |
| `tools/` | Diagnostics, including the UDP path prover |

## Start here

[`docs/README.md`](docs/README.md) is the index. It carries the reading order, the layout and the
writing conventions every document in this repository follows.

If you want the concrete thing rather than the design, go straight to
[`docs/titles/valheim.md`](docs/titles/valheim.md), which runs from a bare Linux machine to friends
connected, including the networking.
