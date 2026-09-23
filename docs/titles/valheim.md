# Valheim dedicated server

> Status: accepted
> Last reviewed: 2026-09-22
> Game version at time of writing: **1.0.15, released 2026-09-18**

The first title on the platform, and the case the platform design is validated against. This
document is the end-to-end reference: from a bare Linux machine to friends connected, including the
networking.

**Version warning.** Valheim left early access at 1.0 on 2026-09-09 and had shipped 1.0.15 by
2026-09-18 ([Iron Gate news](https://www.valheimgame.com/news/), accessed 2026-09-22). That is
roughly fifteen releases in nine days. **1.0 changed the on-disk world format**, so anything you
read about Valheim saves that predates September 2026 is wrong. Check dates on everything,
including this document.

## At a glance

| | |
|---|---|
| Steam app ID | `896660` (dedicated server, separate from the `892970` game client) |
| Steam login | `anonymous`. No account, no game ownership needed on the host |
| Binary | `valheim_server.x86_64` (Linux), `valheim_server.exe` (Windows) |
| Ports | **UDP 2456** game, **UDP 2457** query, **UDP 2458** under crossplay |
| Remote admin | **None.** No RCON, no console socket |
| Graceful stop | **SIGINT** |
| Config | Command-line flags only |
| Saves | `worlds_local/<World>/`, a directory of chunk files since 1.0 |
| Crossplay | `-crossplay`, relays via PlayFab, removes the port-forwarding requirement |

## Hardware

Valheim's server simulation is **largely single-threaded**, so **clock speed matters more than core
count.** A four-year-old desktop CPU will comfortably outperform a many-core server chip at a lower
clock. This is the most important sizing fact and the one most often missed.

| Group | RAM | Notes |
|---|---|---|
| 2 to 5 players, young world | 4 GB | Practical floor |
| 5 to 10 players, established world | 6 to 8 GB | Bases, terraforming and explored map all cost memory |
| 10+, or old heavily-built worlds | 10 GB+ | |

Add the host OS on top. Disk is modest to start and grows with exploration and building; budget
several GB for the install and let the world grow.

Source: these figures are **community and hosting-provider consensus** (accessed 2026-09-22), not
Iron Gate specifications. Iron Gate publishes client requirements, not dedicated server sizing.
Treat them as a starting point and measure your own world, which is the only number that matters.

**CPU is the resource that degrades the experience first.** When a Valheim server struggles, it
shows up as rubber-banding and delayed damage, not as a crash. If players complain about lag on a
machine with plenty of free RAM, look at single-core saturation.

## Prerequisites

Iron Gate lists these beyond the standard Steam client libraries
([A Guide to Dedicated Servers](https://www.valheimgame.com/support/a-guide-to-dedicated-servers/),
2024-04-11, accessed 2026-09-22):

- `libatomic1`
- `libpulse-dev`
- `libpulse0`
- Minimum `GLIBC_2.29` and `GLIBCXX_3.4.26`

The glibc floor rules out older long-term-support distributions. If the server exits immediately
with a symbol or version error rather than a game log, this is why, and the fix is a newer base
system rather than anything in the game's configuration.

Note that `libpulse` is an audio library and the server is headless. It is still required, because
the binary links against it regardless. Do not try to trim it.

**Running in a container makes all of this the image's problem rather than the host's**, which is
one of the concrete arguments in [ADR 0004](../decisions/0004-run-game-servers-as-containers.md).

## Install

SteamCMD, anonymous, app `896660`:

```
steamcmd +force_install_dir /srv/valheim +login anonymous +app_update 896660 validate +quit
```

`validate` checks the downloaded files against Steam's manifest. It costs seconds and catches a
partial download, which otherwise presents as a server that starts and behaves strangely.

**The same command is how you patch later.** There is no separate update path. See
[applying updates](#applying-updates) for the procedure that wraps it safely.

## Configuration

Valheim is configured **entirely by command-line flags.** There is no settings file. Everything
below goes on the command that launches `valheim_server.x86_64`.

| Flag | Example | Meaning |
|---|---|---|
| `-name` | `"Midgard"` | Name shown in the server browser |
| `-world` | `"Midgard"` | World save name. **Must match the save directory name exactly, including case** |
| `-password` | `"ravenstone"` | Required. See [the rules](#the-password-rules-are-stricter-than-at-least-5-characters), which are stricter than they look |
| `-port` | `2456` | Game port. Query port is automatically this **+1** |
| `-public` | `1` or `0` | `1` lists it in the community browser, `0` hides it. Hidden servers are still joinable by address or join code |
| `-savedir` | `/srv/valheim-data` | Where saves live. **Set this** |
| `-crossplay` | (no value) | Switch to the PlayFab backend. See [connection backends](#connection-backends) |
| `-preset` | `hard` | World modifier preset |
| `-modifier` | `raids none` | Individual world modifier |
| `-saveinterval` | `1800` | Seconds between world saves |
| `-backups` | `4` | How many rolling backups the game keeps |
| `-backupshort` | `7200` | Short backup interval, seconds |
| `-backuplong` | `43200` | Long backup interval, seconds |
| `-nographics -batchmode` | | Headless. Always present for a dedicated server |

**Every flag in the table above is documented by Iron Gate**
([A Guide to Dedicated Servers](https://www.valheimgame.com/support/a-guide-to-dedicated-servers/),
2024-04-11, accessed 2026-09-22), whose parameter list also covers `-logFile`, `-instanceid` and
`-setkey`. `-nographics` and `-batchmode` are Unity engine flags rather than Valheim ones.

### Four traps

These are configuration-level, they all produce confusing symptoms, and each has cost people hours.

#### Steam overwrites `start_server.sh` on every update

The shipped launch script is replaced
whenever you run `app_update`. Any configuration you put in it is destroyed by the act of patching,
and the symptom arrives later as a server that came back up with a different name, no password, or
the wrong world. **Keep launch parameters somewhere Steam does not own**: your own script outside
the install directory, a systemd unit, or container environment variables.

#### The password rules are stricter than "at least 5 characters"

Valheim requires at least five characters and **refuses a password that appears inside the server
name or the world name**, with the comparison case-insensitive. A world called `Vikings` with
password `viking` logs `Error bad password:` and **the server exits.** So a password problem does
not look like a password problem: it looks like a server that will not start.

**Both rules are community-sourced, not vendor-documented.** Iron Gate's guide states no password
constraint at all; its entire entry is `-password "Secret" - Set the password.` The behaviour is
real and reproducible, but if it ever changes there is no vendor page that will tell you. **If a
newly configured server exits immediately, check the password before anything else.**

#### `-preset` silently overwrites `-modifier`

Iron Gate's guide states the ordering rule directly, in its `-modifier` entry: "If combined with a
preset should be set after." So **`-preset` goes first and `-modifier` after it.** Put them the
other way round and the preset discards the individual modifiers, silently. The rule is Iron Gate's
([A Guide to Dedicated Servers](https://www.valheimgame.com/support/a-guide-to-dedicated-servers/),
2024-04-11); the explanation of what goes wrong when you ignore it is community-observed.

#### `permittedlist.txt` is an allowlist, and it is all or nothing

Iron Gate's own guide states
it plainly: "Adding a person on the permitted list will ban everyone else from the server."
Intended behaviour, and it surprises everyone the first time. An empty file allows everyone; adding
one friend locks out the rest of the group.

### World modifiers

The official presets are Normal, Casual, Easy, Hard, Hardcore, Immersive and Hammer (community
documentation, accessed 2026-09-22). Individual modifiers cover combat, death penalty, resource
rate, raids and portals.

Two notes worth having before you pick:

- **Dedicated servers have supported world modifiers since 0.217.x (2023).** Iron Gate's
  [dedicated server guide](https://www.valheimgame.com/support/a-guide-to-dedicated-servers/)
  (2024-04-11) documents `-preset`, `-modifier` and `-setkey`. Older guidance claiming modifiers do
  not work on dedicated servers is long out of date, but this is not a 1.0 change.
- **Hammer mode blocks some achievements.** Iron Gate's
  [1.0 FAQ](https://www.valheimgame.com/support/valheim-1-0-faq/) counts it as a temporary cheat
  (accessed 2026-09-22). Worth telling the group before turning it on for a shared world.

## Access control

Three plain-text files in the save directory, one platform user ID per line, in the form
`[Platform]_[User ID]`, case-sensitive
([Iron Gate](https://www.valheimgame.com/support/a-guide-to-dedicated-servers/), 2024-04-11):

| File | Effect |
|---|---|
| `adminlist.txt` | Admin privileges, including the in-game console |
| `permittedlist.txt` | Allowlist. **Non-empty means everyone not listed is excluded** |
| `bannedlist.txt` | Banned |

Admins get in-game console commands (F5): `Kick`, `Ban`, `Unban`, `Banned`.

**These three files are part of the backup**, and they are easy to forget because they sit outside
the world directory. Rebuilding an allowlist by asking six friends for their platform IDs again is
a tedious evening. See [`save-data-and-backups.md`](../save-data-and-backups.md).

**The password is not access control.** It is a short shared secret that will be pasted into a
group chat, cannot be revoked for one person, and is never rotated. For a genuinely private world,
use `permittedlist.txt` and accept its all-or-nothing behaviour.

## Connection backends

Valheim has two, with opposite network requirements. This decision comes *before* any networking
work, because it determines whether there is any networking work.

| | Steam-native | `-crossplay` |
|---|---|---|
| Transport | Direct UDP | Relayed via Microsoft Azure PlayFab Party |
| Port forwarding | **Required** | **Not required** |
| Who can join | Steam only | Steam, Xbox, Game Pass PC, PS5, Switch 2 |
| Joining | Server browser or IP:port | **Numeric join code**, IP:port, or browser |
| Latency | Best | Relayed. The Valheim Wiki notes crossplay players are "more likely to experience lag, timeouts and disconnects" |
| Catch | You have to solve the networking | **The join code regenerates on every server restart** |

Sources: [Iron Gate](https://www.valheimgame.com/support/a-guide-to-dedicated-servers/)
(2024-04-11); [Valheim Wiki](https://valheim.weirdgloop.org/w/Dedicated_servers) (accessed
2026-09-22).

**If anyone in the group plays on a console or Game Pass, crossplay is mandatory** and there is no
decision to make. If everyone is on Steam, it is a genuine trade: crossplay costs latency and a
dependency you cannot debug, and saves you the entire networking problem.

The join code is not a footnote. A restart at 5am silently invalidates the code every friend has,
and they have no way to find the new one. That is a control-plane obligation, covered in
[`remote-control.md`](../remote-control.md).

Full analysis in [`networking.md`](../networking.md) and
[ADR 0002](../decisions/0002-reach-the-server-from-the-internet.md).

## Ports

| Port | Protocol | Purpose | Forward |
|---|---|---|---|
| 2456 | **UDP** | Gameplay | Yes |
| 2457 | **UDP** | Steam query and A2S, server browser listing | **Yes, always** |
| 2458 | UDP | Associated with the crossplay backend | Optional. Crossplay is relayed and needs no forwarding |
| random high | TCP | Steamworks internal | **Never** |

Three rules that are not obvious:

- **Forward 2457 even on a private server.** With `-public 0` nothing gets listed, so it looks
  skippable. It is not: the A2S reply on 2457 is the only proof of the network path this
  documentation accepts ([ADR 0002](../decisions/0002-reach-the-server-from-the-internet.md)), and
  without it you cannot tell a working setup from a broken one.
- **Do not forward TCP 2456-2457.** It does nothing. Both game and query traffic are UDP.
- **Keep external and internal port numbers identical.** Valheim advertises its own port to the
  Steam lobby, so remapping produces a listing that advertises a port nobody can reach.

## Saves

Since 1.0, a world is a **directory**, not a file pair:

```
<savedir>/worlds_local/Midgard/
  _main.7.fwl2      metadata: name, seed, owner
  _main.7.db2       world data
  _main.7.chunks    chunk index
  00_00__0_1.chunk  terrain chunks, many, growing with exploration
  _main.7.ok        write-complete marker for generation 7
```

Three things to carry away:

1. **Back up the whole directory**, never selected files. A partial copy gives a world the server
   cannot open, and its response is to generate a fresh empty one rather than to error.
2. **The `.ok` marker means the save completed.** It is how you tell a consistent copy from one
   taken mid-write, and it is how you tell a healthy server from one that is running and silently
   failing to save.
3. **The 1.0 conversion is one-way.** A pre-1.0 world opened by a 1.0 server is converted and can
   never be opened by an older server again. Iron Gate's
   [1.0.15 notes](https://www.valheimgame.com/news/patch-1-0-15/) (2026-09-18) record a conversion
   bug that damaged item levels and was only fixed in 1.0.12. **Snapshot before the first boot on a
   new major version.**

Default location if `-savedir` is not set: `~/.config/unity3d/IronGate/Valheim/`. Set `-savedir`.

Everything else, including the restore drill, is in
[`save-data-and-backups.md`](../save-data-and-backups.md).

## Running it

Supervision, graceful stop, restarts and monitoring are in
[`always-on-operation.md`](../always-on-operation.md). The Valheim-specific parts:

**Stop with SIGINT.** Iron Gate: "It is important that you close it by pressing CTRL+C". SIGTERM is
unreliable, and SIGKILL loses everything since the last autosave, up to 30 minutes by default.
Docker's defaults (SIGTERM, 10 second timeout) are wrong on both counts and must be overridden.

**Health is two separate questions.** Liveness is an A2S query on 2457. Durability is whether the
newest generation number and `.ok` timestamp are advancing. A server can pass the first and fail
the second indefinitely, which is exactly the failure that costs a world.

## End to end

From a bare Linux machine to friends playing. Each step links to the document that covers it in
depth.

**Decide first**

1. **Is anyone on a console or Game Pass?** If yes, you are using `-crossplay` and can skip most of
   step 5. ([`networking.md`](../networking.md))
2. **Diagnose the connection.** Compare the router WAN address against your observed public
   address. `100.64.0.0/10` means CGNAT, and port forwarding cannot work. **Do this before touching
   the router**, because it determines whether there is any point.
   ([`networking.md`](../networking.md))

**Prepare the host**

3. **Set the machine up to be a server.** BIOS power-on after AC loss, unattended security updates
   with a chosen reboot window, SMART monitoring, and a cold boot tested with no keyboard or
   display attached. ([`always-on-operation.md`](../always-on-operation.md))
4. **Choose where state lives** and point `-savedir` at it. Somewhere deliberate, on the filesystem
   you intend to back up, not the default under a hidden home directory.

**Reachability**

5. **Make it reachable.** Either forward UDP 2456 and 2457 to a DHCP-reserved host address and add
   dynamic DNS if the address moves, or use `-crossplay`, or pick an escape hatch if behind CGNAT.
   ([`networking.md`](../networking.md), [ADR 0002](../decisions/0002-reach-the-server-from-the-internet.md))

**Install and configure**

6. **Install** with SteamCMD, app `896660`, `validate`.
7. **Write the launch parameters somewhere Steam does not own.** Not `start_server.sh`. Check the
   password against [the rules](#the-password-rules-are-stricter-than-at-least-5-characters) before
   the first start.
8. **Supervise it**, with SIGINT as the stop signal and a generous stop timeout. Restart on
   failure, with a rate cap. ([ADR 0004](../decisions/0004-run-game-servers-as-containers.md))

**Protect it**

9. **Set up backups before you invite anybody.** Local copy plus an encrypted off-site copy of the
   whole world directory and the three permission list files.
   ([`save-data-and-backups.md`](../save-data-and-backups.md))
10. **Run the restore drill.** Restore a backup to a second location, start it, connect, confirm
    the world is whole, and time it. A backup you have not restored is a belief.

**Open it up**

11. **Add admins and, if wanted, the allowlist.** Remember `permittedlist.txt` excludes everyone
    not on it.
12. **Verify from outside**, using the checklist below.
13. **Publish how to connect**, and if using crossplay decide now how the join code reaches people
    after a restart. ([`remote-control.md`](../remote-control.md))

**Then keep it alive**

14. **Monitor that saves are advancing**, not just that the process is up.
15. **Have an update procedure** and use it. ([applying updates](#applying-updates))

## Verify it worked

Run in order and stop at the first failure. The step that fails localises the fault.

| # | Check | Passing means |
|---|---|---|
| 1 | `ss -tulpn \| grep 245` on the host shows 2456 and 2457 as **`udp`** | The server is listening on the right protocol. `tcp` here means a container published without `/udp`; nothing at all means a configuration problem |
| 2 | The world directory has a recent generation with a matching `.ok` | It is saving. This is the check that matters most |
| 3 | A2S query from another LAN machine to the host answers | Server and host firewall are fine |
| 4 | A2S query **from outside the network** answers | Forwarding and the ISP path are fine |
| 5 | The server appears in the in-game browser | Port 2457 and `-public 1` are working |
| 6 | A client outside the network connects and stays connected | Port 2456 is working |
| 7 | A restore drill has been completed | The world would actually come back |

**Test from outside, not from the LAN.** A LAN test can pass on a broken setup or fail on a working
one, depending on whether the router hairpins. A phone on mobile data with Wi-Fi off is the
easiest external vantage point.

**Do not trust generic UDP port checkers or `nc -vzu`.** UDP has no handshake, so they report
"open" for a completely dead port. The A2S query is the reliable test because the server actually
replies. See [`networking.md`](../networking.md).

**Write down the result of this ladder.** When it breaks in six months, knowing which rung used to
pass is worth more than re-reading anything.

## Applying updates

The full reasoning, including the client/server version lockstep dilemma, is in
[`always-on-operation.md`](../always-on-operation.md). The Valheim-specific sequence:

1. Announce it.
2. Confirm nobody is connected. Query, do not assume.
3. Stop with **SIGINT** and wait for the process to exit.
4. **Snapshot the world**, somewhere the update cannot reach. **Mandatory on a major version**, and
   this is the step that makes everything after it reversible.
5. `steamcmd +force_install_dir /srv/valheim +login anonymous +app_update 896660 validate +quit`
6. **Check your launch parameters survived.** `start_server.sh` has just been overwritten. If your
   configuration lives outside it, nothing to do; if it does not, fix that now rather than next
   time.
7. Start, and confirm the right world loaded and that a save completes.
8. Have someone connect before calling it done.

**Rolling back is two things.** The binaries, which a container image tag makes trivial and
SteamCMD makes awkward; and the world, from step 4's snapshot. If the update converted the save
format, the binaries alone are not enough, because an older server cannot read the converted
world. Step 4 is the only way back.

## Troubleshooting

| Symptom | Cause |
|---|---|
| **Server exits immediately after start** | Password shorter than 5 characters, **or the password appears in the server name or world name**. Check the log for `Error bad password:`. This is the most common first-run failure |
| Exits with a symbol or `GLIBC` version error | Base system too old. Needs GLIBC 2.29+ and GLIBCXX 3.4.26+ |
| Starts, but the world is empty | `-world` does not match the save directory name, case included; or `-savedir` points somewhere unexpected; or a container mount is wrong. **Stop it before it saves over anything** |
| Not in the browser, connects by direct IP | UDP 2457 unreachable, or `-public 0` |
| In the browser, connection times out | UDP 2456 unreachable, or the container published TCP instead of UDP |
| Worked for weeks, then stopped with no changes | Public IP changed and dynamic DNS did not follow, or the host's DHCP lease moved and the forwarding rule now points nowhere |
| Console friend cannot join, Steam friends can | `-crossplay` not enabled. No amount of port forwarding fixes this |
| Friend has yesterday's join code and cannot connect | A restart regenerated it. Expected behaviour, see [`remote-control.md`](../remote-control.md) |
| Configuration reverted after a patch | It was in `start_server.sh`, which Steam overwrote |
| World modifiers not applied | `-preset` placed after `-modifier`, which silently discards them |
| Everyone locked out after adding one admin | Entry went into `permittedlist.txt`, which excludes everyone not listed |
| Lag and rubber-banding, plenty of free RAM | Single-core CPU saturation. Valheim's simulation is largely single-threaded |
| Server healthy, world not changing on disk | Saves are failing silently. Permissions, full disk, or a container ownership problem. **Worst case in this table** |
| Players on an updated client cannot join | Version lockstep. The server needs the same update |

## Valheim against the platform contract

Valheim's filled-in manifest lives in
**[`platform-architecture.md`, "Valheim against the contract"](../platform-architecture.md#valheim-against-the-contract)**,
next to the contract it validates. It is deliberately not duplicated here: it is meant to be the
single declarative description of the title, and two copies drift, which they already had begun to
do. Everything in it is drawn from the sections above.

If the generic contract could not express the title it was designed around, the contract would be
wrong. Every field is expressible, and the two that come out empty - `preconditions` and `admin` -
are empty for real reasons rather than for lack of room.

Two of the contract's fields exist *because* of Valheim: `config_hazards`, from the
`start_server.sh` trap, and `state_consistency`, from the `.ok` marker. The title drove the
contract rather than being retrofitted to it, which is what makes this a validation rather than a
coincidence.

## What in this document will rot first

Listed so a future reader knows where to look rather than re-verifying everything.

| Claim | Why it rots | Check against |
|---|---|---|
| Save format and file names | Changed at 1.0 and derived from community observation, not a published spec | A real installation |
| Version-specific behaviour | ~15 releases in 9 days around 1.0 | [Iron Gate news](https://www.valheimgame.com/news/) |
| RAM sizing | Community consensus, and 1.0 added a biome | Your own world |
| Crossplay platform list | PS5 and Switch 2 were added at 1.0 | [Iron Gate 1.0 FAQ](https://www.valheimgame.com/support/valheim-1-0-faq/) |
| Port protocols | Not stated by Iron Gate; from the wiki and server implementations | [Valheim Wiki](https://valheim.weirdgloop.org/w/Dedicated_servers) |
| Signal handling | Observed behaviour, not documented by Iron Gate | Test a stop and check the `.ok` marker |
| Password rules | Not documented by Iron Gate at all; community-observed | Try a password that violates them and read the log |
