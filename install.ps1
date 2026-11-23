# Paper Wiki installer for Windows.
# Kept ASCII-only on purpose: Windows PowerShell 5.1 misreads UTF-8 scripts without a BOM.
# -NoLaunch   : do not start the app afterwards (use this when a tool such as Claude Code runs the installer)
# -NoShortcut : do not create the desktop shortcut
param([switch]$NoLaunch, [switch]$NoShortcut)

Set-Location -LiteralPath $PSScriptRoot
Write-Host ""
Write-Host "== Paper Wiki setup ==" -ForegroundColor Cyan

# 1) Find Python 3.10 or newer
$python = $null
foreach ($candidate in @("python", "py")) {
    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if (-not $cmd) { continue }
    $ver = & $cmd.Source -c "import sys; print('%d.%d' % sys.version_info[:2])"
    if ($LASTEXITCODE -eq 0 -and $ver -and ([version]$ver -ge [version]"3.10")) { $python = $cmd.Source; break }
}
if (-not $python) {
    Write-Host "Python 3.10 or newer is required." -ForegroundColor Red
    Write-Host "Install it from https://www.python.org/downloads/ (check 'Add python.exe to PATH'), then run install.bat again."
    exit 1
}
Write-Host "Python: $python"

# 2) Private environment for the app (nothing is installed system-wide)
$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPy)) {
    Write-Host "Creating environment (.venv) ..."
    & $python -m venv .venv
    if ($LASTEXITCODE -ne 0) { Write-Host "Could not create the environment." -ForegroundColor Red; exit 1 }
}
Write-Host "Installing packages (this can take a minute) ..."
& $venvPy -m pip install --quiet --upgrade pip
& $venvPy -m pip install --quiet -e .
if ($LASTEXITCODE -ne 0) { Write-Host "Package installation failed. Check your internet connection and try again." -ForegroundColor Red; exit 1 }

# 3) Desktop shortcut
$exe = Join-Path $PSScriptRoot ".venv\Scripts\paperwiki.exe"
if (-not $NoShortcut) { try {
    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath("Desktop")) "Paper Wiki.lnk"))
    $lnk.TargetPath = $exe
    $lnk.WorkingDirectory = $PSScriptRoot
    $lnk.Description = "Paper Wiki"
    $lnk.Save()
    Write-Host "Added a 'Paper Wiki' shortcut to your desktop."
} catch {
    Write-Host "Could not create the desktop shortcut. You can start the app with PaperWiki.bat instead."
} }

Write-Host ""
Write-Host "Installation finished." -ForegroundColor Green
if (-not $NoLaunch) {
    Write-Host "Starting Paper Wiki. Your browser will open the setup page."
    & $exe
} else {
    Write-Host "Next steps (the app was not started):"
    Write-Host "  1. See where the wiki can live:   `"$exe`" setup --list"
    Write-Host "  2. Choose a place, install skill: `"$exe`" setup --vault `"<folder>`" --skill"
    Write-Host "  3. Check:                         `"$exe`" doctor"
}
