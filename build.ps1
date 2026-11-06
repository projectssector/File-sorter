$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $root

function Invoke-Step {
    param(
        [string]$Label,
        [string]$FilePath,
        [string[]]$Arguments
    )
    Write-Host $Label
    $outFile = Join-Path $env:TEMP ("fs_build_" + [guid]::NewGuid().ToString("N") + ".out")
    $errFile = Join-Path $env:TEMP ("fs_build_" + [guid]::NewGuid().ToString("N") + ".err")
    try {
        $proc = Start-Process -FilePath $FilePath -ArgumentList $Arguments -NoNewWindow -Wait -PassThru -RedirectStandardOutput $outFile -RedirectStandardError $errFile
        if (Test-Path -LiteralPath $outFile) { Get-Content -LiteralPath $outFile | ForEach-Object { Write-Host $_ } }
        if (Test-Path -LiteralPath $errFile) { Get-Content -LiteralPath $errFile | ForEach-Object { Write-Host $_ } }
        if ($proc.ExitCode -ne 0) { throw "$Label failed with exit code $($proc.ExitCode)" }
    } finally {
        Remove-Item -LiteralPath $outFile, $errFile -Force -ErrorAction SilentlyContinue
    }
}

Invoke-Step "Installing/updating build dependencies..." "python" @("-m", "pip", "install", "--upgrade", "-r", "requirements.txt")
Invoke-Step "Generating icon..." "python" @("make_icon.py")

$legacyConfig = Join-Path (Split-Path -Parent $root) "commands.ini"
$seedConfig = Join-Path $root "seed_commands.ini"
if (Test-Path -LiteralPath $legacyConfig) {
    Copy-Item -LiteralPath $legacyConfig -Destination $seedConfig -Force -ErrorAction Stop
    Write-Host "Seeded installer commands from $legacyConfig"
} else {
    Remove-Item -LiteralPath $seedConfig -Force -ErrorAction SilentlyContinue
}

Invoke-Step "Building FileSorter.exe..." "python" @("-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed", "--name", "FileSorter", "--icon", "icon.ico", "--add-data", "icon.ico;.", "--hidden-import", "PIL._tkinter_finder", "file_sorter.py")
if (-not (Test-Path -LiteralPath "dist\FileSorter.exe")) { throw "PyInstaller did not produce dist\FileSorter.exe" }

Copy-Item -LiteralPath "dist\FileSorter.exe" -Destination "FileSorter.exe" -Force -ErrorAction Stop
Write-Host "Standalone exe: $root\FileSorter.exe"

$isccCandidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
)
$iscc = $isccCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 was not found. Install it with: winget install JRSoftware.InnoSetup" }

Remove-Item -LiteralPath "installer_output\FileSorterSetup-1.3.0.exe" -Force -ErrorAction SilentlyContinue
Invoke-Step "Building installer with $iscc ..." $iscc @("installer.iss")

$setup = Join-Path $root "installer_output\FileSorterSetup-1.3.0.exe"
if (-not (Test-Path -LiteralPath $setup)) { throw "Installer not found: $setup" }
Copy-Item -LiteralPath $setup -Destination (Join-Path $root "FileSorterSetup.exe") -Force -ErrorAction Stop
Write-Host "Installer: $root\FileSorterSetup.exe"

