<#
.SYNOPSIS
    Install CustomWhisper: create the virtual environment, install dependencies,
    and create a windowless "Hey Jarvis" desktop shortcut.

.DESCRIPTION
    Idempotent — safe to re-run. Run from anywhere:
        powershell -ExecutionPolicy Bypass -File install.ps1

.PARAMETER SkipDeps
    Skip the pip install step (only (re)create the venv and the shortcut).

.PARAMETER NoShortcut
    Don't create the desktop shortcut.
#>
[CmdletBinding()]
param(
    [switch]$SkipDeps,
    [switch]$NoShortcut
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$venv = Join-Path $root 'venv'
$venvPy = Join-Path $venv 'Scripts\python.exe'
$venvPyw = Join-Path $venv 'Scripts\pythonw.exe'

function Info($m) { Write-Host "==> $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "    $m" -ForegroundColor Green }
function Warn($m) { Write-Host "    $m" -ForegroundColor Yellow }

# 1. Find a Python 3.11 interpreter to build the venv from -----------------
function Find-Python {
    # Prefer the py launcher pinned to 3.11, then any py 3, then PATH python.
    $candidates = @(
        @{ exe = 'py';     args = @('-3.11') },
        @{ exe = 'py';     args = @('-3')    },
        @{ exe = 'python'; args = @()        }
    )
    foreach ($c in $candidates) {
        $cmd = Get-Command $c.exe -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        try {
            $ver = & $c.exe @($c.args + '--version') 2>&1
            if ($ver -match 'Python (\d+)\.(\d+)') {
                return [PSCustomObject]@{
                    Exe = $c.exe; Args = $c.args
                    Major = [int]$Matches[1]; Minor = [int]$Matches[2]; Version = "$ver".Trim()
                }
            }
        } catch { }
    }
    return $null
}

Info 'Locating Python...'
$py = Find-Python
if (-not $py) {
    throw "Python not found. Install Python 3.11 from https://www.python.org/downloads/ and re-run."
}
Ok "Using $($py.Version)"
if (-not ($py.Major -eq 3 -and $py.Minor -eq 11)) {
    Warn "This project targets Python 3.11; you have $($py.Major).$($py.Minor). Continuing, but faster-whisper/PyQt5 wheels may not match."
}

# 2. Create the virtual environment ---------------------------------------
if (Test-Path $venvPy) {
    Info "Virtual environment already exists at .\venv"
} else {
    Info 'Creating virtual environment (.\venv)...'
    & $py.Exe @($py.Args + @('-m', 'venv', $venv))
    if (-not (Test-Path $venvPy)) { throw "venv creation failed (missing $venvPy)." }
    Ok 'venv created'
}

# 3. Install dependencies --------------------------------------------------
if ($SkipDeps) {
    Warn 'Skipping dependency install (-SkipDeps).'
} else {
    $req = Join-Path $root 'requirements-win.txt'
    if (-not (Test-Path $req)) { throw "Missing $req" }
    Info 'Upgrading pip...'
    & $venvPy -m pip install --upgrade pip --quiet
    Info 'Installing dependencies from requirements-win.txt (this can take a few minutes)...'
    & $venvPy -m pip install -r $req
    if ($LASTEXITCODE -ne 0) { throw "pip install failed (exit $LASTEXITCODE)." }
    Ok 'Dependencies installed'
}

# 4. Create the desktop shortcut ------------------------------------------
if ($NoShortcut) {
    Warn 'Skipping desktop shortcut (-NoShortcut).'
} else {
    Info 'Creating desktop shortcut...'
    $desktop = [Environment]::GetFolderPath('Desktop')   # resolves to OneDrive desktop if redirected
    $lnkPath = Join-Path $desktop 'CustomWhisper.lnk'
    $launcher = Join-Path $root 'Start Hands-Free.pyw'
    $icon = Join-Path $root 'assets\ww-custom.ico'
    if (-not (Test-Path $venvPyw)) { throw "Missing $venvPyw" }
    if (-not (Test-Path $launcher)) { throw "Missing $launcher" }

    $sh = New-Object -ComObject WScript.Shell
    $s = $sh.CreateShortcut($lnkPath)
    $s.TargetPath = $venvPyw
    $s.Arguments = '"Start Hands-Free.pyw"'
    $s.WorkingDirectory = $root
    if (Test-Path $icon) { $s.IconLocation = "$icon,0" }
    $s.Description = 'Start CustomWhisper hands-free (Hey Jarvis)'
    $s.WindowStyle = 7
    $s.Save()
    Ok "Shortcut: $lnkPath"
}

Write-Host ''
Info 'Done.'
Write-Host '    - Double-click "CustomWhisper" on your desktop, then say "Hey Jarvis".' -ForegroundColor Green
Write-Host '    - Or run "Start CustomWhisper.pyw" for hotkey-only mode (Right-Ctrl+Space).' -ForegroundColor Green
Write-Host '    - Run "Stop CustomWhisper.pyw" to shut everything down.' -ForegroundColor Green
