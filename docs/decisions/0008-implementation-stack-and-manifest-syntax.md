# 0008 - Implementation stack and manifest syntax

> Status: accepted
> Date: 2026-09-22

## Context

[ADR 0005](0005-describe-titles-with-a-declarative-manifest.md) decided that each title is
described by a declarative manifest interpreted by shared machinery, and that the manifest is
**data, not code**. It deliberately stopped there.
[`platform-architecture.md`](../platform-architecture.md) says why, twice: the title contract is
"written as a shape, not a schema, because committing to a syntax is an implementation decision
that has not been made yet", and "this repository is documentation; the implementation is a later
ticket".

This is that ticket, and this record makes those decisions.

Every one of them is weighed against the project's standing guidance: prefer quality, simplicity,
robustness and long-term maintainability over what is cheapest to build today, and start with the
simplest direct path rather than building machinery before a concrete need justifies it. Those two
pull in opposite directions often enough that saying which won, and why, is the useful part.

Nothing here is a large decision on its own. Together they set what every later change to this
repository has to live inside, which is why they are recorded rather than just done.

## The language of the shared machinery

The work is parsing a declaration, validating it hard, rendering it into runtime arguments,
walking a save directory to decide whether a copy is consistent, and talking to two HTTP APIs. It
is almost entirely I/O orchestration and data validation. There is no hot path.

| | **Python** | Go | Bash | TypeScript |
|---|---|---|---|---|
| Fit for the work | Strong. Validation and file walking are its centre | Good, more code for the same result | **Fails on the validation and consistency logic** | Good |
| Runtime on the host | A container, same as everything else | Single static binary | Already there | A container |
| Testing | pytest | Good | Painful, and this is logic that must be tested | Good |
| Already on the developer machine | Yes | No | Yes | No |

**Bash is the one worth taking seriously and rejecting explicitly**, because the project's guidance
points at it: it is the simplest direct path, and much of this job is running `docker` and
`restic`. It fails on the two pieces that carry the actual risk. Deciding whether a Valheim save is
a consistent copy means parsing generation numbers out of filenames and matching `.ok` markers
against them, and getting that wrong means a backup that does not restore. That is logic that has
to be unit tested against fixtures, and shell is where such logic goes to rot untested.

Go's single static binary is a real advantage for a thing that must keep working for years with no
maintenance. It loses because the platform already runs everything in containers
([ADR 0004](0004-run-game-servers-as-containers.md)), so "no runtime to install" buys nothing here,
and the same logic is more code to write and read.

**Decision: Python, currently 3.13, managed with `uv`, running inside a container on the host.**

Running it in a container rather than natively on Windows is the part worth defending. It costs an
indirection. It buys that ADR 0004's argument, that the host stays clean and rebuildable, holds for
the platform itself and not only for the games it supervises, on a host
([ADR 0007](0007-host-on-windows-with-docker-desktop-and-wsl2.md)) that is somebody's daily driver
and will be reinstalled one day.

**One exception, deliberately.** [`tools/udpecho`](../../tools/udpecho/README.md) is stdlib-only
and avoids 3.10+ syntax, because half of it runs on a phone, a friend's laptop, or whatever is to
hand during a network problem. A diagnostic that needs the environment installed before it can
diagnose the environment is not a diagnostic.

## The manifest syntax

The manifest is the thing ADR 0005 is really about, so this is the decision with the longest
shadow.

| | **YAML** | TOML | JSON |
|---|---|---|---|
| Comments | Yes | Yes | **No** |
| Nested structures | Natural | Awkward beyond two levels | Natural |
| Type surprises | Real, and well known | Few | Few |
| Diff quality in review | Good | Good | Noisy |

**JSON is ruled out by one requirement, and it is not a stylistic one.** ADR 0005 states that the
declaration "is reviewable, diffable, and doubles as the documentation of how that title works".
The three fields that ADR defends hardest are exactly the ones that are incomprehensible without a
comment carrying a source URL and a reason: `config_hazards` is a list of file paths that means
nothing without "Steam overwrites this on every update"; `state_consistency` is a filename pattern
that means nothing without "this marker is how you tell a complete save from one in flight"; and
`admin: null` reads as an oversight rather than a finding unless something says "Valheim has no
remote administration channel at all". A format that cannot carry that turns the manifest back into
an opaque configuration file, which is the outcome ADR 0005 exists to avoid.

TOML is genuinely safer per token, and its flat key-value core would suit `acquire` and `stop`
well. It loses on `ports`, which ADR 0005 consequence 2 already says must carry a per-port
"remapping permitted" flag, and which in TOML becomes an array of tables that reads worse than the
equivalent YAML for anyone skimming to answer "which ports does this game need".

YAML's type coercion is a real cost and it is paid in the next section rather than waved away.

**Decision: YAML.**

## How the manifest is validated

YAML will turn `no` into a boolean, `2456` into an integer and `1.0.15` into a string that looks
like a float to the next reader. Choosing YAML without a hard schema is choosing those bugs.

| | **Pydantic models** | `jsonschema` against a hand-written schema | Hand-rolled checks |
|---|---|---|---|
| Error messages | Names the field and the reason | Names a JSON pointer | Whatever we write |
| Schema for other tools | Generated from the models | The schema is the source | None without extra work |
| Code to maintain | Model definitions only | Schema plus glue | All of it, roughly 150 lines |
| Dependency | One | One | None |

Hand-rolling is the option the project's guidance nudges toward, and it is rejected on the specific
grounds that error quality is the whole point here. A manifest is edited by someone adding a title
at most a few times a year, from documentation, under no pressure to remember conventions. The
difference between "validation failed" and "ports[1].remap_allowed: field required, and it must be
explicit because Satisfactory cannot remap its standard port" is the difference between a schema
that teaches and one that obstructs.

**Decision: Pydantic models as the source of truth, with a JSON Schema exported to
`titles/schema.json`** so an editor or a CI job can check a manifest without running our code.

This is a dependency that removes code rather than adding a layer, which is the test the project's
guidance actually asks.

## How the platform talks to the container runtime

[ADR 0005](0005-describe-titles-with-a-declarative-manifest.md) is explicit that the platform's
control operations must come from the container runtime rather than the game, because two of the
five titles surveyed expose no control interface at all. So this interface is load-bearing.

- **The `docker` CLI, with `--format '{{json .}}'`.** No dependency. The command is the one an
  operator types when debugging at 2am, which means the platform's behaviour and the human's
  intuition stay in the same place. Costs parsing text, though `--format` makes it structured text.
- **The Docker SDK for Python.** Structured objects, no parsing. Costs a dependency that tracks the
  daemon API, and a divergence between what the platform does and what a person would type.

**Decision: the CLI.** The deciding argument is debuggability under an unfamiliar host. ADR 0007
put this on Windows, WSL 2 and Docker Desktop, where more things are unusual than usual, and a
failing `docker inspect` that can be copied out of a log and rerun by hand is worth more than typed
return values.

## The game server image

| | **Our own thin image** | The community reference container |
|---|---|---|
| Configuration source | The manifest | Its own environment-variable vocabulary |
| Supervision, backups, scheduled restarts | Ours, per the ADRs | **Its own, competing with ours** |
| Version pinning | The image tag is the Valheim version | Downloads at start; the tag is not the version |
| Maintenance | Ours | Someone else's, which is a real gift |
| Track record | None | Mature and widely used |

[`valheim-server-docker`](https://github.com/community-valheim-tools/valheim-server-docker) is
cited throughout this documentation and is good software. Adopting it would be the simplest direct
path, and that is the project's stated preference, so rejecting it needs a reason rather than a
taste.

The reason is that it already implements the things this ticket exists to build. It has a backup
scheduler, a restart scheduler and a supervisor, and this platform has its own because ADR 0003 and
ADR 0006 specify behaviours (a consistency check against `.ok`, an off-site encrypted copy with a
verified restore, a status reader with no authority) that are the project's whole point. Running
both means two schedulers stopping the same server, and configuration living in two vocabularies
with the manifest no longer the source of truth ADR 0005 requires.

The second reason is version pinning. [ADR 0004](0004-run-game-servers-as-containers.md)
consequence 5 says "image tags become the version-pinning mechanism, which makes binary rollback
easy", and [`always-on-operation.md`](../always-on-operation.md) leans on it again when it says
rolling back binaries is trivial with containers and awkward with SteamCMD. **That is only true if
the server is in the image.** A container that runs SteamCMD at startup has an image tag that
pins the wrapper and not the game, and the advantage the ADR claimed is not actually held.

**Decision: build our own image, with the server installed at build time and the tag carrying the
Valheim version.**

The costs are accepted and named: a slow, large build; an update means building an image rather
than running one command; and issue #802's lesson about file versus directory permissions is now
ours to get right rather than inherited from people who already got it wrong once and fixed it.

## The backup tool

ADR 0003 requires a local copy, an off-site copy that is **encrypted**, retention longer than the
time it takes to notice a problem, and a restore that has actually been performed.

| | **restic** | `tar` + `age` + our own retention | `rclone sync` |
|---|---|---|---|
| Encryption | Built in | Built in | Depends on backend |
| Retention and pruning | `forget --keep-*` | Ours to write | **None. It is a mirror** |
| Deduplication | Yes | No: a full copy per run | Yes, by file |
| Verify without restoring | `restic check --read-data` | Ours to write | No |
| Dependency | One static binary | Two, plus our code | One binary |

`rclone sync` is rejected outright and is worth naming because it is what people reach for: a sync
mirrors deletions and corruption to the far end, so it protects against losing the machine and not
against anything that damages the data. ADR 0003's retention requirement rules it out by itself.

The real comparison is restic against rolling our own, and here the project's guidance points the
same way as the engineering: hand-rolling retention and verification is *more* machinery, not less,
and it is machinery whose failure mode is a backup that does not restore.

**Decision: restic**, to Backblaze B2 or Cloudflare R2 for the off-site copy, chosen by the owner.
ADR 0003's "revisit if" anticipated deduplication becoming worth its complexity; at daily copies of
a growing world it already is.

**One consequence that belongs to the restore drill and not to this decision**: the restic
repository password must live somewhere off this host, or the off-site backup is an encrypted blob
nobody can open. See [`save-data-and-backups.md`](../save-data-and-backups.md).

## The stage 1 publisher

[ADR 0006](0006-give-friends-a-control-plane.md) stage 1 is read-only status published where the
group already talks, granting **no authority to anyone**. The group talks on Telegram.

Telegram has one mechanism, the Bot API, so there is no choice of transport. The choice is how much
of it to use:

- **Send and edit only.** `sendMessage` once, keep the `message_id`, `editMessageText` on every
  refresh. The channel carries one status message that stays current instead of a stream of noise.
- **Also receive**, via `getUpdates` or a webhook, so friends could type commands.

**Decision: send and edit only. The platform never calls `getUpdates` and registers no webhook.**

That is worth stating as a decision rather than as an omission, because it is what makes stage 1
safe by construction rather than by discipline. ADR 0006 consequence 5 separates the state reader
from the action executor and ships only the reader. A bot that never reads its own inbox **cannot
be instructed**, so there is no command surface to get authorization wrong on, no rate limiting to
forget, and a leaked token buys an attacker the ability to edit a status message. Stage 2 will have
to add receiving, and it will have to add identity and an audit trail at the same moment, which is
exactly the coupling ADR 0006 wanted.

**Scheduling: a long-running process with its own timers, not cron inside a container.** A cron job
in a container writes to a log nobody collects and fails silently, which is precisely the failure
mode [`always-on-operation.md`](../always-on-operation.md) says matters most here.

## Decision, in one place

| Axis | Chosen | The argument that decided it |
|---|---|---|
| Language | Python 3.13, `uv`, in a container | The consistency and validation logic must be unit tested; shell cannot be |
| Manifest syntax | YAML | Only format with comments, and ADR 0005 requires the manifest to document its title |
| Validation | Pydantic, JSON Schema exported | Error quality, for a file edited twice a year from documentation |
| Runtime interface | `docker` CLI with JSON output | Debuggable by hand on an unfamiliar host |
| Game image | Ours, server baked in, tag is the version | ADR 0004's rollback claim is only true if the server is in the image |
| Backup | restic to B2 or R2 | Retention and verification are required, and hand-rolling them is more machinery |
| Publisher | Telegram Bot API, send and edit only | Never reading its inbox makes stage 1 safe by construction |

### Repository layout

```
titles/valheim.yaml       the manifest. Data.
titles/schema.json        generated from the models, so a manifest is checkable without us
hostlab/                  the shared machinery
images/valheim/           the image, server baked in
deploy/                   compose, host scripts, the .env contract
tools/udpecho/            the UDP path prover
tests/
```

`titles/` is a directory from the start for the same reason `docs/titles/` is
([`README.md`](../README.md)): titles are the axis this grows along, and making it a directory
later renames every reference.

**The package is `hostlab` and not `platform`**, which is what the layered model in
[`platform-architecture.md`](../platform-architecture.md) would suggest. `platform` is a Python
standard library module, so a top-level package of that name shadows it for us and for anything we
depend on. The bug that produces is remote from its cause and arrives late, which is exactly the
kind this project keeps finding in other people's tooling. The layer is still called the platform
everywhere in prose; only the importable name differs.

## What this deliberately does not build

[`platform-architecture.md`](../platform-architecture.md) has a section called "What the platform
must not try to unify" written specifically to stop this ticket over-building. Restating the parts
this record could have violated and did not:

- **No universal configuration vocabulary.** The manifest describes Valheim in Valheim's terms:
  its flags, by their real names. It does not invent a `max_players` that maps onto four games.
- **No plugin or adapter interface.** ADR 0005 option B, rejected there and not smuggled back in.
  Valheim's oddities, including its password rules and the `-preset` before `-modifier` ordering,
  are expressed as declared constraints in the manifest rather than as per-title Python.
- **No executor, no start, no stop, no restart.** Stage 1 only.
- **No web UI, no panel, no database.**
- **No scheduler beyond timers in one process.** One machine, a handful of jobs.

## Consequences

1. **The manifest schema is now a compatibility surface.** `titles/schema.json` is generated, so it
   cannot drift from the models, but a field removed or renamed breaks any manifest using it.
2. **Adding a title stays a documentation exercise**, per ADR 0005 consequence 1. The test of that
   claim is whether a second title can be added without touching `hostlab/`, and the constraint
   mechanism is what has to hold for it to be true.
3. **Updating Valheim now means building an image.** Slower than the reference container's restart,
   and it is what buys a tag that is genuinely a version.
4. **Issue #802's permission bug is ours to not repeat.** The image must distinguish files from
   directories when setting permissions.
5. **The restic repository password is a new single point of failure**, and it is not on the host.
6. **A Telegram bot token exists**, and it must not enter the repository. It is write-only by
   construction, which bounds what a leak costs, but it is still a secret in a `.env` file.
7. **Python is in the always-on path**, and it is a dependency Go would not have added. Mitigated
   by it running in a pinned image rather than against a host interpreter.

## Revisit if

- **A title cannot be expressed without per-title code.** ADR 0005 already says one such title is
  an extension and two are evidence that its option B was right. The constraint mechanism decided
  here is the thing that would be failing.
- **The manifest outgrows YAML**, which in practice means someone wants conditionals or references
  in it. That is a signal it has stopped being data, not a reason for a templating language.
- **Maintaining the image stops being worth it**, for example if the reference container gains a
  mode that does supervision and nothing else. Its schedulers competing with ours is the objection,
  and that objection can go away.
- **Stage 2 arrives**, which forces the bot to read its inbox and therefore forces identity,
  authorization and an audit trail at the same time.
