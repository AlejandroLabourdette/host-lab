# Host configuration

Applies the Windows 11 host arrangement decided in
[ADR 0007](../../docs/decisions/0007-host-on-windows-with-docker-desktop-and-wsl2.md) and described
in [`docs/windows-host.md`](../../docs/windows-host.md).

## Run it

From an **elevated** PowerShell prompt, on the host:

```powershell
.\configure-host.ps1 -WslMemory 8GB -WslProcessors 4 -NetAdapter Ethernet
```

Pick the numbers from the sizing table in
[`docs/windows-host.md`](../../docs/windows-host.md#6-resource-limits-on-a-machine-that-is-also-a-gaming-pc),
then measure your own world and correct them.

The script is re-runnable and reports what it found before changing anything. `-WhatIf` shows what
it would do without doing it.

## What it does not do, and why

### Auto-logon

Docker Desktop needs a logged-on session, so an unattended reboot needs auto-logon. That needs the
account password, and a password does not belong in a script, a parameter or a shell history. Do it
by hand:

1. Download [Sysinternals Autologon](https://learn.microsoft.com/en-us/sysinternals/downloads/autologon).
2. Run it, enter the account and password, click Enable.

**Use that tool rather than the `netplwiz` checkbox.** Both reach the same result, but `Autologon`
stores the password in **LSA secrets**, while the manual registry route writes `DefaultPassword` as
**plain text** that anything on the machine can read. The better option is free, so take it.

**The cost:** the account password becomes recoverable by any local administrator. ADR 0007 accepts
that knowingly for a single-owner personal machine, and records the no-auto-logon fallback if it
ever stops being acceptable. The script installs the mitigation, a task that locks the screen the
moment the automatic logon completes.

### Windows Update active hours

Needs a decision about when this household plays, and Windows 11 Home exposes it only in Settings.
Set it under Settings > Windows Update > Advanced options.

Home cannot prevent a restart outside that window, only move it. That is why the acceptance test is
an unattended reboot rather than a check that reboots do not happen.

### BIOS power-on after AC loss

Firmware, not Windows. Set it while you are in there, because it is free and it is invisible until
the first power cut.

## Then

```powershell
wsl --shutdown        # so the new .wslconfig is read
```

and run the acceptance test in
[`docs/windows-host.md`](../../docs/windows-host.md#the-acceptance-test).
