# Commissioning

> Status: in progress
> Last reviewed: 2026-09-23

Everything that can be built away from the host is built and tested. **What is
left needs the host itself**, and this document is that work: the order to do it
in, what each step should print, and what it means when it does not.

[`titles/valheim.md`](titles/valheim.md) has the design-level walkthrough, which
applies to anyone. This is *this* deployment on *this* machine, with the
decisions already made.

## Where things stand

| | |
|---|---|
| Machinery, manifest, images, backup, control plane | **Built and tested.** 162 tests |
| Networking branch | **Decided.** Relay, per [ADR 0009](decisions/0009-reach-the-server-without-a-router-we-control.md). No router work |
| Telegram | **Working.** Bot created, send and edit both verified in the group |
| Windows host configuration | **Written, not applied** |
| A Valheim server that has ever run | **No** |
| A backup that has ever been restored | **No.** See [what is not yet true](#what-is-not-yet-true) |

## Before starting

| | |
|---|---|
| Docker Desktop installed, "Start when you sign in" enabled | Nothing below works without it |
| World name, password and `DeathPenalty` agreed with the group | The password must not appear inside the server or world name |
| Backblaze B2 or Cloudflare R2 account and application key | Only needed from step 6 |

## The sequence

### 1. Check the host script parses, then run it

```powershell
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile(
    "$PWD\deploy\host\configure-host.ps1", [ref]$null, [ref]$errors) | Out-Null
if ($errors) { $errors } else { "parses cleanly" }
```

It was written on a machine with no PowerShell, so it has never been parsed by
the thing that will run it. Then, **elevated**:

```powershell
.\deploy\host\configure-host.ps1 -WslMemory 12GB -WslProcessors 8 -NetAdapter 'Wi-Fi 2'
```

**Expect** it to report the build as at least 22621, set the power policy, set
the lid action, report **classic S3 sleep**, write `.wslconfig`, and create both
firewall rules. It prints the Wi-Fi MAC; that is only informational here,
because under ADR 0009 there is no router rule to point at it.

**If it reports Modern Standby**, the sleep settings may not hold and the
one-hour test in [`windows-host.md`](windows-host.md) becomes a gate rather than
a confirmation. This host reported S3 on 2026-09-23, so that would be a change.

Then by hand: Windows Update active hours, auto-logon (see
[`../deploy/host/README.md`](../deploy/host/README.md)), and `wsl --shutdown`.

### 2. The unattended reboot, and the lid

Both tests are in [`windows-host.md`](windows-host.md#the-acceptance-test). Do
them **now**, before there is a world to lose, with a throwaway container.

The lid test is the one a desktop would not need and the one most likely to
catch something: it needs no update, no power cut and no crash, just somebody
closing a laptop.

**Record both results in that document.** A number there is the difference
between believing the host is always-on and knowing it.

### 3. Build the images

```powershell
docker build --platform linux/amd64 -t hostlab/valheim:1.0.15 images/valheim
docker build -f images/hostlab/Dockerfile -t hostlab:0.1.0 .
```

The first is the one that could not be verified away from the host: SteamCMD's
32-bit client crashes under emulation on Apple Silicon, so **this is the first
time that build has ever run**. Tag it with the version you actually get:

```powershell
docker run --rm --entrypoint cat hostlab/valheim:1.0.15 `
    /opt/valheim/steamapps/appmanifest_896660.acf | Select-String buildid
```

### 4. Configure and start the world

Copy `deploy/.env.example` to `deploy/.env` and fill it in. Put the world
settings in `deploy/valheim/valheim.yaml`. Then:

```powershell
uv run hostlab plan valheim --instance deploy/valheim/valheim.yaml
```

**Read what it prints.** It runs every refusal and writes nothing, so it is the
cheap way to find out that a password breaks a rule, because the server's way of
telling you is to exit in a way that looks like a crash.

```powershell
uv run hostlab compose valheim --instance deploy/valheim/valheim.yaml `
    --out deploy/valheim/compose.yaml
docker compose --env-file deploy/.env -f deploy/valheim/compose.yaml up -d
```

### 5. The first four rungs

Work down [the ladder](titles/valheim.md#verify-it-worked), stopping at the
first failure.

| Check | Command |
|---|---|
| Ports are **udp**, not tcp | `docker exec valheim sh -c 'ss -tulpn \| grep 245'` |
| The world loaded and is the right one | `docker logs valheim` |
| A save completes | `uv run hostlab state valheim --state-dir ...` shows a generation with a recent `.ok` |
| **A stop produces a fresh `.ok`** | Stop it, then look again |

That last one is the half of the SIGINT claim that only the real server can
answer. The container plumbing half is already tested; this is Iron Gate's half.

### 6. Backups, then the drill

```powershell
uv run hostlab backup valheim --state-dir ... --repo <b2 or r2>
uv run hostlab snapshots valheim
```

Then **the restore drill**, in full, from
[`save-data-and-backups.md`](save-data-and-backups.md#the-restore-drill): a
backup picked at random rather than the newest, restored to a **different**
`-savedir` on a **different** port, started, connected to, and inspected for
buildings, chest contents and explored map. Time it end to end and write the
number down.

**ADR 0003 is explicit that a backup is not accepted until it has been
restored.** Until this is done, this project has not met the goal it exists for.

### 7. The platform services

```powershell
cd deploy\platform
docker compose --env-file ..\.env up -d docker-socket hostlab-agent
docker logs -f hostlab-agent
```

**Expect** the join code in the status message within five minutes, and the
message to be **edited in place** rather than a new one arriving each cycle.
Pin it in the group.

### 8. The rung that matters

**A friend connects from outside the network, using the join code.** Under
ADR 0009 that is the only reachability test that means anything: an A2S query
from outside cannot answer and the server will not appear in the community
browser, both by design.

Then record the whole ladder in
[`titles/valheim.md`](titles/valheim.md#verify-it-worked) with dates.

## What is not yet true

Stated plainly, because the rest of this repository reads as though the platform
works, and these are the claims that have not been earned yet.

| Claim | Status |
|---|---|
| A Valheim server has run on this host | **No.** Never started |
| The image builds with the SteamCMD fetch | **Unverified.** Could not be built away from an x86-64 machine |
| SIGINT makes the server save cleanly | **Half.** The plumbing delivers SIGINT, measured. Whether the server saves on receiving one is untested |
| The host survives an unattended reboot | **Unverified.** The settings are written and have never been exercised |
| The host survives a closed lid | **Unverified**, and it is the most likely failure |
| A backup can be restored | **Unverified with real data.** A full restic round trip passes against synthetic saves, which is not the drill |
| A friend can connect | **Unverified** |
| Crossplay works from this network | **Unverified.** The relay needs no inbound path, so it should, and "should" is why this line exists |
| The join code appears in the log as expected | **Unverified against a real server.** The pattern comes from community documentation and Iron Gate publishes no log reference. **If the wording differs, publication breaks silently while the server works perfectly** |

The last one is the most fragile thing in the project and the cheapest to check:
the first crossplay start will either show the line or not.

## What is deliberately not built

- **Start, stop or restart for anyone.** [ADR 0006](decisions/0006-give-friends-a-control-plane.md)
  stages it and its trigger, a second title competing for the machine, has not
  happened. The read-only boundary is enforced by
  [ADR 0010](decisions/0010-reach-the-runtime-through-a-read-only-proxy.md)'s
  proxy rather than by our restraint.
- **A second title.** The manifest makes one possible; bending the design toward
  a hypothetical one is what `platform-architecture.md` warns against.
- **Any panel or web UI**, and **mods**.
