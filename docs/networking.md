# Reaching the server from the internet

> Status: accepted
> Last reviewed: 2026-09-22

Hosting from home is the consequence of [ADR 0001](decisions/0001-host-on-an-owned-always-on-x86-machine.md),
and this is the document where that consequence has to be paid. Everything else in this project is
ordinary Linux operations. This part depends on what a particular ISP decided to do with its IPv4
addresses, and it is the step most likely to stop the project dead.

The decision is recorded in [ADR 0002](decisions/0002-reach-the-server-from-the-internet.md). This
document is the reasoning and the procedure behind it.

**Do not start by forwarding ports.** Start by finding out whether forwarding ports can work at
all. That is [step 1](#step-1-find-out-what-connection-you-actually-have).

## What the server actually puts on the wire

Valheim is not an HTTP service and the usual intuitions do not transfer.

| Port | Protocol | Purpose | Forward it? |
|---|---|---|---|
| 2456 (the `-port` value) | **UDP** | Gameplay RPC. The actual game traffic. | Yes |
| 2457 (`-port` + 1) | **UDP** | Steam query port, including A2S. Public lobby registration, metadata and server heartbeat. | Yes, always. See below |
| A random high port | TCP | Steamworks API, for Steam's own internal library use. | **No.** Never expose this. |

Source: [Valheim Wiki, Dedicated servers](https://valheim.weirdgloop.org/w/Dedicated_servers)
(community wiki, accessed 2026-09-22). Iron Gate's own
[guide to dedicated servers](https://www.valheimgame.com/support/a-guide-to-dedicated-servers/)
(2024-04-11) states the port range - "uses the specified Port AND specified Port+1" - but does not
state the protocol. The UDP attribution comes from the wiki and from the reference server
implementations, which is a secondary source, and it is flagged as such here rather than presented
as vendor documentation.

Three consequences worth stating plainly, because they are where most setups fail:

**Forwarding TCP does nothing.** A great many guides tell you to forward "TCP/UDP 2456-2458". The
TCP half is pure superstition. Valheim's gameplay and query traffic are both UDP, and the only TCP
the server opens is an outbound-initiated Steamworks connection on a random port that must not be
reachable from outside. Forwarding TCP 2456-2457 will not help a broken setup and adds exposure.

**Forward 2457 even for a private server.** It is tempting to skip it when running `-public 0`,
since nothing needs to be listed. Do not: the A2S reply on 2457 is the only admissible proof that
the network path works at all ([ADR 0002](decisions/0002-reach-the-server-from-the-internet.md)),
and without it a working server and a broken one look identical from outside. The listing is
controlled by `-public`, not by the port.

**The query port is separate from the game port, and they fail differently.** If UDP 2456 is open
but 2457 is not, players who type the address in manually can connect, but the server never appears
in anyone's server browser and looks offline. If 2457 is open but 2456 is not, the server appears
in the browser, shows a player count, and then refuses to let anyone in. That asymmetry is the
single most useful diagnostic signal in this document, and it is why the
[symptom table](#symptom-table) is organised around it.

**About port 2458.** Guides routinely say to forward 2456-2458, and the widely used
[valheim-server-docker](https://github.com/community-valheim-tools/valheim-server-docker)
container exposes UDP
2458 when crossplay is enabled (project README, accessed 2026-09-22). Iron Gate's own guide
documents only the port and port+1. In practice this rarely matters: 2458 is associated with the
crossplay backend, and the crossplay backend is precisely the one that does not need port
forwarding at all. Forward it if you like; do not expect it to fix anything.

## The two connection backends

Before any networking decision, one game-level decision changes the whole problem. Valheim ships
two different ways for a client to reach a server, and they have opposite network requirements.

| | Steam-native (default) | Crossplay (`-crossplay`) |
|---|---|---|
| Transport | Direct UDP, client to server | Relayed through Microsoft Azure PlayFab Party |
| Needs port forwarding | **Yes** | **No.** Iron Gate: crossplay "does not require Port Forwarding to be accessible from outside of your local network" |
| Who can join | Steam players only | Steam, Xbox, Game Pass PC, and since 1.0 (2026-09-09) PlayStation 5 and Nintendo Switch 2 |
| How players join | Server browser, or public IP and port | A numeric **join code**, or public IP and port, or the browser |
| Latency | Lowest available. One hop, no intermediary | Higher. Traffic goes via a relay. The Valheim Wiki states crossplay players "are more likely to experience lag, timeouts and disconnects" |
| Operational cost | The whole of this document | The join code **regenerates on every server restart** |
| Dependency | Steam | A Microsoft-operated relay that is outside your control and cannot be fixed by you when it breaks |

Sources: [Iron Gate, A Guide to Dedicated Servers](https://www.valheimgame.com/support/a-guide-to-dedicated-servers/)
(2024-04-11); [Valheim Wiki, Dedicated servers](https://valheim.weirdgloop.org/w/Dedicated_servers)
(accessed 2026-09-22). Both accessed 2026-09-22.

### Which one to use

This is not a decision to make in the abstract, because one input settles it:

- **If anyone in the group plays on a console or on Game Pass, crossplay is mandatory.** There is
  no other way for them to connect. The networking question then largely evaporates, and the
  problem to solve becomes the rotating join code instead - see
  [`remote-control.md`](remote-control.md), where publishing the current code is a control-plane
  responsibility.
- **If everyone is on Steam**, the choice is real: crossplay trades measurable latency and a
  third-party dependency for skipping this entire document. For a group whose ISP turns out to be
  hostile, that trade is often worth taking.

Because the group's platforms are not yet known, both are documented here as first-class paths and
neither is set as the default. The decision table in
[ADR 0002](decisions/0002-reach-the-server-from-the-internet.md) is written as a branch, not a
winner.

**One thing crossplay is not:** it is not a substitute for having any plan. It removes the port
forwarding requirement. It does not remove the need to know the server's state, to restart it, or
to distribute a code that changes every restart.

## Step 1: find out what connection you actually have

Almost every wasted evening in home hosting comes from skipping this. There are four possible
situations and only two of them allow port forwarding to work.

**The test.** Open the router's admin page and read the WAN address, the address the router itself
believes it has. Then, from any machine on the same network, ask an external service what address
your traffic appears to come from. Compare the two.

```
# what the outside world sees
curl -4 https://ifconfig.co
# also useful: is there working IPv6 at all?
curl -6 https://ifconfig.co
```

| Router WAN address | Means | Port forwarding |
|---|---|---|
| Matches the external address, and is stable over days | **Static public IPv4** | Works. No dynamic DNS needed. |
| Matches the external address, but changes | **Dynamic public IPv4** | Works, with dynamic DNS. |
| Inside `100.64.0.0/10` | **Carrier-grade NAT, certain.** That range is reserved by IANA for exactly this. | **Cannot work.** |
| A private range (`10/8`, `192.168/16`, `172.16/12`) and different from the external address | Double NAT. Either CGNAT, or a second router of your own in front | Cannot work until resolved. Check for your own extra router first: an ISP modem in router mode ahead of your router is a common and fixable version of this. |
| No IPv4 at all, only IPv6 | **IPv6-only or DS-Lite** | IPv4 forwarding cannot work. See below. |

Source for the CGNAT range: [RFC 6598](https://datatracker.ietf.org/doc/html/rfc6598), which
allocates `100.64.0.0/10` as Shared Address Space for service provider NAT. Accessed 2026-09-22.

**If the WAN address is in `100.64.0.0/10`, stop.** No amount of router configuration will make
port forwarding work, because the device that would have to forward the port belongs to the ISP
and is shared with thousands of other subscribers. Go to
[the CGNAT escape hatches](#when-port-forwarding-cannot-work). This is the single most common
reason a home game server never becomes reachable, and it is worth ten minutes to rule in or out
before spending an evening on the router.

**A DS-Lite or IPv6-only connection is a variant of the same problem.** IPv4 reachability is
provided, if at all, by a carrier translation device you do not control. Valheim clients on
IPv4-only connections will not reach an IPv6-only server, so in practice this behaves like CGNAT
and the same escape hatches apply.

**One caveat on the "stable over days" test.** Many connections keep the same address for weeks and
then change it during a line resync or a maintenance window. Do not conclude "static" from a single
observation; conclude it from the ISP's contract, or assume dynamic and use dynamic DNS anyway. The
cost of assuming dynamic when it is static is one unnecessary DNS record. The cost of the reverse
is the server silently becoming unreachable on a random Tuesday.

## Step 2: port forwarding, when it can work

### Give the host a stable address on the LAN first

A forwarding rule points at an internal address. If the host's address is assigned by DHCP and
changes after a reboot, the rule now points at whatever device inherited it, and the symptom is a
server that was reachable for a month and then was not. Fix this before creating the rule:

- Preferred: a **DHCP reservation** on the router, tying the host's MAC address to a fixed lease.
  The host keeps using DHCP, and the router guarantees the answer. One place to change, and it
  survives reinstalling the host.
- Alternative: a static address configured on the host, outside the router's DHCP pool. Works, but
  the knowledge now lives in two places that can disagree.

### The rules

Two rules, both UDP, both to the host's reserved LAN address:

```
UDP 2456 -> 192.0.2.10:2456     gameplay
UDP 2457 -> 192.0.2.10:2457     steam query, A2S, server browser listing
```

Keep the external and internal port numbers identical. Valheim advertises its own port to the Steam
lobby, and remapping the external port to something else produces a server that appears in the
browser advertising a port nobody can reach.

### Then check the host's own firewall

A forwarding rule delivers the packet to the host. It does not make the host accept it. If the host
runs `ufw`, `firewalld` or `nftables`, UDP 2456 and 2457 must be allowed there too. If the server
runs in a container, the container's port publishing must be UDP as well: publishing `2456:2456`
without `/udp` publishes TCP, which is the wrong protocol and produces a silently dead server. This
catches people constantly and produces exactly the same symptom as a missing router rule.

## Step 3: dynamic DNS, when the address moves

A dynamic public address works fine until it changes, at which point every friend has a stale
number. Dynamic DNS fixes the indirection: a name that a small client on the host keeps pointed at
the current address.

What to look for in a provider, rather than which provider to pick:

- **The updater runs on the host**, not on the router. Router-embedded DDNS clients are frequently
  limited to a fixed list of providers and fail quietly. A client on the host can be monitored like
  anything else on the host.
- **A short TTL**, on the order of a minute. A long TTL means the name keeps resolving to the old
  address for hours after a change, which is indistinguishable from the server being down.
- **An update mechanism you can drive yourself**, so failure is detectable and alertable rather
  than discovered by a friend.

Free options in this space (DuckDNS, and the DNS providers that expose a token-authenticated record
update API such as Cloudflare) all satisfy this. Registering a domain is explicitly out of scope for
this project, so a free subdomain is the expected answer.

**Two failure modes to design against, because both look like "the server is down":**

1. The address changed and the updater did not notice or could not reach the provider. Detect by
   comparing the resolved name against the observed public address on a schedule, and alert on
   disagreement. This is cheap and it is the difference between a five-minute outage and a
   weekend-long one.
2. The address changed and the name updated correctly, but a client still has the old value cached.
   Mitigated by the short TTL, and worth telling friends about once: "if it says it cannot connect,
   quit to the main menu and retry" resolves it.

## When port forwarding cannot work

CGNAT, DS-Lite, and a landlord's or campus network all land here. The problem is identical in each
case: nothing on the public internet can initiate a connection towards your host, so the host must
initiate the connection outwards, to something that is reachable, and traffic must return along
that path.

Five ways to do that, compared on what they actually cost.

### A. Ask the ISP for a routable public address

Worth doing first because it is often free or nearly so, and it makes the problem disappear rather
than routing around it.

- **Cost:** sometimes zero, sometimes a small monthly fee, sometimes a business tariff. A monthly
  fee conflicts with the project's zero-recurring-cost constraint.
- **Effort:** one phone call, and the result is either "done" or a clear no.
- **Failure mode:** none, if granted. If it is granted, everything above in this document applies
  and the rest of this section is unnecessary.
- **Verdict:** always the first thing to try. The cost of asking is ten minutes.

### B. Overlay VPN (Tailscale, or self-hosted Headscale)

Every participant joins a private WireGuard-based network. The server is reachable at a private
address inside it, regardless of what either end's ISP does.

- **Cost:** free at this size. Tailscale's Personal plan is "Up to 6 users" with "Unlimited user
  devices" and "Up to 50 tagged resources to start", at $1 per month per tagged resource beyond
  that ([Tailscale pricing](https://tailscale.com/pricing), accessed 2026-09-22; the page carries
  no publication date). **The figure that could actually bite this project is the tagged-resource
  allowance, not a device count**: an always-on server is normally enrolled with a tag, which makes
  it a tagged resource. Fifty is far more than this needs. Headscale removes the third party
  entirely at the cost of running it yourself, which needs a reachable host and is therefore
  circular unless one exists.
- **Latency:** the best of any option here, though not from the first packet. "All connections
  start as relayed through a DERP server, and Tailscale then tries to upgrade them to a direct
  connection", and "Direct connections usually provide the lowest latency and highest throughput,
  while relayed connections are a fallback when direct connectivity isn't possible"
  ([Tailscale connection types](https://tailscale.com/kb/1257/connection-types), accessed
  2026-09-22). A working setup settles on a direct path; one stuck on the relay is a performance
  problem to investigate rather than the normal case.
- **The cost that actually matters:** **every player must install and sign in to it.** This is a
  real imposition on friends and it is the reason this is not an automatic win. A subnet router on
  the host removes the requirement for devices that cannot run a client, but only for devices on a
  network that already routes through it, which does not help a friend in another house.
- **Fatal limitation:** **consoles cannot run it.** A PlayStation 5 or Switch 2 player cannot join
  an overlay network, and no subnet router arrangement changes that from their living room. If the
  group includes console players, this option cannot serve them and crossplay is the answer
  instead.
- **Also:** the server cannot be public. It will not appear in the Steam server browser to anyone
  outside the overlay. For a private group that is usually a feature.
- **Verdict:** excellent for an all-PC group willing to install one thing once. Useless for
  consoles.

### C. A tunnel service (playit.gg and equivalents)

An agent on the host holds an outbound connection to a provider's edge, which rents you a public
address and port and forwards traffic down the tunnel.

- **Cost: free for Valheim.** playit.gg lists Valheim among its built-in free game presets,
  alongside Minecraft, Palworld, Terraria and Factorio, and UDP tunnels are on the free tier.
  Premium, at $3/month, gates generic TCP, TCP+UDP, SSH and HTTPS tunnels plus some additional game
  presets ([playit.gg](https://playit.gg/), accessed 2026-09-22). For the title this documentation
  is built around, this option costs nothing. A future title with no preset, needing a generic TCP
  tunnel, would cost $3/month. Verify the current boundary before relying on it; free tiers rot
  faster than anything else cited here.
- **Effort on friends:** **none.** They receive an address and port and connect normally. This is
  the option's real advantage and it is a significant one.
- **Latency:** every packet is relayed via the provider's nearest datacentre, in both directions.
  Worse than direct, comparable to crossplay's relay. playit.gg advertises 19 datacentres across 5
  continents (accessed 2026-09-22), so the penalty depends heavily on where the group is.
- **Failure mode:** the provider is a hard dependency. If it has an outage, changes its terms, or
  the free tier moves, the server becomes unreachable and there is nothing to fix locally.
- **Trust:** all game traffic transits a third party.
- **Verdict:** the best option when friends must not have to install anything and consoles are in
  play but crossplay is not wanted. Weakest on dependency risk.

### D. A cheap relay VPS with WireGuard

Rent the smallest available VPS purely for its public address. The host dials a WireGuard tunnel
out to it, and the VPS forwards UDP 2456-2457 down the tunnel.

- **Cost:** a few currency units a month, and it is the *smallest possible* violation of the
  zero-recurring-cost constraint, since the VPS needs no CPU and no disk and the game still runs at
  home. It is still a violation, and for Valheim specifically option C is free, which is most of
  why this ranks below it.
- **Latency:** one extra hop, and the geography is yours to choose, which is the advantage over C.
  Put the VPS near the group and the penalty is small.
- **Effort on friends:** none. They get a stable public address and port.
- **Effort on the owner:** the highest of any option here. A WireGuard tunnel, forwarding rules, and
  a second machine to keep patched and alive. It is now a thing that can break at 2am.
- **Trust:** the provider can see the traffic, same as C, but the relay is yours.
- **Verdict:** the right answer when a stable public endpoint is genuinely required, nothing can be
  installed by players, and the dependency risk of C is unacceptable. Otherwise it is more machine
  than the problem deserves.

### E. Use the crossplay relay and do nothing else

Valheim already ships a relay. Turning on `-crossplay` makes the CGNAT problem irrelevant without
adding any infrastructure at all.

- **Cost:** zero, in money and in setup.
- **Effort on friends:** they need the join code, which changes on every restart.
- **Latency:** relayed, and per the Valheim Wiki more prone to lag and disconnects than a direct
  connection.
- **Failure mode:** a Microsoft-operated service you cannot inspect or fix.
- **Verdict:** **the correct first thing to try behind CGNAT.** It is free, it is native to the
  game, it works today, and it costs one command-line flag. Its weakness is the join code, which is
  a control-plane problem this project has to solve anyway.

### Summary

| Option | Money | Friends install | Consoles | Latency | Biggest risk |
|---|---|---|---|---|---|
| A. Public IP from ISP | Maybe | Nothing | Yes | Best | May be refused |
| B. Overlay VPN | Free | **Yes, each one** | **No** | Best | Excludes consoles |
| C. Tunnel service | **Free for Valheim**; $3/mo for a title with no preset | Nothing | Yes | Relayed | Third-party dependency |
| D. Relay VPS | ~$3-5/mo | Nothing | Yes | One chosen hop | Another machine to run |
| E. Crossplay relay | Free | Nothing | Yes | Relayed | Rotating join code |

## Verifying it actually works

This is the part most guides omit, and the omission is why people spend hours unsure whether their
change did anything.

**From inside the LAN, test nothing.** A connection from inside the network may reach the server by
a path that has nothing to do with the forwarding rule. Some routers do not hairpin at all, so the
test fails on a working setup; others route it internally, so the test passes on a broken one. Both
outcomes are noise. Test from outside: a phone on mobile data, with Wi-Fi off, is the most
convenient external vantage point most people have.

**Do not trust a generic UDP port checker.** UDP has no handshake. A checker sends a datagram and
concludes "open" when nothing comes back, but nothing comes back from a filtered port either. The
same goes for `nc -vzu host 2456`: for UDP it reports success unless an ICMP port-unreachable is
returned, which routers routinely suppress. It will happily tell you a completely dead port is
open.

**Query the server instead, because it answers.** UDP 2457 speaks the Steam A2S protocol, which is
a real request with a real reply. If the server responds with its name and player count, then the
packet reached the host, the host processed it, and the reply came back: the entire path is proven
in one step. Any A2S query tool works; the useful property is that a reply is unambiguous evidence
and a timeout is unambiguous evidence of the opposite.

A practical ladder, in this order, stopping at the first failure:

1. **On the host:** is the process listening, and on the right protocol? `ss -tulpn | grep 245`
   shows both TCP and UDP listeners, which matters: if 2456 and 2457 appear as `tcp`, a container
   published them without `/udp` and the server is unreachable no matter what the router does. If
   nothing appears at all, the problem is the server's configuration rather than the network.
2. **From another machine on the LAN:** does an A2S query to the host's LAN address answer? Proves
   the server and the host firewall are fine, and narrows everything remaining to the router and
   beyond.
3. **From outside, to the public address:** does the A2S query answer? Proves forwarding, ISP path
   and everything else. If step 2 passed and this fails, the fault is the router rule or the ISP.
4. **In-game, from outside:** does the server appear in the browser, and can a client connect and
   stay connected? The browser tests 2457 and the connection tests 2456, which is what makes the
   next table usable.

Record the result of this ladder somewhere after the first successful setup. When it breaks in six
months, knowing which rung used to pass is worth more than any amount of re-reading.

## Symptom table

| Symptom | Most likely cause |
|---|---|
| Not in the server browser, but connects by direct IP | UDP **2457** not reachable. Query port rule missing, or `-public 0` |
| In the browser, but connecting times out | UDP **2456** not reachable. Gameplay port rule missing, or the container published TCP |
| Worked for weeks, then stopped, no changes made | The public address changed (no dynamic DNS, or the updater is broken), or the host's DHCP lease moved and the forwarding rule now points at nothing |
| Works on the LAN, never from outside | Router rule missing or wrong, or CGNAT. Re-run [step 1](#step-1-find-out-what-connection-you-actually-have) |
| Nothing works, WAN address is in `100.64.0.0/10` | CGNAT. Port forwarding cannot work. Pick an escape hatch. Note the range, not just a leading `100.`: `100.43.x.x` is ordinary public space |
| Connects, then drops after a few minutes | Not a forwarding problem. Suspect the relay if on crossplay, upstream bandwidth saturation, or the server process dying - check [`always-on-operation.md`](always-on-operation.md) |
| Steam friends connect, console friend cannot | `-crossplay` is not enabled. No amount of port forwarding fixes this |
| Everything is open but the server still does not list | `-public 0`, or the server has not finished its first heartbeat. Listing is not instant |

## Upstream bandwidth

A domestic connection is asymmetric, and a game server is an upload-heavy workload: the server
sends world state to every connected player. Downstream capacity, which is what the ISP advertises,
is almost irrelevant here.

Valheim's per-player bandwidth is modest and a handful of players will not trouble any modern
connection. The realistic risk is not the game but contention: a large upload, a backup job pushing
to off-site storage, or someone's video call sharing the same upstream will show up as lag spikes
for every player at once. This is worth knowing before blaming the game. Scheduling the off-site
backup for a time nobody plays is the cheapest mitigation and costs nothing to arrange - see
[`save-data-and-backups.md`](save-data-and-backups.md).

## Security notes

Opening a UDP port to the internet is a deliberate act and deserves a moment's thought.

- **Expose the two game ports and nothing else.** In particular never forward the Steamworks TCP
  port, and never expose SSH to the internet to make remote administration easier. Administration
  belongs on the overlay VPN or behind a key-only, non-password path.
- **The server password is not access control.** It is a weak shared secret, minimum five
  characters, that will end up pasted in a group chat. For a genuinely private world use
  `permittedlist.txt` - with the caveat, from Iron Gate's own guide, that adding one person to the
  permitted list bans everyone not on it, which is the intended behaviour and surprises everyone
  the first time.
- **A public server will be found.** Listing a server publicly means it appears in a browser that
  anybody can read. Set `-public 0` if the world is meant for the group only; it stays joinable by
  direct address and join code.
