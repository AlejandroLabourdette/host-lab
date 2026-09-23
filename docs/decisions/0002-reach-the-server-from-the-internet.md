# 0002 - Reach the server from the internet

> Status: accepted
> Date: 2026-09-22
> Amended by [0009](0009-reach-the-server-without-a-router-we-control.md): the router is
> not ours, which removes branch 3 whatever the connection type. The procedure stands; the
> branch needed a condition this record did not contemplate.

## Context

[ADR 0001](0001-host-on-an-owned-always-on-x86-machine.md) put the host on a domestic connection.
Friends elsewhere on the internet have to reach it. Whether that is trivial or impossible depends
on a fact nobody has checked yet: whether the ISP hands out a routable public IPv4 address or puts
the household behind carrier-grade NAT.

A second unknown compounds it. Valheim has two connection backends with opposite network
requirements, and which one is usable depends on whether any friend plays on a console or Game
Pass. That is also not yet known.

Two unknowns, each of which can invalidate a recommendation, mean **a single winner cannot honestly
be named here.** Writing "use port forwarding" would be wrong for a CGNAT household, and writing
"use Tailscale" would be wrong for a group with a PlayStation player. This ADR therefore decides a
*procedure* and a *branch*, which is the only decision the available evidence supports.

The options and their full costs are compared in [`networking.md`](../networking.md); this record
does not repeat that table.

## Decision

**Diagnose first, then branch. Prefer the cheapest option that satisfies the group's constraints,
and do not build infrastructure before proving it is needed.**

The branch, in evaluation order:

1. **Determine the connection type** by comparing the router's WAN address against the observed
   public address. A WAN address in `100.64.0.0/10` is carrier-grade NAT, conclusively.
2. **Determine whether any player is on a console or Game Pass.** If yes, `-crossplay` is
   mandatory, and with it port forwarding stops being required. The networking problem is then
   solved and the remaining work is publishing the rotating join code, which belongs to the control
   plane.
3. **If there is a public address (static or dynamic) and everyone is on Steam:** forward UDP 2456
   and 2457 to a DHCP-reserved host address, and add dynamic DNS if the address is not static. This
   is the recommended path when it is available, because it is the only one with no third party in
   the data path and the lowest achievable latency.
4. **If behind CGNAT:** ask the ISP for a public address first, since it is free to ask and
   collapses the problem. If refused, try `-crossplay` next, because it costs one flag and no
   infrastructure. Only if both fail, pick between an overlay VPN (all-PC groups willing to install
   a client), a tunnel service (nobody installs anything), and a relay VPS (a stable public
   endpoint is genuinely required and the third-party dependency is not acceptable).

**Verification is part of the decision, not an afterthought.** A configuration is not accepted until
an A2S query from outside the network answers. Generic UDP port checkers and `nc -vzu` do not
constitute evidence, for the reasons given in [`networking.md`](../networking.md).

## Why not simply pick one

- **Always port forward.** Fails outright behind CGNAT, which is common enough that the
  documentation would be useless to a meaningful share of readers, including possibly this one.
- **Always use an overlay VPN.** Cannot serve consoles at all, and imposes an install on every
  friend. Recommending it unconditionally would quietly exclude players.
- **Always use crossplay.** Tempting, because it makes this whole document optional. But it adds
  measurable latency, makes the group depend on a Microsoft relay that cannot be debugged locally,
  and introduces a join code that changes every restart. That is a real cost to pay when a direct
  path is available for free.
- **Always rent a relay VPS.** Works in every case, and is the only option here that always works.
  It also breaks the project's zero-recurring-cost constraint for a problem that is frequently
  solvable for nothing.

## Consequences

1. **The networking document leads with a diagnostic**, and readers cannot follow it linearly
   without first establishing which branch they are on. That is deliberate.
2. **The crossplay decision is upstream of the networking decision** and has to be settled first.
   It is a game-level flag with network-level consequences, which is easy to miss.
3. **If crossplay is chosen, this project inherits the join code problem.** The code regenerates on
   every server restart, so restarts become user-visible events and the control plane must be able
   to publish the current code. This is a direct dependency created by a networking decision.
4. **Whatever is chosen, verification is by A2S query from outside the network.** Any other
   evidence is inadmissible.
5. **Recurring cost is accepted only as a last resort**, and only for the relay VPS or a tunnel
   Premium tier, never for moving the game server itself off the owned machine.

## Revisit if

- The connection type changes, which for a domestic line usually means an ISP migration or a
  router replacement. The diagnostic should be re-run, not assumed.
- A console player joins a group that had settled on an overlay VPN. That immediately invalidates
  branch 3 and forces crossplay.
- Iron Gate changes the crossplay backend or its port requirements. This is version-sensitive, and
  Valheim is currently patching frequently.
