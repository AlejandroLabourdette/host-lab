# 0009 - Reach the server without a router we control

> Status: accepted
> Date: 2026-09-23
> Amends [0002](0002-reach-the-server-from-the-internet.md)

## Context

[ADR 0002](0002-reach-the-server-from-the-internet.md) decided a procedure and a branch rather
than a winner, which was the right call. Its branch turns on two unknowns: whether the ISP hands
out a routable address, and whether any player is on a console.

Both were answered. Nobody is on a console, so `-crossplay` is not mandatory on those grounds and
branch 3, direct UDP, was the recommended path. The observed public address is not in
`100.64.0.0/10`, so CGNAT was not indicated from that side.

**Then a third fact arrived that ADR 0002 never contemplated: the router is not ours.** The host
is a laptop on a **shared network** in a building, confirmed 2026-09-23. There is no
administration access, there will not be, and asking for it is not a route that exists here.

That is a different kind of obstacle from the two ADR 0002 branches on, and it is worth naming
precisely because it is easy to file under CGNAT and reason wrongly from there:

- **CGNAT is a property of the connection.** It makes port forwarding impossible.
- **A router that is not yours is a property of the situation.** It makes port forwarding
  *unavailable*, which lands in the same place by a different road.

The consequence is that **branch 3 is off the table regardless of whether there is CGNAT**, and so
the CGNAT diagnosis stops being the decision's input. It is still worth recording if it can be had
cheaply, because it would matter again if the host ever moved to a network the owner controls, but
nothing now waits on it.

ADR 0002's escalation order assumed the first move is to ask the ISP for a public address. On a
shared building network there is no such conversation to have, so the escalation starts one step
further down, at its options B, C and E.

## Options considered

All three remaining options work by having the host open a connection **outward**, which is what
makes them independent of a router nobody can configure.

### A. `-crossplay`, Valheim's own relay (chosen)

One launch flag. The server registers with Microsoft Azure PlayFab and players join with a numeric
code.

- **Costs nothing and installs nothing**, on the host or on any friend's machine. It is native to
  the game.
- **Works regardless of CGNAT, double NAT or an unknown router**, because nothing inbound is ever
  required.
- **Latency is relayed**, and the Valheim Wiki notes crossplay players are "more likely to
  experience lag, timeouts and disconnects" than those on a direct connection.
- **A dependency on a Microsoft-operated service that cannot be inspected or fixed locally.** If
  PlayFab has an outage, the server is unreachable and there is nothing to debug.
- **The join code regenerates on every server restart**, which is the real operational cost and
  the subject of most of this record's consequences.

### B. A tunnel service (playit.gg)

An agent on the host holds an outbound connection to a provider's edge, which rents a public
address and port and forwards traffic down the tunnel.

- **Free for Valheim**, which playit.gg lists among its built-in game presets.
- **Friends install nothing** and connect by address and port, exactly as they would to a directly
  reachable server. No join code to distribute, which is a genuine advantage over A.
- **Costs a second piece of software on the host** to keep running and updated, in the always-on
  path, and ADR 0007 already added two things there that a Linux desktop would not have had.
- **A harder third-party dependency than A.** The provider is not the game's vendor, its free tier
  can move, and if it does the server is unreachable with nothing to fix locally.
- **Verdict:** the strongest alternative, and the one to take if crossplay's latency turns out to
  be unacceptable in play. It trades a rotating code for a running agent.

### C. An overlay VPN (Tailscale)

- **Best latency of the three** once it negotiates a direct path, which is a real advantage for a
  game where latency is the thing being traded away.
- **Every friend installs and signs in to a VPN client.** That is the objection, and it is not a
  small one: it turns "click join" into "install this first", permanently, for everyone.
- Viable here only because the whole group is on Steam on PC. It would exclude a console player
  entirely, and the group's composition is not a guarantee about the future.
- **Verdict:** rejected for now on the imposition it places on friends, not on the technology.
  Worth revisiting if the group ends up running an overlay for another reason.

### D. A relay VPS

Rejected without much argument. It breaks the zero-recurring-cost constraint, and it does so to
buy control over a relay when option A supplies one for free and option B supplies one at no cost
either. It would only earn its keep if both relays were unacceptable and a stable public endpoint
were genuinely required.

## Decision

**Use `-crossplay`.** Publish the join code automatically, and treat that publication as part of
the reachability mechanism rather than as a convenience.

The deciding argument is not that crossplay is the best of the three in isolation. It is that it is
the only one that adds **nothing** to a host that has already accumulated more moving parts than
the design intended: Windows, WSL 2, Docker Desktop, auto-logon and a laptop's power behaviour, per
[ADR 0007](0007-host-on-windows-with-docker-desktop-and-wsl2.md). Options B and C each add another
component to the always-on path, and the always-on path is where this project's failures live.

The second argument is that **the cost crossplay imposes is one this project has already paid.**
The rotating join code needs a control plane that publishes it, and
[ADR 0006](0006-give-friends-a-control-plane.md) already decided to build exactly that, for
different reasons, and it is built. Choosing B instead would leave that work slightly less
justified rather than more.

## Consequences

1. **Stage 1 of the control plane is now mandatory, not optional.** ADR 0006 consequence 1 said
   this would happen if crossplay were chosen, and it has. A restart with no publication silently
   locks out everyone who was not watching, and restarts happen for reasons nobody chose.
2. **The platform must read the join code from the server's log**, because Valheim has no
   administration channel and the log is the only place it appears. That makes the status reader
   depend on a game's log format, which is exactly the coupling
   [`always-on-operation.md`](../always-on-operation.md) warns about when it notes LinuxGSM's
   query-based monitor breaking against a Valheim update. Accepted because there is no alternative
   source, and mitigated by the pattern living in the manifest as data rather than in code.
3. **Port forwarding is out of scope for this deployment.** The whole of
   [`networking.md`](../networking.md) step 2, and the DHCP reservation, do not apply. They stay in
   the document because they are correct for a reader who controls their router.
4. **The verification ladder loses two rungs and changes a third.** An A2S query from outside will
   not answer, because nothing is forwarded, and the server will not appear in the community
   browser. Reachability is proven by a friend connecting with the join code from outside the
   network, which is the only test that now means anything.
5. **`tools/udpecho` becomes a LAN diagnostic**, not a reachability proof. It keeps its value for
   answering "is anything listening at all", which is still the first question when the server
   stops working.
6. **`-public 0` is now the only sensible setting.** A public listing requires a reachable query
   port, so advertising the server would list something nobody can reach.
7. **Latency is worse than it would be on a direct connection, and that is the price paid.** If it
   turns out to be unacceptable in play, option B is the documented next move and does not require
   re-opening this decision.
8. **LAN players are unaffected.** Anyone on the same network can still connect directly by
   address, which makes local testing possible without going near the relay.

## Revisit if

- **The host moves to a network the owner controls.** That restores ADR 0002's branch 3, and the
  CGNAT diagnosis becomes load-bearing again rather than a curiosity. This is the single change
  that would most improve reachability.
- **Crossplay's latency proves unacceptable in play**, which is a measurement rather than a
  prediction. Option B is next.
- **Iron Gate changes the crossplay backend, its ports, or the log line the join code appears in.**
  The last of those would break the publication silently, which is the failure mode that matters
  most here.
- **A console player joins the group.** That would have forced crossplay anyway, so this decision
  becomes over-determined rather than wrong.
