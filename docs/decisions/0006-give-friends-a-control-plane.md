# 0006 - Give friends a control plane, starting with read-only status

> Status: accepted
> Date: 2026-09-22

## Context

The project exists because nobody can play unless one particular person is at their computer.
Moving the world to an always-on machine fixes the availability half. If the owner remains the only
person who can start, stop or even check the server, the dependency has been renamed rather than
removed, and goal G3 in [`scope-and-goals.md`](../scope-and-goals.md) is unmet.

Examining the actual requests, documented in [`remote-control.md`](../remote-control.md), produced
a result that changed the decision: **three of the four real needs are information, not control.**
"Is it up", "how do I connect", "what is the current join code" and "is anyone playing" are all
read-only. Only "the group moved to another game and Valheim is holding the RAM" needs authority.

Two constraints narrow the design:

- **Valheim has no remote administration channel.** No RCON, no console socket. Two of the five
  titles surveyed in [`platform-architecture.md`](../platform-architecture.md) are in the same
  position. Control must therefore come from the container runtime.
- **Stop is destructive.** A Valheim server killed rather than stopped loses up to `-saveinterval`
  of play, 30 minutes by default. A stop button is a data-destroying operation handed to people
  who cannot see what it does.

## Options considered

### A. Nothing. Owner-only, over SSH

- **For:** zero work, zero attack surface.
- **Against:** does not meet G3. The owner is still the bottleneck.
- **Verdict:** rejected as an end state, though it is what exists today.

### B. Always-on, plus read-only status published where the group already talks (chosen first step)

- **For:** addresses three of the four real needs. Grants no authority to anyone, so nothing can
  destroy a world. Nearly no attack surface. Small enough to actually get built.
- **Against:** does not cover freeing the machine for another title.
- **Verdict:** the right first step, because it is almost all of the value and none of the risk.

### C. Full start/stop control for friends

- **For:** meets G3 completely.
- **Against:** exposes the destructive operation. Needs real identity, authorization, an audit
  trail and confirmations. Every one of those is work, and skipping any of them is how it goes
  wrong.
- **Verdict:** necessary eventually, not yet. The need becomes real when a second title competes
  for the machine.

### D. Adopt an existing panel

- **For:** users, permissions, console and start/stop already exist and are what panels are good at.
- **Against:** a panel, a database and a daemon to run and patch for a group of six.
  [ADR 0004](0004-run-game-servers-as-containers.md) rejected it as the platform *foundation*, which
  is a different question from whether it is a good control plane.
- **Verdict:** the right answer if the control plane outgrows a bot. Not the right starting point.

### E. A shared password on a simple web endpoint

- **For:** trivially simple.
- **Against:** the password reaches a group chat and stays there. Not revocable per person, never
  rotated, and every action is anonymous, which destroys the audit trail that makes a destructive
  operation acceptable at all.
- **Verdict:** rejected. This is the option that feels adequate and is not.

## Decision

**Build the control plane in stages, cheapest and safest first.**

1. **Now: always-on plus read-only status.** The server runs continuously; there is nothing to
   start. Publish liveness, connection details, player count, the crossplay join code and the last
   backup result to where the group already talks. No authority granted.
2. **When a second title makes it real: add start and stop**, with identity from Discord or from an
   overlay VPN, whichever the group already uses. Never a shared password.
3. **Only if it outgrows that: adopt a panel** rather than growing a custom one.

**Stop carries mandatory conditions** wherever it is eventually built: it uses the title's graceful
stop and waits for it; a timeout escalating to a kill is an incident, not a success; it refuses or
requires explicit confirmation while players are connected; it triggers or confirms a backup first;
and it is attributable to a person.

## Why staged rather than built once

The project's guidance is to start with the simplest direct path and add machinery only when a
concrete blocker or repeated need justifies it. Applied here, the split is unusually clean: the
information needs exist today and are cheap and safe, while the control needs do not exist yet and
are expensive and dangerous. Building the dangerous half first, before anyone needs it, risks the
exact asset the project was created to protect in service of a feature nobody is using.

The staging is also not speculative. Stage 2's trigger is a specific, observable event - the group
running a second title on the same machine - not a guess about future demand.

## Consequences

1. **Crossplay makes stage 1 mandatory rather than optional.** The join code regenerates on every
   restart, so without automatic publication a restart silently locks out everyone who was not
   watching. See [ADR 0002](0002-reach-the-server-from-the-internet.md).
2. **Scheduled restarts are coupled to this.** They are harmless if the new code is announced
   automatically and harmful if it is not
   ([`always-on-operation.md`](../always-on-operation.md)).
3. **The control plane acts on containers, not games**, because two of five titles offer no game
   control interface. This makes it title-agnostic for free and ties this decision to
   [ADR 0004](0004-run-game-servers-as-containers.md).
4. **Some things are permanently unavailable.** No in-game restart warning, no kick, no console for
   Valheim. Announcements happen out of band.
5. **The state reader and the action executor are separate components**, and only the executor has
   authority. Stage 1 ships the reader alone, which is what makes stage 1 safe.
6. **Identity must be revocable per person.** This is the concrete requirement that rules out the
   shared password, and it should be checked against any option before adoption.

## Revisit if

- The group runs several titles on the machine, which triggers stage 2 by definition.
- The owner starts wanting per-player permissions, quotas or a console, which is the point where a
  panel stops being overkill.
- Iron Gate adds a remote administration channel to Valheim, which would change what the control
  plane can offer and make in-game warnings possible.
