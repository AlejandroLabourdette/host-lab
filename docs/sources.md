# Sources and staleness

> Status: living
> Last reviewed: 2026-09-22

Every external source this documentation relies on, with what it supports and when it was read.
Convention 3 in [`README.md`](README.md) requires that claims carry their source at the point of
the claim; this page is the consolidated view, so a future reader can re-verify the whole set
without re-reading every document.

**All sources were accessed 2026-09-22.**

## Why this page matters more than usual

Valheim reached 1.0 on **2026-09-09** and had shipped **1.0.15 by 2026-09-18**. That is roughly
fifteen releases in nine days, and one of them changed the on-disk world format. This
documentation was written thirteen days after 1.0.

Two consequences:

1. **Anything version-specific here has a short shelf life**, and the version-specific parts are
   the operationally dangerous ones.
2. **Almost every Valheim guide on the open web predates 1.0** and is confidently wrong about
   saves. That includes sources that were correct when written. A guide with no date is unusable.

## Primary sources

Vendor and standards documentation. These outrank everything below them.

| Source | Publisher | Published | Supports |
|---|---|---|---|
| [A Guide to Dedicated Servers](https://www.valheimgame.com/support/a-guide-to-dedicated-servers/) | Iron Gate | 2024-04-11 | Launch parameters, Linux prerequisites, glibc floor, save paths, `-savedir`, permission list files and the `permittedlist.txt` all-or-nothing behaviour, port range, crossplay needing no port forwarding, stop with Ctrl+C |
| [Valheim 1.0 FAQ](https://www.valheimgame.com/support/valheim-1-0-faq/) | Iron Gate | 2026-09 | Old saves remain playable, biome generation caveat, crossplay across all platforms, hammer mode blocking achievements |
| [Patch 1.0.15](https://www.valheimgame.com/news/patch-1-0-15/) | Iron Gate | 2026-09-18 | The 1.0 world conversion bug that damaged item levels, fixed in 1.0.12. Evidence that conversions are risky |
| [Valheim news index](https://www.valheimgame.com/news/) | Iron Gate | ongoing | Current version and release cadence |
| [RFC 6598](https://datatracker.ietf.org/doc/html/rfc6598) | IETF | 2012-04 | `100.64.0.0/10` is Shared Address Space for carrier-grade NAT. The CGNAT diagnostic |
| [Tailscale pricing](https://tailscale.com/pricing) | Tailscale | current as of 2026-04-08 | Personal plan: 6 users, 100 devices, unlimited user devices |
| [Tailscale subnet routers](https://tailscale.com/kb/1019/subnets) | Tailscale | ongoing | What a subnet router reaches, direct peer-to-peer preference, its limitations |
| [playit.gg](https://playit.gg/) | playit.gg | current | Free tier exists, custom TCP/UDP is Premium at $3/month, 19 datacentres, players install nothing |
| [LinuxGSM Valheim](https://linuxgsm.com/servers/vhserver/) | LinuxGSM | ongoing | Valheim supported as `vhserver`; monitor, update and alerting features |

## Secondary sources

Community wikis, project documentation and issue trackers. Used where no primary source exists,
and **flagged as secondary at the point of use** in each document.

| Source | Kind | Supports | Why not primary |
|---|---|---|---|
| [Valheim Wiki, Dedicated servers](https://valheim.weirdgloop.org/w/Dedicated_servers) | Community wiki | **UDP** for 2456 and 2457, the Steamworks TCP port that must not be forwarded, `worlds_local` path, crossplay join codes and its lag/timeout caveat | Iron Gate states the port range but never the protocol |
| [lloesche/valheim-server](https://github.com/lloesche/valheim-server-docker) | Project README | **The 1.0 conversion is one-way**, UDP 2458 under crossplay, backup and restart scheduling defaults, a 120 second stop timeout | Iron Gate has not documented the conversion |
| [valheim-server-docker issue #802](https://github.com/community-valheim-tools/valheim-server-docker/issues/802) | Issue tracker | The silent-autosave-failure case: `0644` on the new per-world directories broke every save while the container reported healthy | A real incident, not documentation |
| [Valheim 1.0 world folder format](https://www.gameserverkings.com/knowledge-base/valheim/valheim-save-location/) | Vendor knowledge base | The 1.0 directory layout: `_main.N.fwl2`, `.db2`, `.chunks`, `.ok`, `.chunk`, the generation counter | **Iron Gate publishes no save-format reference at all** |
| [systemd unit gist](https://gist.github.com/cnrat/3605f9892ec535297030fc173d180651) | Community gist | `KillSignal=SIGINT`, the basis for the SIGTERM-is-unreliable caveat | Iron Gate documents Ctrl+C, not signal semantics |
| [LinuxGSM #4060](https://github.com/GameServerManagers/LinuxGSM/issues/4060), [#4821](https://github.com/GameServerManagers/LinuxGSM/issues/4821) | Issue tracker | Valheim query-based monitoring breaking after game updates. Evidence that game-specific health checks are fragile | Real incidents |

### Claims resting only on diffuse community consensus

No single citable source. Treated as weaker than anything above, and flagged in place.

| Claim | Where | How to verify properly |
|---|---|---|
| RAM sizing by group size and world age | [`titles/valheim.md`](titles/valheim.md) | Measure your own world. Iron Gate publishes client requirements, not server sizing |
| Valheim's simulation is largely single-threaded | [`titles/valheim.md`](titles/valheim.md) | Observe per-core load on a busy server |
| `-backupshort` and `-backuplong` defaults | [`save-data-and-backups.md`](save-data-and-backups.md) | The server's own startup log |
| Password rejected when it appears in the server or world name | [`titles/valheim.md`](titles/valheim.md) | Try it. The server logs `Error bad password:` and exits |
| `-preset` after `-modifier` silently discards modifiers | [`titles/valheim.md`](titles/valheim.md) | Set both and inspect the world's actual modifiers |
| World modifier preset names | [`titles/valheim.md`](titles/valheim.md) | The in-game world creation screen |
| Per-title facts for Minecraft, Palworld, Satisfactory, Enshrouded | [`platform-architecture.md`](platform-architecture.md) | Each title's own wiki. These support an argument about *shape*, so an error in one cell would not overturn the conclusion |

## Staleness policy

### Re-verify when one of these happens

Event-driven rather than calendar-driven, because these documents rot on events, not on time.

| Trigger | Re-check |
|---|---|
| **A Valheim major version** | Save format, conversion behaviour, launch parameters, ports. Assume the save format changed until proven otherwise |
| **Any Valheim patch, while 1.0.x is moving this fast** | The news index, for anything touching dedicated servers or saves |
| **Crossplay or platform support changes** | The backend comparison in [`networking.md`](networking.md) and the platform list |
| **The ISP or router changes** | The whole connection diagnostic in [`networking.md`](networking.md). Do not assume the connection type carried over |
| **Before relying on any free tier** | Tailscale and playit.gg limits. Free tiers move, and both are load-bearing for a CGNAT branch |
| **Adding a title to the platform** | Fill in a full manifest from that title's own sources. Do not extrapolate from the table in [`platform-architecture.md`](platform-architecture.md) |
| **Any change to the save format or the backup job** | Re-run the restore drill in [`save-data-and-backups.md`](save-data-and-backups.md) |

### The highest-risk claims

If time is short, these are the ones where being wrong costs the most.

1. **The save format and what a complete save looks like.** Rests on a secondary source because
   Iron Gate publishes no format reference, changed recently, and getting it wrong means backups
   that do not restore. Verify against a real installation before writing anything that parses it.
2. **SIGINT as the graceful stop signal.** Secondary, and getting it wrong loses up to 30 minutes
   of play on every stop. Verify by stopping a server and checking the `.ok` marker.
3. **Port protocols.** Secondary. Getting it wrong means a server that looks correct and is
   unreachable.
4. **Whether the connection is behind CGNAT.** Not a documentation fact at all, but the one that
   invalidates the most downstream work if it changes.

### Conventions for adding sources

- **Prefer primary.** Iron Gate, Valve, a standards body, or a project's own repository.
- **Record the publication date, not just the access date.** A 2024 page read today is a 2024 fact.
- **Where only secondary sources exist, say so in the document**, not only here. A reader following
  a runbook should not have to come back to this page to learn a claim is uncorroborated.
- **A source with no date is not a source.** Most Valheim guides on the web have no date and are
  now wrong about saves. Find something dated, or mark the claim as consensus in the table above.
