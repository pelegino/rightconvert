<#
.SYNOPSIS
    Installs RightConvert: the conversion tools, the "Convert" Explorer menu and the rightconvert command.

.EXAMPLE
    .\install.ps1                    install everything, ask about LibreOffice
    .\install.ps1 -WithLibreOffice   install LibreOffice without asking
    .\install.ps1 -NoLibreOffice     skip LibreOffice
    .\install.ps1 -SkipDeps          only reinstall RightConvert and refresh the menu
#>
[CmdletBinding()]
param([switch]$WithLibreOffice, [switch]$NoLibreOffice, [switch]$SkipDeps)

# Not 'Stop' globally: Windows PowerShell 5.1 would treat any stderr output from winget or python
# as fatal. Native exit codes are checked explicitly and file operations use -ErrorAction Stop.
$PSDefaultParameterValues = @{ 'Copy-Item:ErrorAction' = 'Stop'; 'New-Item:ErrorAction' = 'Stop'; 'Set-Content:ErrorAction' = 'Stop' }
$Repo = Split-Path -Parent $PSScriptRoot
$Dest = Join-Path $env:LOCALAPPDATA 'RightConvert'

function Test-Installed([string]$Id) {
    $null = winget list --id $Id --exact --accept-source-agreements 2>$null
    return $LASTEXITCODE -eq 0
}

function Install-Package([string]$Id, [string]$Name) {
    if (Test-Installed $Id) { Write-Host "$Name is already installed."; return }
    Write-Host "Installing $Name..."
    winget install --id $Id --exact --silent --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0 -and -not (Test-Installed $Id)) { throw "Installing $Name failed (winget exit code $LASTEXITCODE)." }
}

function Find-Python {
    # The python.exe in WindowsApps is a Microsoft Store shortcut, not an interpreter.
    $candidates = @()
    $candidates += Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe", "$env:ProgramFiles\Python3*\python.exe" -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | ForEach-Object FullName
    if (Get-Command py -ErrorAction SilentlyContinue) { $candidates += (& py -3 -c 'import sys; print(sys.executable)' 2>$null) }
    $candidates += Get-Command python -All -ErrorAction SilentlyContinue | Where-Object Source -notlike '*WindowsApps*' | ForEach-Object Source
    foreach ($python in $candidates | Where-Object { $_ } | Select-Object -Unique) {
        & $python -c 'import sys, tkinter; sys.exit(sys.version_info < (3, 9))' 2>$null
        if ($LASTEXITCODE -eq 0 -and (Test-Path (Join-Path (Split-Path $python) 'pythonw.exe'))) { return $python }
    }
    return $null
}

if (-not $SkipDeps) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw 'winget is required. Install "App Installer" from the Microsoft Store and run this script again.'
    }
    if (-not (Find-Python)) { Install-Package 'Python.Python.3.12' 'Python' }
    Install-Package 'Gyan.FFmpeg' 'FFmpeg'
    Install-Package 'ImageMagick.ImageMagick' 'ImageMagick'
    Install-Package 'oschwartz10612.Poppler' 'Poppler'
    Install-Package 'JohnMacFarlane.Pandoc' 'Pandoc'

    if (Test-Installed 'TheDocumentFoundation.LibreOffice') {
        Write-Host 'LibreOffice is already installed.'
    } else {
        $libreoffice = $WithLibreOffice
        if (-not $WithLibreOffice -and -not $NoLibreOffice) {
            Write-Host 'LibreOffice (about 1 GB) enables Word/Excel/PowerPoint conversions and anything-to-PDF for documents.'
            $libreoffice = (Read-Host 'Install LibreOffice? [y/N]') -match '^[yY]'
        }
        if ($libreoffice) { Install-Package 'TheDocumentFoundation.LibreOffice' 'LibreOffice' }
        else { Write-Host 'Skipping LibreOffice. Office formats will be hidden from the Convert menu.' }
    }
}

$python = Find-Python
if (-not $python) { throw 'Python 3.9 or newer (with tkinter) was not found. Install it with: winget install Python.Python.3.12' }

Write-Host "Installing RightConvert to $Dest..."
foreach ($dir in 'bin', 'rightconvert', 'windows') {
    Remove-Item (Join-Path $Dest $dir) -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force (Join-Path $Dest $dir) | Out-Null
}
Copy-Item (Join-Path $Repo 'bin\rightconvert') (Join-Path $Dest 'bin')
Copy-Item (Join-Path $Repo 'rightconvert\*.py') (Join-Path $Dest 'rightconvert')
Copy-Item (Join-Path $PSScriptRoot '*') (Join-Path $Dest 'windows')
Copy-Item (Join-Path $Repo 'LICENSE') $Dest
Set-Content -Encoding ASCII (Join-Path $Dest 'bin\rightconvert.cmd') "@`"$python`" `"%~dp0rightconvert`" %*"

$bin = Join-Path $Dest 'bin'
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if (($userPath -split ';') -notcontains $bin) {
    [Environment]::SetEnvironmentVariable('Path', (($userPath, $bin) | Where-Object { $_ }) -join ';', 'User')
    Write-Host "Added $bin to your PATH (open a new terminal to use 'rightconvert')."
}

& $python (Join-Path $Dest 'bin\rightconvert') --register
if ($LASTEXITCODE -ne 0) { throw 'Registering the Explorer menu failed.' }

Write-Host ''
Write-Host 'Done. Right-click any file in Explorer and hover Convert to pick a format.'
Write-Host 'On Windows 11, Convert is under "Show more options" (or Shift+right-click).'
Write-Host 'After installing new tools (like LibreOffice), run this script again with -SkipDeps to refresh the menu.'
