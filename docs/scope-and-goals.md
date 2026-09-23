# Scope and goals

> Status: accepted
> Last reviewed: 2026-09-22

## The problem

A group of friends plays Valheim together. The world is hosted by one of them, from their own
machine, which means:

- The world only exists while that one person's computer is on.
- Nobody can play unless that person is home, awake, and has launched the game.
- The only copy of the save that matters lives on one person's disk, protected by whatever backup
  habits that person happens to have.

The first two are an availability problem and they are annoying. The third is a durability problem
and it is the serious one. A shared world is hundreds of hours of a group's time, and it is
currently one failed SSD, one reinstalled operating system, or one friendship going quiet away
from ceasing to exist.

The project exists to move the world off any individual's machine and onto something that is
always on, backed up, and operable by the group rather than by one person.

## Goals

| # | Goal | Why it matters |
|---|---|---|
| G1 | The world survives the loss of any single machine, including the host | This is the real problem. Everything else is convenience. |
| G2 | The server is reachable and playable without the owner being present | Removes the human single point of failure. |
| G3 | Friends can start, stop and check the server themselves | Without this, the owner has simply replaced the previous host as the bottleneck. |
| G4 | Game updates and restarts do not damage the world | The most common way self-hosted worlds die is a bad shutdown or a half-applied update. |
| G5 | Adding a second game is a configuration change, not a redesign | The group will not stay on one game forever. |
| G6 | Zero recurring cost, or close to it | A constraint the owner set. It rules out the easy answers and shapes the networking. |

## Actors

Two roles, with genuinely different needs. Conflating them is how self-hosted setups end up with a
shared SSH key in a group chat.

**The owner** physically has the machine. Comfortable with Linux, a shell and a router admin page.
Installs and configures things, holds the credentials, and is the only person who can fix a broken
host. Wants to stop being the person everyone waits for.

**The friends** are players. They should need no shell access, no VPN expertise and no credentials
beyond an identity they already have. Their entire required vocabulary is "is it up", "start it",
"stop it", and "how do I connect". Some may be on consoles, where installing anything at all is
not an option.

## Hard constraints

These were decided before this documentation was written, and the documents are built on top of
them rather than re-litigating them. See [ADR 0001](decisions/0001-host-on-an-owned-always-on-x86-machine.md).

- **The host is an always-on x86 PC or mini-PC the owner already owns.** Not a VPS, not a rented
  game host, not an ARM single-board computer.
- **It runs Linux and already has Docker available.**
- **It sits on a domestic internet connection**, behind a household router, with whatever the local
  ISP provides. Whether that includes a routable public address is not yet known.
- **No recurring spend.** A one-off is acceptable; a monthly bill is not.

The combination of the first and third constraints is what makes this project interesting rather
than trivial. A VPS would make the networking a non-issue and the durability a solved problem, and
would cost money every month forever. Hosting at home means the networking has to be solved
properly, and it is the part of this documentation that most guides get wrong.

## Non-goals

Stated so that the implementation which follows this documentation does not quietly grow into them.

- **Not a hosting business.** One household, one group of friends, a handful of concurrent players.
  Nothing here needs to scale to tenants, quotas or billing.
- **Not a mod platform.** Modded Valheim is out of scope for the first pass. It changes the update
  story substantially and deserves its own decision when it is actually wanted.
- **Not high availability.** A single machine at home will have outages: power cuts, ISP work, a
  failed disk. The goal is that an outage is *recoverable and bounded*, not that it never happens.
  Chasing real HA at home costs more than it returns here.
- **Not a competitor to the game's own hosting.** Where a title ships something official that
  solves a problem, the platform uses it rather than reimplementing it.
- **Not a general-purpose home server.** This documents game servers. Media, storage and home
  automation on the same box are somebody else's document.

## Out of scope for this documentation specifically

This repository is research and design. It contains **no implementation of any kind** - no compose
files, no unit files, no scripts, no application code. Those are a separate piece of work which
this documentation is the input to.

Also out of scope here: buying or configuring any real infrastructure, choosing or registering a
domain name, and touching the owner's router. This documentation describes what would need to be
done and why. It does not do it.

## How to tell if this documentation succeeded

These are the criteria the rest of the repository is measured against.

1. Someone who owns an always-on x86 machine and knows their way around Linux can follow the
   Valheim document from a bare machine to friends connected, **including the networking**, without
   needing a source outside this repository.
2. The generic platform design is written down, and the boundary between what is shared across
   games and what is specific to one game is explicit and justified by evidence rather than
   assumed.
3. Every real choice in the design has its alternatives, their costs, and a recommendation written
   down - not just the winner.
4. A reader can tell, for any fact that might have rotted, where it came from and when it was true.
5. A reader who loses the host machine entirely can tell, from these documents, exactly how to get
   the world back.

Criterion 5 is the one that matters most, because it is the one the whole project was started for.
