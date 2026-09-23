#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Configures a Windows 11 host to run the game server platform unattended.

.DESCRIPTION
    Applies sections 1, 4 and 5 of docs/windows-host.md: power policy, the WSL 2
    configuration, the two firewall rules, and the lock-after-automatic-logon task.

    Re-runnable. Every step reports what it found before it changes anything, and
    nothing here is destructive.

    Two things this script deliberately does NOT do:

      * Auto-logon (section 3). It needs an account password, and a password
        belongs in an interactive prompt rather than in a script, a parameter or
        a shell history. deploy/host/README.md has the procedure.
      * Windows Update active hours (section 2) and the resource numbers
        (section 6). Both need a human decision about this household.

.PARAMETER WslMemory
    Memory ceiling for the whole WSL 2 VM, for example '8GB'. See the sizing
    table in docs/windows-host.md, and measure rather than trust it.

.PARAMETER WslProcessors
    Logical processors for the WSL 2 VM.

.PARAMETER NetAdapter
    Name of the network adapter to disable power management on, as shown by
    Get-NetAdapter. Optional; skipped when not given.

.EXAMPLE
    .\configure-host.ps1 -WslMemory 8GB -WslProcessors 4 -NetAdapter Ethernet
#>
[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)] [string] $WslMemory,
    [Parameter(Mandatory)] [int]    $WslProcessors,
    [string] $NetAdapter
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# WSL's VM creator id, from Microsoft Learn, "Accessing network applications with WSL",
# updated 2026-06-02, accessed 2026-09-22.
$WslVmCreatorId = '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}'

function Write-Step { param([string] $Message) Write-Host "`n== $Message" -ForegroundColor Cyan }
function Write-Ok   { param([string] $Message) Write-Host "   ok    $Message" -ForegroundColor Green }
function Write-Did  { param([string] $Message) Write-Host "   set   $Message" -ForegroundColor Yellow }
function Write-Warn { param([string] $Message) Write-Host "   warn  $Message" -ForegroundColor Red }

# --- Preflight -------------------------------------------------------------
# Mirrored networking needs Windows 11 22H2 or higher. Everything downstream of
# this assumes it, so fail loudly here rather than silently later.

Write-Step 'Checking the Windows version'
$build = [int](Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion').CurrentBuild
if ($build -lt 22621) {
    throw ("Windows build $build is below 22621 (Windows 11 22H2). " +
           'WSL 2 mirrored networking is not available, and there is no documented ' +
           'UDP path to WSL 2 without it. See ADR 0007 for the fallbacks.')
}
Write-Ok "build $build, mirrored networking is available"

# --- 1. Power --------------------------------------------------------------

Write-Step 'Power policy: never sleep, never hibernate, no Fast Startup'
foreach ($setting in 'standby-timeout-ac', 'hibernate-timeout-ac', 'disk-timeout-ac') {
    if ($PSCmdlet.ShouldProcess($setting, 'powercfg /change ... 0')) {
        powercfg /change $setting 0
        Write-Did "$setting = 0 (never)"
    }
}
if ($PSCmdlet.ShouldProcess('hibernation', 'powercfg /hibernate off')) {
    # Also removes Fast Startup, which otherwise makes a "shutdown" a hibernation
    # and means the clean boot you tested is not the one that happens.
    powercfg /hibernate off
    Write-Did 'hibernation and Fast Startup off'
}

# --- Laptop-specific -------------------------------------------------------
# This host is a laptop (ADR 0007 reality 5). Each of the following ends the
# always-on premise on its own, and none of them looks like a fault afterwards.

Write-Step 'Lid action on AC'
$isLaptop = $null -ne (Get-CimInstance -ClassName Win32_Battery -ErrorAction SilentlyContinue)
if (-not $isLaptop) {
    Write-Ok 'no battery detected, so no lid to worry about'
} elseif ($PSCmdlet.ShouldProcess('lid close on AC', 'do nothing')) {
    # SUB_BUTTONS / LIDACTION, 0 = do nothing. AC only: on battery, suspending
    # on a closed lid is still the right behaviour.
    powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0
    powercfg /setactive SCHEME_CURRENT
    Write-Did 'closing the lid on AC now does nothing'
    Write-Warn 'the machine must stay PLUGGED IN: the DC power policy is separate and still sleeps'
}

Write-Step 'Sleep states this hardware actually supports'
# Many laptops use S0 low-power idle rather than S3, and on those the timeout
# settings above are necessary but may not be sufficient. This is not knowable
# from documentation, only from the hardware.
$sleepStates = (powercfg /a) -join "`n"
if ($sleepStates -match 'Standby \(S0 Low Power Idle\)') {
    Write-Warn 'Modern Standby (S0 low power idle). The timeout settings may not be enough.'
    Write-Warn 'Test it: leave the machine untouched for an hour, then check from another machine'
} elseif ($sleepStates -match 'Standby \(S3\)') {
    Write-Ok 'classic S3 sleep, which the timeout settings above do control'
} else {
    Write-Warn 'could not classify the sleep states; read `powercfg /a` by hand'
}

if ($isLaptop) {
    Write-Step 'Battery, which is the UPS on this host'
    # always-on-operation.md calls a UPS the cheapest real upgrade available.
    # A laptop has one built in, and a battery held at 100% on permanent AC
    # degrades, so the UPS is on a clock unless the firmware can cap the charge.
    Write-Ok 'a power cut is absorbed by the battery rather than ending the service'
    Write-Warn 'if the firmware offers a charge limit (typically 60-80%), set it: a battery held at 100% degrades, and it is the UPS'
}

# On a machine nobody touches, an adapter that idles down drops the link, and
# the symptom is a server that was reachable and now is not with nothing in any
# log to say why. On Wi-Fi this is mandatory rather than housekeeping.
if ($NetAdapter) {
    Write-Step "Network adapter power management: $NetAdapter"
    if ($PSCmdlet.ShouldProcess($NetAdapter, 'Disable-NetAdapterPowerManagement')) {
        Disable-NetAdapterPowerManagement -Name $NetAdapter -NoRestart
        Write-Did 'power management disabled (takes effect on next adapter restart)'
    }

    $adapter = Get-NetAdapter -Name $NetAdapter -ErrorAction SilentlyContinue
    if ($adapter) {
        Write-Ok "MAC $($adapter.MacAddress). Reserve the DHCP lease against THIS address"
        if ($adapter.PhysicalMediaType -match 'Native 802.11|Wireless') {
            Write-Warn 'this is Wi-Fi. Valheim is UDP with no retransmission underneath it, so'
            Write-Warn 'jitter shows up in game as rubber-banding, the same symptom as CPU'
            Write-Warn 'saturation. A cable is the cheapest single improvement available here.'
        }
    }
} else {
    Write-Warn 'no -NetAdapter given; skipping. An adapter that sleeps drops the link silently'
    Write-Warn 'Get-NetAdapter lists them. On this host it is the Wi-Fi one.'
}

# --- 4. Docker Desktop -----------------------------------------------------
# Docker Desktop's start-on-sign-in setting lives in its own settings file and is
# not reliably scriptable across versions, so this reports rather than sets it.

Write-Step 'Docker Desktop'
$dockerSettings = Join-Path $env:APPDATA 'Docker\settings-store.json'
if (-not (Test-Path $dockerSettings)) {
    $dockerSettings = Join-Path $env:APPDATA 'Docker\settings.json'
}
if (Test-Path $dockerSettings) {
    $settings = Get-Content $dockerSettings -Raw | ConvertFrom-Json
    if ($settings.PSObject.Properties['AutoStart'] -and $settings.AutoStart) {
        Write-Ok 'set to start on sign-in'
    } else {
        Write-Warn 'NOT set to start on sign-in. Settings > General > "Start Docker Desktop when you sign in"'
    }
} else {
    Write-Warn 'settings file not found; check Settings > General by hand'
}

# --- 5. WSL 2 --------------------------------------------------------------

Write-Step 'WSL 2 configuration'
$wslConfigPath = Join-Path $env:USERPROFILE '.wslconfig'
$wslConfig = @"
# Managed by deploy/host/configure-host.ps1. See docs/windows-host.md section 5.
# Run 'wsl --shutdown' after changing this file.

[wsl2]
# Valheim is UDP-only, and netsh interface portproxy, the documented NAT-mode
# route to WSL 2 from the LAN, has no UDP mode. Mirrored mode is the supported
# path. Requires Windows 11 22H2 or higher.
networkingMode=mirrored

# Left on deliberately. The narrow Hyper-V rule below admits two ports; turning
# this off would open the whole boundary to avoid writing one line.
firewall=true

# Caps, so the machine stays usable for gaming.
memory=$WslMemory
processors=$WslProcessors

# This is an always-on server. The VM must never idle out.
vmIdleTimeout=-1

[general]
# Same reason. A distribution that shuts itself down takes the world with it.
instanceIdleTimeout=-1

[experimental]
# Give cached memory back to Windows, but slowly. The default, dropCache,
# releases it immediately, which means re-reading the world from disk.
autoMemoryReclaim=gradual
"@

if ((Test-Path $wslConfigPath) -and ((Get-Content $wslConfigPath -Raw) -eq $wslConfig)) {
    Write-Ok "$wslConfigPath already correct"
} elseif ($PSCmdlet.ShouldProcess($wslConfigPath, 'write .wslconfig')) {
    if (Test-Path $wslConfigPath) {
        $backup = "$wslConfigPath.bak-$(Get-Date -Format yyyyMMddHHmmss)"
        Copy-Item $wslConfigPath $backup
        Write-Warn "existing file backed up to $backup"
    }
    # UTF8 without BOM: WSL ignores a malformed file and starts normally, so a
    # BOM here would fail silently and look like the settings never applied.
    [IO.File]::WriteAllText($wslConfigPath, $wslConfig, [Text.UTF8Encoding]::new($false))
    Write-Did "$wslConfigPath written. Run 'wsl --shutdown' for it to take effect"
}

# --- Firewall --------------------------------------------------------------

Write-Step 'Hyper-V firewall rule for UDP 2456-2457'
$hyperVRule = Get-NetFirewallHyperVRule -Name 'Valheim-UDP' -ErrorAction SilentlyContinue
if ($hyperVRule) {
    Write-Ok 'rule Valheim-UDP already present'
} elseif ($PSCmdlet.ShouldProcess('Valheim-UDP', 'New-NetFirewallHyperVRule')) {
    New-NetFirewallHyperVRule `
        -Name 'Valheim-UDP' `
        -DisplayName 'Valheim game and query (UDP 2456-2457)' `
        -Direction Inbound `
        -VMCreatorId $WslVmCreatorId `
        -Protocol UDP `
        -LocalPorts 2456-2457 | Out-Null
    Write-Did 'rule Valheim-UDP created'
}

Write-Step 'Windows Defender Firewall rule for UDP 2456-2457'
$fwRule = Get-NetFirewallRule -DisplayName 'Valheim game and query (UDP 2456-2457)' -ErrorAction SilentlyContinue
if ($fwRule) {
    Write-Ok 'rule already present'
} elseif ($PSCmdlet.ShouldProcess('Valheim inbound UDP', 'New-NetFirewallRule')) {
    New-NetFirewallRule `
        -DisplayName 'Valheim game and query (UDP 2456-2457)' `
        -Direction Inbound -Protocol UDP -LocalPort 2456-2457 `
        -Action Allow -Profile Private | Out-Null
    Write-Did 'rule created for the Private profile'
}

# A home LAN marked Public is a common, silent reason a correct rule does nothing.
$public = @(Get-NetConnectionProfile | Where-Object NetworkCategory -eq 'Public')
if ($public.Count -gt 0) {
    Write-Warn ('these networks are marked Public, so the Private-profile rule will not apply: ' +
                ($public.Name -join ', '))
}

# --- 3. Lock after automatic logon ----------------------------------------
# The auto-logon itself is manual (see README.md). This is its mitigation, and
# it is harmless to install before auto-logon exists.

Write-Step 'Lock-after-automatic-logon task'
$taskName = 'Lock after automatic logon'
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Write-Ok 'task already registered'
} elseif ($PSCmdlet.ShouldProcess($taskName, 'Register-ScheduledTask')) {
    # Locks the screen only. The session keeps running, so Docker Desktop and
    # everything under it stay up, which is the whole point.
    $action  = New-ScheduledTaskAction -Execute 'rundll32.exe' -Argument 'user32.dll,LockWorkStation'
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger | Out-Null
    Write-Did 'task registered'
}

# --- Done ------------------------------------------------------------------

Write-Host @"

Done. Still to do by hand, because each needs a decision or a password:

  1. Windows Update active hours       Settings > Windows Update > Advanced options
  2. Auto-logon                        see deploy/host/README.md
  3. Keep the laptop PLUGGED IN        an operating requirement, not a setting
  4. Battery charge limit, if offered  the battery is this host's UPS
  5. wsl --shutdown                    so the new .wslconfig takes effect

Then run BOTH acceptance tests in docs/windows-host.md and record the results:
an unattended reboot, and closing the lid for ten minutes. The second is the
one a desktop would not need and the one most likely to catch something.
"@ -ForegroundColor Cyan
