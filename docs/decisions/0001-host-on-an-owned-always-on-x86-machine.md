# 0001 - Host on an owned, always-on x86 machine

> Status: accepted
> Date: 2026-09-22
> Decided by: the project owner, before this documentation was written

## Context

The group needs a place to run game servers that is not any player's gaming PC. Four shapes were
available, and the choice constrains almost everything downstream: whether the networking is a
solved problem or the hardest part of the project, whether durability is somebody else's job, and
whether there is a monthly bill.

The owner set one non-negotiable: **no recurring cost**. That is a real constraint and not a
preference, because a game server for a group of friends is exactly the sort of thing that gets
cancelled when the group stops playing for two months and nobody wants to keep paying.

## Options considered

### A. An always-on x86 machine the owner already owns (chosen)

A PC or mini-PC in the owner's home, running Linux, powered on permanently.

- **Cost:** zero recurring, beyond electricity. A machine drawing 20 W costs on the order of a few
  currency units per month depending on local rates - noise compared to any hosted option.
- **Performance:** typically much better than the entry-level VPS the same money would not buy.
  Valheim's simulation is largely single-threaded, so a desktop CPU's clock speed is worth more
  here than a cloud instance's core count.
- **Cost paid instead:** the networking. A domestic connection may have a dynamic address, may be
  behind carrier-grade NAT, and has an upstream bandwidth far below its downstream. All of this
  becomes the project's problem. It is the single largest consequence of this decision.
- **Also paid:** durability is entirely the owner's responsibility. Nobody else is taking
  snapshots. Power cuts, ISP outages and disk failure are all now in scope.

### B. A VPS

A small rented Linux instance.

- **Buys:** a static, routable public address. Port forwarding, dynamic DNS and CGNAT all stop
  existing as problems. Real upstream bandwidth. Someone else's power and cooling. Usually a
  snapshot facility.
- **Costs:** a bill every month, forever, which violates the stated constraint. Also, at the price
  point that would feel acceptable, the CPU is usually a shared, modestly-clocked core - the exact
  resource Valheim is most sensitive to.

### C. A managed game host

A company that runs Valheim servers as a product.

- **Buys:** the whole problem solved, today, by someone else. Networking, updates, backups and a
  friend-facing control panel are all included and are the product.
- **Costs:** a bill, again. More importantly it forfeits the *point* of the project: the world
  lives on a third party's disk under their terms, which is a variation of the original problem
  rather than a fix for it, and there is nothing generic to build.

### D. An ARM single-board computer

A Raspberry Pi class device.

- **Buys:** very low power draw, low one-off cost.
- **Costs:** fatal for this use. The Valheim dedicated server is distributed as an x86-64 Linux
  binary through Steam and there is no ARM build, so this would mean emulation - which destroys
  the single-threaded performance the game depends on. It also generalises badly: several of the
  titles the platform is meant to grow into are x86-only for the same reason.

## Decision

**Option A.** Host on an always-on x86 machine the owner already has, running Linux.

The deciding argument is not cost alone. It is that A and B differ mainly in *which* hard problem
the project inherits, and A's inherited problem - domestic networking - is solvable once, with
documentation, and then stays solved. B's inherited problem is a recurring bill, which is never
solved, only paid. C removes the project's reason to exist. D cannot run the software.

## Consequences

Accepted deliberately, and each one becomes an obligation on the documentation:

1. **Reachability from the internet is now a first-class problem.** Dynamic addresses, port
   forwarding, and the possibility of carrier-grade NAT all have to be diagnosed and handled. This
   is why the networking document leads with a diagnostic rather than with instructions.
2. **Durability is entirely ours.** There is no provider snapshot to fall back on. Backups must
   leave the host, and the restore path must be tested rather than assumed.
3. **Upstream bandwidth is the scarce resource,** not downstream. Domestic connections are
   asymmetric, and a game server is an upload-heavy workload.
4. **Physical reality is in scope.** Power cuts, the machine failing to come back up after one,
   dust, heat, and an unattended OS upgrade rebooting at the wrong moment are all now operational
   concerns.
5. **x86-64 is a platform requirement,** not an incidental detail. Any future title considered for
   this platform must ship an x86-64 Linux server build.

## Revisit if

- The connection turns out to be behind carrier-grade NAT *and* none of the escape hatches are
  acceptable. A cheap VPS used purely as a relay is a smaller concession than moving the whole
  server, and is covered as an option in the networking document.
- The group grows past the point a domestic upstream can carry.
