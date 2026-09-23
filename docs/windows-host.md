# The Windows host

> Status: accepted
> Last reviewed: 2026-09-22

[ADR 0001](decisions/0001-host-on-an-owned-always-on-x86-machine.md) assumed a Linux machine whose
only job is to be a server. The actual host is **Windows 11 Home**, and it is also the owner's
daily driver and gaming machine. [ADR 0007](decisions/0007-host-on-windows-with-docker-desktop-and-wsl2.md)
records that correction and decides the arrangement. **This document is how to build it.**

[`always-on-operation.md`](always-on-operation.md) covers what keeps the *process* alive and is
still correct. This document covers the layer underneath it, which that document assumed away.

## This host

Filled in from the machine itself. Values that are not yet measured are marked, rather than
guessed, because this is exactly the kind of table that rots into fiction.

Measured 2026-09-23.

| | |
|---|---|
| Windows edition | Windows 11 **Home** |
| Windows version | **25H2**, build 26200.9457. Comfortably above the 22H2 that mirrored networking needs |
| Form factor | **Laptop**. See [section 1](#1-never-sleep-never-hibernate-no-fast-startup) |
| CPU | Intel Core i7-13700H, 14 cores / 20 threads |
| RAM | **63.7 GB** |
| Network | **Wi-Fi**, adapter named `Wi-Fi 2`, MAC `6C-F6-DA-87-ED-99` |
| Link rate observed | **130 Mbps**, which is 802.11n on **2.4 GHz**. See [section 1](#wi-fi-since-that-is-the-network-path) |
| Sleep states | **S3 available. S0 Low Power Idle unsupported by the firmware** |
| WSL | 2.6.3.0, kernel 6.6.87.2 |
| Docker | **Not installed yet** |
| Also used for | Daily desktop work and playing games, including Valheim |

Three of those settle questions this document was written not to assume:

- **25H2** means mirrored networking exists, so the arrangement in
  [ADR 0007](decisions/0007-host-on-windows-with-docker-desktop-and-wsl2.md) holds.
- **No S0 Low Power Idle** means this is a classic-sleep machine and the timeouts in section 1
  really do control it. The opposite answer would have left the always-on premise resting on
  nothing.
- **63.7 GB** means the resource limits in [section 6](#6-resource-limits-on-a-machine-that-is-also-a-gaming-pc)
  stop being a negotiation. There is enough for the server and the game at once with room spare.

**It being a laptop is not a detail.** A laptop is a machine designed to stop running when nobody
is using it, and three of its defaults each end the always-on premise on their own. It also brings
one real gain: the battery is the uninterruptible power supply
[`always-on-operation.md`](always-on-operation.md) calls the cheapest available upgrade.

## The chain that has to work

Everything below exists to make one sequence complete without a person in it. If any link breaks,
the world is down until someone walks over to the machine, which is the dependency
[`scope-and-goals.md`](scope-and-goals.md) goal G2 exists to remove.

```
  Windows Update reboots at 04:00
  (a power cut does NOT appear here: the battery absorbs it)
      |
      v
  the machine powers on and boots            <- no hibernation state to resume
      |
      v
  Windows logs a session on automatically    <- auto-logon, then immediately locked
      |
      v
  Docker Desktop starts with that session    <- it cannot start without one
      |
      v
  the WSL 2 VM starts, and stays up          <- idle timeouts disabled
      |
      v
  the container restarts by policy           <- restart: unless-stopped
      |
      v
  the world loads and saves advance
```

**Five of those seven links do not exist by default**, and none of them announces its absence. The
[acceptance test](#the-acceptance-test) exercises the whole chain at once, which is the only
honest way to check it.

## 1. Never sleep, never hibernate, no Fast Startup

Sleep and hibernation end the always-on premise outright, and Fast Startup is the subtle one: with
it enabled a "shut down" is actually a hibernation of the kernel session, so the thing you tested
as a clean boot is not the thing that happens.

```powershell
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /change disk-timeout-ac 0
powercfg /hibernate off              # also removes Fast Startup
```

`powercfg /hibernate off` is doing double duty here and that is deliberate: Fast Startup has no
separate switch that survives a settings reset, and turning hibernation off removes both.

The monitor is left alone. A blank screen costs nothing.

### The three that are specific to a laptop

This host is a laptop, and the settings above were written for a desktop. Each of these ends the
always-on premise on its own, and none of them looks like a fault afterwards.

**Closing the lid suspends it.** The most likely way this server dies. It takes one absent-minded
moment, and what you find later is a machine that is simply asleep:

```powershell
powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0   # 0 = do nothing
powercfg /setactive SCHEME_CURRENT
```

Set only for AC. On battery, suspending on a closed lid is still the right behaviour.

**On battery, none of the AC policy applies.** Windows keeps a separate DC policy, so an unplugged
host sleeps on its own schedule regardless of everything above. **The machine has to stay plugged
in.** That is a physical operating requirement, not a setting, and no script can enforce it.

**Modern Standby may ignore the timeouts entirely.** Many laptops use S0 low-power idle rather than
the older S3 sleep, and on those the classic settings do not reliably keep the machine awake. This
is not knowable from documentation; read it off the hardware:

```powershell
powercfg /a
```

If the output says the system supports **Standby (S0 Low Power Idle)** and reports S3 as
unavailable, this machine is Modern Standby and the timeout settings above are necessary but may
not be sufficient.

**On this host, read 2026-09-23, the answer is the favourable one.** S3 is available and S0 Low
Power Idle is explicitly unsupported by the firmware, so the timeout settings do control it. The
hour-long test below is still worth running once, because a setting that is correct and a machine
that stays awake are different claims, but it is confirmation rather than a gate.

### The gain a laptop brings

[`always-on-operation.md`](always-on-operation.md) lists an uninterruptible power supply as
"optional, and the cheapest real upgrade available", because it turns most domestic power events
into a non-event. **This host has one built in.** A power cut stops being an outage, which also
makes the BIOS power-on-after-AC-loss setting that document asks for largely moot, and most
laptops do not offer it anyway.

Two things follow that a desktop owner never has to think about:

- **Keep it plugged in**, per above. The UPS only works if the machine is on AC to begin with.
- **Battery health is now operational.** A battery held at 100% on permanent AC degrades, and the
  battery is the UPS. If the firmware offers a charge limit, typically 60 to 80 percent, set it.
  If it does not, the UPS is on a clock and will quietly stop being one.

### Wi-Fi, since that is the network path

```powershell
Disable-NetAdapterPowerManagement -Name 'Wi-Fi 2'
```

The adapter is named `Wi-Fi 2` on this host, with a space, so it has to be quoted.

### The band, which is the finding worth acting on

The adapter reported a link rate of **130 Mbps**. That is precisely the 802.11n rate for a
two-stream 40 MHz channel on **2.4 GHz**, which is the congested band, on a shared building
network where the congestion is other people's.

Bandwidth is not the concern: Valheim's per-player traffic is small and 130 Mbps is far more than
this needs. **Jitter is.** Valheim sends world state over UDP with no retransmission underneath
it, so variance in delivery arrives in the game as rubber-banding rather than as a disconnection,
and that is now the third thing that produces that same symptom alongside single-core saturation
and thermal throttling.

**If the access point offers 5 GHz, moving to it is free and is the largest improvement available
short of a cable.** 5 GHz is less congested, and on a shared network that matters more than usual
because the interference is not yours to turn off.

**This stops being housekeeping and becomes mandatory on a machine nobody touches.** An adapter
that idles down drops the link, and the symptom is a server that was reachable and now is not,
with nothing in any log to explain it.

Two more Wi-Fi consequences, both covered in [`networking.md`](networking.md):

- **The DHCP reservation goes against the Wi-Fi adapter's MAC**, not the ethernet port's. A
  reservation on the wrong interface does nothing, silently.
- **Wi-Fi jitter and CPU saturation produce the same complaint.** Both show up as rubber-banding
  rather than as a disconnection, so "it is laggy" now has two plausible causes and the first
  question is which.

**A cable is the single cheapest improvement available to this project.** It is a recommendation
rather than a requirement: it removes a whole class of fault for the price of a cable. If the host
ever moves to ethernet, the DHCP reservation and the forwarding rule both have to follow the new
MAC address.

## 2. Windows Update: schedule the reboot, do not fight it

**Windows 11 Home has no Local Group Policy Editor**, so the policies normally used to defer or
suppress automatic restarts are not available. What Home does have is **Active Hours**, under
Settings > Windows Update > Advanced options, which is a window during which Windows will not
restart on its own.

Set Active Hours to cover when people play. Then stop there, because the rest of that fight is not
winnable on this edition.

> **The conclusion, and it is the useful one: on this host, reboot survival is the mitigation, not
> reboot prevention.** Outside the active window the machine will restart, and a design that tries
> to prevent it will fail quietly one Tuesday. Everything else in this document assumes the reboot
> happens and makes it a non-event.

## 3. Auto-logon, and what it costs

Docker Desktop is a desktop application. It starts with a user session and there is no supported
service mode ([docker/roadmap #515](https://github.com/docker/roadmap/issues/515), accessed
2026-09-22). After an unattended reboot nobody is logged in, so without auto-logon the chain above
stops at link three.

**Use Sysinternals `Autologon` rather than the `netplwiz` checkbox.** Both achieve the same result,
but they store the password differently: `Autologon` puts it in **LSA secrets**, while the manual
registry route writes `DefaultPassword` as **plain text** readable by anything on the machine. The
difference is free, so take it.

```
Autologon.exe <username> <domain-or-machine-name> <password>
```

**The cost, stated plainly rather than buried:** the account password is now recoverable by any
local administrator. On a single-owner personal machine that is a bounded cost, and it is the price
of the Docker Desktop option. It is in the threat model from here on.

**Mitigate the physical half** with a task that locks the workstation the instant the automatic
logon completes, so the machine is never sitting unlocked at a desk:

```powershell
$action  = New-ScheduledTaskAction -Execute 'rundll32.exe' -Argument 'user32.dll,LockWorkStation'
$trigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName 'Lock after automatic logon' -Action $action -Trigger $trigger
```

This locks the screen. It does not lock the session, so Docker Desktop and everything under it keep
running, which is exactly what is wanted.

**If this trade is ever unacceptable**, ADR 0007 records the fallback: Docker Engine inside a WSL 2
distribution, started by a Task Scheduler task running as SYSTEM, which needs no logon at all.

## 4. Docker Desktop starts with the session

In Docker Desktop, Settings > General, enable **"Start Docker Desktop when you sign in"**.

Then let the container's own restart policy do the rest. `restart: unless-stopped` survives a
daemon restart and a reboot, and is what [ADR 0004](decisions/0004-run-game-servers-as-containers.md)
assumed when it chose containers for supervision.

Docker Desktop is free for personal use, so this costs nothing beyond the auto-logon above.

## 5. WSL 2: mirrored networking, the firewall, and the idle timers

All of these go in `%UserProfile%\.wslconfig`. WSL reads it at VM start, so `wsl --shutdown` is
needed before a change takes effect.

```ini
[wsl2]
# Valheim is UDP-only, and the documented NAT-mode route to WSL 2 from the LAN
# (netsh interface portproxy) has no UDP mode at all. Mirrored mode is the
# supported path. Requires Windows 11 22H2 or higher.
networkingMode=mirrored

# The Hyper-V firewall is on by default and blocks inbound until a rule allows it.
# Left on deliberately: the rule below is narrow, and turning this off would be
# opening the whole boundary to avoid writing one line.
firewall=true

# Cap the VM so the machine stays usable for gaming. See section 6.
memory=<pending>
processors=<pending>

# The VM must never idle out. This is an always-on server, not a dev box.
vmIdleTimeout=-1

[general]
# Same reason. A distribution that shuts itself down takes the world with it.
instanceIdleTimeout=-1

[experimental]
# Give cached memory back to Windows, but slowly. The default, dropCache, releases
# it immediately, which on a file-heavy workload means re-reading the world from disk.
autoMemoryReclaim=gradual
```

Source for every key, its section and its minimum version:
[Microsoft Learn, Advanced settings configuration in WSL](https://learn.microsoft.com/en-us/windows/wsl/wsl-config)
(updated 2026-09-16, accessed 2026-09-22). `networkingMode`, `firewall` and `dnsTunneling` require
Windows 11 22H2 or higher; `autoMemoryReclaim` and `hostAddressLoopback` live under
`[experimental]`, not `[wsl2]`, which is easy to get wrong and fails silently because **WSL ignores
a malformed file and starts normally**.

**The idle timeouts deserve their own note**, because nothing in the rest of this documentation
anticipated them. WSL shuts an idle VM down on a timer: `vmIdleTimeout` defaults to 60000 ms and
`instanceIdleTimeout` to 15000 ms. Those defaults are right for a development machine and wrong for
a server, and the symptom would be a world that disappears when nobody has touched the machine for
a minute. Disable both.

### The Hyper-V firewall rule

Mirrored mode routes LAN traffic to the WSL 2 VM, and the Hyper-V firewall blocks it inbound until
told otherwise. Admit the two Valheim ports and nothing else:

```powershell
New-NetFirewallHyperVRule `
  -Name 'Valheim-UDP' `
  -DisplayName 'Valheim game and query (UDP 2456-2457)' `
  -Direction Inbound `
  -VMCreatorId '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}' `
  -Protocol UDP `
  -LocalPorts 2456-2457
```

The `VMCreatorId` above is WSL's, given by Microsoft's own documentation
([Accessing network applications with WSL](https://learn.microsoft.com/en-us/windows/wsl/networking),
updated 2026-06-02, accessed 2026-09-22). That page also offers
`Set-NetFirewallHyperVVMSetting -DefaultInboundAction Allow`, which opens the whole boundary.
**Do not use it.** The narrow rule is one line longer and admits two ports instead of all of them.

### The Windows Defender Firewall rule

The Hyper-V rule governs the boundary into the VM. The ordinary Windows firewall still governs the
machine, and Docker Desktop's published-port listener sits on the Windows side of it:

```powershell
New-NetFirewallRule -DisplayName 'Valheim game and query (UDP 2456-2457)' `
  -Direction Inbound -Protocol UDP -LocalPort 2456-2457 -Action Allow -Profile Private
```

**Check the network profile is Private**, not Public. A home LAN marked Public is a common and
silent cause of a rule that exists and does nothing:

```powershell
Get-NetConnectionProfile
```

**None of the above is proof that UDP actually traverses this stack.** Docker Desktop publishes
ports through its own Windows-side proxy, which is a different mechanism from anything Microsoft
documents for WSL, and its behaviour for UDP from *external* hosts is not settled by any vendor
page. [`networking.md`](networking.md) proves it with a datagram, before any code depends on it,
exactly as [ADR 0002](decisions/0002-reach-the-server-from-the-internet.md) requires.

## 6. Resource limits, on a machine that is also a gaming PC

The owner will be playing on this box while it serves. Two resources are genuinely contended and
one is not.

| Resource | Contended | Why |
|---|---|---|
| **GPU** | No | The server runs `-nographics -batchmode` and never touches it |
| **CPU** | **Yes** | Valheim's simulation is largely single-threaded, so the server needs one core's worth of *uninterrupted* time, not many cores. This is what degrades first, and it shows up as rubber-banding rather than a crash |
| **RAM** | **Yes** | The WSL 2 VM claims host memory, and a game client wants several gigabytes of its own |

Both are capped rather than negotiated, at two levels: `memory` and `processors` in `.wslconfig`
bound the whole VM, and per-container limits bound the game inside it. Starting points, to be
measured and then corrected:

| Host RAM | `.wslconfig memory` | `.wslconfig processors` | Container limit |
|---|---|---|---|
| 16 GB | `6GB` | `4` | `--memory 5g --cpus 2` |
| 32 GB | `10GB` | `4` | `--memory 8g --cpus 2` |
| **63.7 GB (this host)** | **`12GB`** | **`8`** | **`--memory 8g --cpus 4`** |

**On this host these numbers are not a negotiation.** With 63.7 GB and 20 threads there is enough
for the server and the game at once with a lot spare, so the caps exist to stop WSL 2 from
helping itself rather than to ration anything. Left alone, WSL 2 claims half the machine's memory
by default, which here would be about 32 GB taken from a machine that is also somebody's desktop.

Four cores for a largely single-threaded server is not waste: it leaves headroom for the autosave,
which is the moment the server most needs not to be starved, and which is the moment a world is
most at risk.

**One nuance this CPU introduces.** The i7-13700H is a hybrid design, six performance cores and
eight efficient ones. Valheim's simulation wants a performance core, and neither WSL 2 nor Docker
can ask for one by name: the Windows scheduler decides. This is not worth engineering around in
advance, but it is worth knowing as a lever if players report lag while every other number looks
healthy.

**Measure rather than trust this table.** [`titles/valheim.md`](titles/valheim.md) is explicit that
the published RAM figures are community consensus and that the only number that matters is your own
world. If players report lag while RAM is plentiful, look at single-core saturation **or at the
Wi-Fi path**, which on this host produce the same symptom.

**Thermals deserve a line of their own here, because this is a laptop.**
[`always-on-operation.md`](always-on-operation.md) already notes that a machine idling at a desk
for an hour a day behaves differently from one running a game simulation continuously for months.
A laptop chassis has far less thermal headroom than the desktop that sentence was written about,
and a laptop that thermally throttles does not crash: it gets slower, which arrives as
rubber-banding, which is the third thing that produces that same complaint.

Two cheap mitigations, in order of value: **do not run it on a soft surface**, where the intake is
usually on the underside, and **cap the container cpus rather than letting the server take what it
wants**, which is what the table above already does.

## 7. Where the state lives, and where it must not

**The save directory goes on the WSL 2 ext4 filesystem or in a Docker volume. Never under
`/mnt/c`.**

DrvFs, the filesystem that presents Windows drives inside WSL, does not carry POSIX ownership and
permission semantics faithfully unless explicitly mounted with metadata, and even then imperfectly
([Microsoft Learn, wsl.conf automount options](https://learn.microsoft.com/en-us/windows/wsl/wsl-config),
accessed 2026-09-22). This project already has a documented case of exactly that class of bug
destroying every autosave while the container reported healthy
([valheim-server-docker issue #802](https://github.com/community-valheim-tools/valheim-server-docker/issues/802)):
permissions applied without distinguishing files from directories left the per-world directories
without the execute bit, so nothing could be created inside them.

The consequence is that **the backup service is the only thing that moves world data across the
Windows boundary**, which is a cleaner arrangement anyway. See
[`save-data-and-backups.md`](save-data-and-backups.md).

## Applying it

The PowerShell in [`../deploy/host/`](../deploy/host/) applies sections 1, 3, 4 and 5, so the host
is reproducible rather than a story about what someone once clicked. Run it from an elevated
PowerShell prompt. It is written to be re-runnable: every step checks before it changes.

Sections 2 and 6 need a human decision (which hours, which numbers) and are done by hand.

## The acceptance test

Settings that look correct and do not survive a reboot are the failure this whole document guards
against, so the test is the reboot, not the checklist.

1. Start a marker container that should outlive anything:
   `docker run -d --restart unless-stopped --name reboot-probe alpine sleep infinity`
2. **Log out.** Do not shut down from a logged-in session; the point is that nobody is there.
3. Reboot the machine.
4. Wait, without touching it and without logging in.
5. From another machine, or after the fact, confirm `docker ps` shows `reboot-probe` running, and
   note how long after power-on it came back.

### And the second test, which this host needs and a desktop would not

**Close the lid.** With the marker container running and the machine on AC:

1. Close the lid and leave it for ten minutes.
2. From another machine on the network, confirm the container is still answering.
3. Open it again and check `docker ps`.

This is a separate test because it is a separate failure, and on a laptop it is the **most likely**
one: it needs no update, no power cut and no crash, just somebody tidying up. If the machine
suspended, the lid action did not take, and nothing else in this document will save the server
from it.

While you are there, the same ten minutes answers the Modern Standby question from
[section 1](#1-never-sleep-never-hibernate-no-fast-startup): leave the lid **open** and the machine
untouched for an hour instead, and confirm the same thing.

**Record the result below.** A number here is the difference between believing the host is
always-on and knowing it.

### Record

| Date | What was tested | Result | Time to recovery |
|---|---|---|---|
| *pending* | Unattended reboot, marker container | *pending* | *pending* |
| *pending* | Lid closed ten minutes, on AC | *pending* | n/a |
| *pending* | Untouched one hour, lid open (Modern Standby) | *pending* | n/a |

The full-stack version of this test, with the real server rather than a marker container, is rung
one of [the end-to-end verification](titles/valheim.md#verify-it-worked).

## What in this document will rot first

| Claim | Why it rots | Check against |
|---|---|---|
| `.wslconfig` key names and their sections | Keys have moved between `[wsl2]` and `[experimental]` as features left preview | [Microsoft Learn, wsl-config](https://learn.microsoft.com/en-us/windows/wsl/wsl-config) |
| Docker Desktop needing a session | A supported service mode would remove section 3 entirely | [docker/roadmap #515](https://github.com/docker/roadmap/issues/515) |
| Mirrored mode carrying UDP from outside | Not vendor-documented either way. Ours is an observation | Re-run the proof in [`networking.md`](networking.md) |
| The resource table | Guesses until measured, and the world grows | Your own world |
| Windows 11 Home's update controls | Microsoft moves these between builds | Settings > Windows Update > Advanced options |
| That the lid action holds | Power plans get reset by updates, driver installs and vendor utilities | Close the lid and check |
| That the battery is still a UPS | Batteries degrade, and this one is held at charge continuously | Unplug it briefly and watch the estimate |
| That the host is still on Wi-Fi | A cable is the cheapest improvement here, and taking it changes the MAC | `Get-NetAdapter`, and the router's DHCP reservation |
