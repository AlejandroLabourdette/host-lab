# 0007 - Host on Windows 11 Home, with the Linux layer in Docker Desktop and WSL2

> Status: accepted
> Date: 2026-09-22
> Amends the context of [0001](0001-host-on-an-owned-always-on-x86-machine.md) and [0004](0004-run-game-servers-as-containers.md)

## Context

[ADR 0001](0001-host-on-an-owned-always-on-x86-machine.md) chose "an always-on x86 machine the
owner already owns, running Linux". [ADR 0004](0004-run-game-servers-as-containers.md) records as
context that "the host runs Linux and already has Docker available".

When the implementation began, the actual host turned out to be:

- **Windows 11 Home.** Not Linux. Linux exists on it only inside WSL2.
- **A laptop**, not a desktop or a mini-PC. Confirmed 2026-09-23.
- **On Wi-Fi**, not ethernet. Confirmed 2026-09-23.
- **The owner's daily driver and gaming machine.** They keep using it for everything, including
  playing Valheim itself, while it hosts. It has to stay usable.

The last two arrived after the first draft of this record, which described a desktop. They are
called out rather than folded in silently, because each one breaks a specific assumption the
documentation had made: [`always-on-operation.md`](../always-on-operation.md) tells the reader to
set BIOS power-on after AC loss, which most laptops do not offer, and
[`networking.md`](../networking.md) assumes a wired host when it says to reserve a DHCP address.

Neither ADR's *decision* is wrong. 0001 chose an owned always-on x86 machine over a VPS, a managed
game host and an ARM board, and every argument it made still holds. 0004 chose containers over bare
systemd, LinuxGSM and a panel, and every argument it made still holds. What was wrong is a premise
both recorded as settled fact, and that premise is load-bearing for six operational questions the
documentation never asked.

This record is marked as **amending** rather than superseding those two, because supersession would
claim their decisions were reversed and they were not. The marker added to each is one line, which
keeps `decisions/` append-only in the way [`README.md`](../README.md) intends.

## The six realities, with evidence

### 1. Windows Update reboots on its own schedule, and Home cannot stop it

Windows 11 Home has no Local Group Policy Editor, so the policy settings normally used to defer or
block automatic restarts are unavailable. What Home does expose is **Active Hours**, a daily window
during which Windows will not restart automatically, and a toggle to restart as soon as possible
otherwise.

That is a scheduling control, not a veto. Outside the active window the machine will reboot, and
sleep or hibernation would end the always-on premise just as completely.

**The conclusion this forces is the useful one: on this host, reboot survival is the mitigation,
not reboot prevention.** A design that tries to prevent the reboot will fail quietly one Tuesday. A
design that assumes the reboot happens and comes back unattended is correct regardless. This ADR
therefore treats "the stack returns by itself after an unannounced reboot with nobody logged in" as
the acceptance test for the whole host arrangement.

### 2. Docker Desktop requires an interactive logged-on session

This is a known, long-standing design limitation rather than a misconfiguration: Docker Desktop is
a desktop application that starts with a user session, and there is no supported service mode
([docker/roadmap issue #515, "Open Docker Desktop at startup without logging on Windows"](https://github.com/docker/roadmap/issues/515),
accessed 2026-09-22).

Combined with reality 1 the consequence is direct: **an unattended reboot at 04:00 leaves nobody
logged in, so Docker Desktop never starts and the world stays down until somebody walks over to the
machine.** That is precisely the human dependency [`scope-and-goals.md`](../scope-and-goals.md) goal
G2 exists to remove, reintroduced by the host platform.

### 3. Valheim is UDP-only, and WSL2's documented LAN path is TCP-only

This is the sharpest of the four and the one most likely to stop the project.

Microsoft's own guidance for reaching a WSL2 distribution from the local network in the default NAT
mode is `netsh interface portproxy`
([Microsoft Learn, Accessing network applications with WSL](https://learn.microsoft.com/en-us/windows/wsl/networking),
updated 2026-06-02, accessed 2026-09-22). **`netsh interface portproxy` forwards TCP. It has no UDP
mode.** Valheim's gameplay and query traffic are both UDP and nothing it needs is TCP
([`networking.md`](../networking.md)). So in default NAT mode there is no documented path at all for
the only protocol this project cares about.

The same page documents the route that does exist:

- **Mirrored networking mode**, set with `networkingMode=mirrored` under `[wsl2]` in `.wslconfig`,
  available on **Windows 11 22H2 and higher**. Among its listed benefits: "Connect to WSL directly
  from your local area network (LAN)".
- **The Hyper-V firewall is on by default** on Windows 11 22H2+ with WSL 2.0.9+, and blocks inbound
  traffic until a rule allows it. The page gives both the blanket
  `Set-NetFirewallHyperVVMSetting -DefaultInboundAction Allow` and the targeted
  `New-NetFirewallHyperVRule`, which takes `-Protocol` and `-LocalPorts` and can therefore express
  UDP 2456-2457 specifically.

**One important distinction, because it decides how this is verified.** Docker Desktop does not
publish ports through `netsh portproxy`. It runs its own proxy on the Windows side, and a published
`-p 2456:2456/udp` becomes a Windows listener. That is a different mechanism with a different
answer, and its behaviour for UDP from *external* hosts is not something the vendor documentation
settles either way.

So this ADR does not assert that the UDP path works. **It requires it to be proven, with a datagram
sent from outside the network to a listener behind the published port, before any code depends on
it.** ADR 0002 already rules generic UDP port checkers and `nc -vzu` inadmissible as evidence, for
the same reason. If the proof fails, that is a finding that returns to the design rather than a
thing to work around.

### 4. The host is also the machine the owner plays on

[ADR 0001](0001-host-on-an-owned-always-on-x86-machine.md) assumed a machine whose job is to be a
server. This one has a second job that the owner cares about more.

Two resources are genuinely contended and one is not. **The GPU is not**: a headless dedicated
server runs with `-nographics -batchmode` and does not touch it. **CPU is**, and it is the resource
that degrades Valheim first: the simulation is largely single-threaded, so what matters is that the
server keeps a core's worth of uninterrupted time, not that it gets many cores
([`titles/valheim.md`](../titles/valheim.md)). **Memory is**, because WSL2's virtual machine claims
host RAM and a game client wants several gigabytes of its own.

Both contended resources are capped rather than negotiated: `memory` and `processors` in
`.wslconfig` bound the whole WSL2 virtual machine, and per-container limits bound the game inside
it. The numbers are in [`windows-host.md`](../windows-host.md), because they depend on the machine
and will change; the decision here is only that they are set explicitly rather than left to default.

### 5. A laptop is a machine designed to stop running

Everything in reality 1 was written for a desktop, and a laptop adds three ways
to end the always-on premise that no amount of `powercfg /change standby-timeout-ac 0` addresses.

**Closing the lid suspends it.** This is the most likely way this server dies, it takes one
absent-minded moment, and nothing about it looks like a fault afterwards: the machine is simply
asleep. The lid action has to be set to do nothing while on AC.

**On battery, the AC power policy does not apply.** Windows keeps a separate policy for DC, so a
host that is unplugged will sleep on its own schedule no matter what was configured for AC. The
machine has to stay plugged in, which is a physical operating requirement rather than a setting.

**Modern Standby cannot always be turned off.** Many laptops use S0 low-power idle rather than the
older S3 sleep, and on those the classic timeout settings do not reliably keep the machine awake.
Whether this one does is not knowable from documentation: `powercfg /a` reports which sleep states
the hardware actually supports, and that has to be read rather than assumed.

**Read, and the answer is favourable.** On 2026-09-23 this host reported S3 available and
**S0 Low Power Idle explicitly unsupported by the firmware**. So it is a classic-sleep machine and
the timeout settings above do control it. This is recorded because it closes a real uncertainty,
and because the opposite answer would have meant the always-on premise rested on nothing.

**The one thing a laptop gives back is real, and ADR 0001 wanted it.** That document lists an
uninterruptible power supply as "optional, and the cheapest real upgrade available", because it
turns most domestic power events into a non-event. **A laptop has one built in.** A power cut
becomes a non-event for free, and the BIOS power-on-after-AC-loss setting
[`always-on-operation.md`](../always-on-operation.md) asks for, which most laptops do not offer,
stops mattering as much because the machine never went down.

### 6. Wi-Fi is the network path, and the server is UDP-only

Valheim sends world state to every connected player over UDP, with no retransmission layer
underneath it. Wi-Fi contributes jitter and loss that ethernet does not, and the way that presents
in Valheim is not a disconnection: it is rubber-banding and delayed damage, which
[`titles/valheim.md`](../titles/valheim.md) warns is the same symptom as CPU saturation. **So the
network path and the resource limits can produce an identical complaint**, and telling them apart
later costs an evening.

Two consequences follow immediately:

- **Wi-Fi adapter power saving stops being housekeeping and becomes mandatory.** An adapter that
  idles down on a machine nobody is touching drops the link, and the symptom is a server that was
  reachable and now is not, with nothing in any log to say why.
- **The DHCP reservation must be made against the Wi-Fi adapter's MAC address.** An adapter has
  one MAC per interface, so a reservation made for the ethernet port does nothing while the host
  is on Wi-Fi, and a host that later moves to a cable will silently take a different lease and
  leave the forwarding rule pointing at nothing.

**A cable remains the single cheapest improvement available to this project**, and is recommended
rather than required. It removes reality 6 entirely for the price of a cable, and it is the only
item in this record that trades money for the removal of a whole class of fault.

## Options considered

### A. A Hyper-V Linux virtual machine on an external switch

A real Linux guest, bridged onto the LAN with its own address, Docker Engine inside, the VM set to
start with the host.

- **Would buy:** the strongest answer to all four realities at once. It starts as a service with no
  logon, it has no NAT layer so ADR 0002's port forwarding applies unmodified, its resources are
  capped by construction, and it would make ADR 0001's "runs Linux" true again rather than something
  worked around.
- **Costs:** a fixed RAM carve-out from a gaming machine, and a VM to maintain.
- **Rejected because it does not exist here.** Hyper-V ships on Windows 11 Pro, Enterprise and
  Education. **This host is Home**, which does not include it. Recorded because it is the option to
  revisit if the machine is ever upgraded to Pro, and because a reader on Pro should take it.

### B. Docker Engine inside a WSL2 distribution, no Docker Desktop

Docker Engine installed directly in a WSL2 distribution with systemd enabled, the distribution
started at boot by a Task Scheduler task running as SYSTEM.

- **For:** removes reality 2 entirely. No logon, no auto-logon credential, no Docker Desktop. Fewer
  moving parts in the always-on path, and the part removed is the one that is known to need a
  session.
- **Against:** the boot arrangement is a scheduled task invoking `wsl.exe`, which is a community
  pattern rather than a supported product feature, so it is ours to keep working. Port publishing
  then depends on mirrored networking and the Hyper-V firewall rule rather than on Docker Desktop's
  proxy, which is a different unproven path, not a safer one.
- **Its main cost disappeared on 2026-09-23.** Port publishing was its weak point, because it
  would depend on mirrored networking and the Hyper-V firewall rather than on Docker Desktop's
  proxy. ADR 0009 removed the need for any inbound path, so that objection no longer applies.
- **Verdict:** the strongest technical option available on Home, **re-offered on 2026-09-23 with
  its cost corrected and declined**. It remains the **documented fallback**, and the case for it is
  now stronger than when it was first written: taking it would remove the auto-logon credential
  entirely.

### C. Docker Desktop with the WSL2 backend, mirrored networking (chosen)

- **For:** a supported product with a graphical interface, rather than a boot arrangement of our
  own construction. Its published-port proxy is one mechanism to reason about rather than a chain
  of them, which keeps direct LAN access simple if it is ever wanted.
- **Corrected 2026-09-23.** This option was first argued on the grounds that it was "the
  arrangement the owner already runs and already understands". **That was false**: Docker is not
  installed on the host at all. The second supporting argument, that its proxy gives the UDP
  question a single answer to test, was made moot the same week by
  [ADR 0009](0009-reach-the-server-without-a-router-we-control.md), which chose a relay and
  removed the need for any inbound path. Both reasons for preferring this over option B were
  therefore gone.
  **The choice was put again on that corrected basis and this option was re-affirmed by the
  owner.** It is recorded this way rather than quietly re-justified, because a decision made twice
  on good information is worth more than one that looks like it was never questioned.
- **Against:** it requires a logged-on session, so **Windows auto-logon is a hard prerequisite**,
  and auto-logon stores the account password in LSA secrets where any local administrator can
  retrieve it. On a personal machine that is a bounded cost, but it is a real one and it is the
  price of this option. Mitigated, not removed, by a scheduled task that locks the workstation
  immediately after the automatic logon, so the machine is never left sitting unlocked.
- **Verdict:** chosen by the owner, with the cost accepted knowingly, and chosen again once the
  argument for it had been corrected.

### D. Run `valheim_server.exe` natively on Windows

- **For:** no WSL2, no NAT, no container, and the UDP question disappears.
- **Against:** it abandons [ADR 0004](0004-run-game-servers-as-containers.md) wholesale, and with it
  the dependency isolation and the rebuildable host that made a multi-game platform possible at all.
  Goal G5 would be unreachable.
- **Verdict:** rejected. Recorded because it is the obvious shortcut and someone will propose it.

## Decision

**Run the Linux layer in Docker Desktop with the WSL2 backend, in mirrored networking mode, on a
host configured so that an unattended reboot restores the whole stack without anyone logging in.**

Concretely, and each item exists because of a reality above:

1. **Sleep, hibernation and Fast Startup off.** `powercfg /h off` removes hibernation and Fast
   Startup together; Fast Startup matters because it turns a shutdown into a hibernation and makes
   a "clean boot" not one.
2. **Active Hours covering play hours**, with the reboot itself accepted rather than fought.
3. **Windows auto-logon, plus a lock-on-logon scheduled task.** The prerequisite for reality 2, and
   its mitigation.
4. **Docker Desktop set to start on sign-in**, with the Valheim container on a restart policy, so
   the chain from power-on to a running world needs no human.
5. **`networkingMode=mirrored` in `.wslconfig`**, plus a `New-NetFirewallHyperVRule` admitting UDP
   2456 and 2457 specifically rather than opening the Hyper-V firewall wholesale.
6. **`memory` and `processors` capped in `.wslconfig`**, and per-container limits inside.
7. **The lid action set to do nothing on AC**, and the machine kept plugged in. The first is a
   setting; the second is an operating requirement that no script can enforce.
8. **`powercfg /a` read rather than assumed**, to find out whether this hardware honours the
   classic sleep settings or uses Modern Standby.
9. **Wi-Fi adapter power management off**, and the DHCP reservation made against the **Wi-Fi**
   MAC address.
10. **The state directory lives on the WSL2 ext4 filesystem or in a Docker volume, never under
   `/mnt/c`.** DrvFs does not carry POSIX ownership and permission semantics faithfully, and this
   project already has a documented case of exactly that class of bug destroying every autosave
   while the container reported healthy
   ([valheim-server-docker issue #802](https://github.com/community-valheim-tools/valheim-server-docker/issues/802)).

**Option B is the recorded fallback**, to be taken without re-opening this decision if either the
auto-logon arrangement or Docker Desktop's UDP publishing proves unreliable in practice.

## Consequences

1. **The acceptance test for the host is an unattended reboot**, performed with nobody logged in,
   not a checklist of settings. Settings that look right and do not survive a reboot are the exact
   failure this is guarding against.
2. **Auto-logon is a standing security cost**, not a step. It is in the threat model from now on:
   any local administrator can recover the account password. The lock-on-logon task reduces the
   physical exposure and does nothing about the credential itself.
3. **The UDP path is unproven until it is proven**, and nothing networking-dependent may be built
   on it before then. This is ADR 0002's rule applied to a layer ADR 0002 did not know existed.
4. **`/mnt/c` is out of bounds for state.** This constrains where backups read from and means the
   backup service is the only thing that moves world data across the Windows boundary.
5. **Two new things can now break that Linux hosts do not have:** a WSL2 virtual machine and a
   desktop application in the always-on path. Both are in scope for monitoring.
6. **The documentation's Linux assumption is corrected rather than quietly worked around.** Any
   future reader of 0001 and 0004 reaches this record from the marker on those files.
7. **The host has a built-in UPS**, which is a genuine gain over the desktop this was written for
   and closes the optional upgrade ADR 0001 recommended.
8. **Battery health is now an operational concern.** A laptop kept at full charge on AC
   permanently degrades its battery, and the battery is the UPS. Where the firmware offers a
   charge limit, it is worth setting; where it does not, the UPS is on a clock.
9. **Lag has two plausible causes now, not one.** Wi-Fi jitter and single-core saturation produce
   the same complaint, so the answer to "it is laggy" starts with which of the two it is.
10. **A move to ethernet is a network change, not just an improvement.** It takes a new MAC
    address, so the DHCP reservation and the forwarding rule both have to follow it.

## Revisit if

- **The machine is upgraded to Windows 11 Pro.** Option A becomes available and is better on every
  axis that matters here. This is the single change that would most improve the arrangement.
- **The UDP proof fails.** Take option B, and if that also fails, `-crossplay`, which removes the
  port forwarding requirement entirely at the cost of a join code that rotates on every restart
  ([ADR 0002](0002-reach-the-server-from-the-internet.md)).
- **The auto-logon credential becomes unacceptable**, for example because the machine stops being
  solely the owner's. Option B needs no auto-logon.
- **The owner stops gaming on this machine**, which removes reality 4 and most of the resource
  capping with it.
- **The host moves to ethernet.** This removes reality 6, and is the cheapest available
  improvement to the whole arrangement. Re-run the DHCP reservation against the new MAC.
- **The laptop is replaced by a desktop or mini-PC**, which is what ADR 0001 originally imagined.
  That removes reality 5 and gives back the BIOS power-on setting, at the cost of the free UPS.
