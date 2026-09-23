# Documentation index

> Status: living
> Last reviewed: 2026-09-22

This is the documentation for a self-hosted, multi-game server platform running on a machine the
owner controls. Read [`scope-and-goals.md`](scope-and-goals.md) first; it defines the problem that
every other document here is trying to solve.

## Reading order

The documents are written to be read in this order. Each one assumes the ones above it.

| # | Document | Answers |
|---|---|---|
| 1 | [`scope-and-goals.md`](scope-and-goals.md) | What are we building, for whom, and what is explicitly not in scope? |
| 2 | [`networking.md`](networking.md) | How do friends on the internet reach a server sitting behind a household router? |
| 3 | [`save-data-and-backups.md`](save-data-and-backups.md) | What is the world on disk, what has to be copied, and how do we know it would come back? |
| 4 | [`always-on-operation.md`](always-on-operation.md) | What keeps the machine, the process and the world alive without anyone watching? |
| 5 | [`platform-architecture.md`](platform-architecture.md) | What is shared across games, what is specific to one, and where does the boundary go? |
| 6 | [`remote-control.md`](remote-control.md) | How do friends start, stop and check the server without the owner present? |
| 7 | [`titles/valheim.md`](titles/valheim.md) | The first concrete case, end to end: bare machine to friends connected. |
| 8 | [`windows-host.md`](windows-host.md) | The host is Windows, not Linux. What does that change, and what has to be configured so it survives a reboot nobody asked for? |
| 9 | [`sources.md`](sources.md) | Where every claim came from, when it was true, and what to re-check when. |

Each document assumes the ones above it and can be read without the ones below. Cross-references
do point forward where a later document holds the detail, but **never for a prerequisite**: a
forward link is always an offer of more, not a dependency you have to follow first.

## Decision records

Choices with real alternatives are recorded as ADRs in [`decisions/`](decisions/), one file per
decision, numbered and append-only. An ADR states the context, the options that were genuinely on
the table, what each costs, the decision, and the consequences that fall out of it.

ADRs are **immutable once merged**. A decision that turns out to be wrong is not edited: a new ADR
supersedes it, and the old one is marked `Superseded by NNNN`. Where a decision still stands but a
*premise* recorded in its context turns out to be false, the new ADR **amends** rather than
supersedes, and the old one is marked `Amended by NNNN`. Supersession would claim a decision was
reversed; amendment says only that it was reached on one wrong fact and survives it. ADRs 0001 and
0004 carry such a marker, from [0007](decisions/0007-host-on-windows-with-docker-desktop-and-wsl2.md). This is why trade-off comparisons
live in ADRs rather than inline in the prose documents - the prose can then be rewritten freely
without destroying the record of why the shape is what it is.

| ADR | Decision | Status |
|---|---|---|
| [0001](decisions/0001-host-on-an-owned-always-on-x86-machine.md) | Host on an owned, always-on x86 machine | Accepted |
| [0002](decisions/0002-reach-the-server-from-the-internet.md) | Reach the server from the internet: diagnose, then branch | Accepted |
| [0003](decisions/0003-back-up-world-saves-off-the-host.md) | Back up world saves off the host | Accepted |
| [0004](decisions/0004-run-game-servers-as-containers.md) | Run game servers as containers | Accepted |
| [0005](decisions/0005-describe-titles-with-a-declarative-manifest.md) | Describe titles with a declarative manifest | Accepted |
| [0006](decisions/0006-give-friends-a-control-plane.md) | Give friends a control plane, starting with read-only status | Accepted |
| [0007](decisions/0007-host-on-windows-with-docker-desktop-and-wsl2.md) | Host on Windows 11 Home, with the Linux layer in Docker Desktop and WSL2 | Accepted |
| [0008](decisions/0008-implementation-stack-and-manifest-syntax.md) | Implementation stack and manifest syntax | Accepted |
| [0009](decisions/0009-reach-the-server-without-a-router-we-control.md) | Reach the server without a router we control | Accepted |

## Layout, and why it is this way

```
docs/
  README.md              this index
  scope-and-goals.md     the problem statement
  <concern>.md           one file per cross-cutting operator concern
  titles/<title>.md      one file per game, the concrete cases
  decisions/NNNN-*.md    append-only decision records
  sources.md             every external source, with dates
```

Three groups, because the documentation has three different rates of change:

- **The flat files in `docs/`** are the platform's cross-cutting concerns - networking, backups,
  supervision, architecture, control. Each answers one question an operator will actually ask, and
  each is roughly stable once written.
- **`titles/` is a directory from day one**, even though it holds a single file today. Titles are
  the axis this project grows along, and a per-title document is where the messy, game-specific,
  fast-rotting detail is quarantined so it does not leak into the generic documents. Making this a
  directory later would be a rename of every cross-reference in the repository.
- **`decisions/` is append-only** and therefore physically separate from documents that get edited.

## Writing conventions

Every document in this repository follows these. They are not stylistic preferences; each one
exists because of a specific way this kind of documentation fails.

1. **English only**, throughout the repository.
2. **No em dashes.** Use a plain `-`.
3. **Every claim that can go stale carries its source and a date, at the point of the claim.** A
   port number, a version, a path, a system requirement, a vendor's free tier: all of these have
   rotted in every guide older than a year, and a reader cannot tell a current fact from a stale
   one unless the document says when it was true.
4. **Primary sources outrank secondary ones.** Iron Gate's own documentation, Valve's SteamCMD
   documentation, and a project's own README beat any hosting company's blog post. Where only a
   secondary source exists, the document says so explicitly rather than laundering it.
5. **Every document opens with `Status` and `Last reviewed`.** A document nobody has re-read since
   the game's last major patch is a liability, and this line is what makes that visible.
6. **Trade-offs are compared, not asserted.** Where there is a real choice, the alternatives, what
   each costs, and a recommendation all appear. A document that only states the winner has thrown
   away the information the reader needs when the winner does not fit their situation.
7. **Code fences in `docs/` are illustrative only.** No snippet in this directory is a file to be
   extracted and run: it is there to show the shape of a command or a file, and the real thing
   lives outside `docs/`. The repository did once contain nothing executable at all, and
   [ADR 0008](decisions/0008-implementation-stack-and-manifest-syntax.md) ended that. The
   convention survives the change because its purpose was never that the repository be inert; it
   was that **a reader never has to guess whether a fence is documentation or the artifact**. In
   `docs/`, it is always documentation. Where a document describes something real, it links to the
   file rather than reproducing it, so the two cannot drift.
