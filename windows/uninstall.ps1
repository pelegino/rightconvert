<#
.SYNOPSIS
    Removes the Convert Explorer menu, the rightconvert command and its files. Tools installed with winget are kept.
#>
param([switch]$Pause)
$ErrorActionPreference = 'Stop'
$Dest = Join-Path $env:LOCALAPPDATA 'RightConvert'
$bin = Join-Path $Dest 'bin'

# Delete the menu keys directly, so uninstalling works even if Python is gone.
$classes = 'HKCU:\Software\Classes'
Get-ChildItem "$classes\SystemFileAssociations" -ErrorAction SilentlyContinue | ForEach-Object {
    Remove-Item "$($_.PSPath)\shell\RightConvert" -Recurse -Force -ErrorAction SilentlyContinue
}
Remove-Item "$classes\Directory\shell\RightConvert" -Recurse -Force -ErrorAction SilentlyContinue
Add-Type -Namespace RightConvert -Name Shell -MemberDefinition '[DllImport("shell32.dll")] public static extern void SHChangeNotify(int e, uint f, System.IntPtr a, System.IntPtr b);'
[RightConvert.Shell]::SHChangeNotify(0x08000000, 0, [IntPtr]::Zero, [IntPtr]::Zero)

$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($userPath) {
    [Environment]::SetEnvironmentVariable('Path', (($userPath -split ';') | Where-Object { $_ -and $_ -ne $bin }) -join ';', 'User')
}

Set-Location $env:TEMP
Remove-Item $Dest -Recurse -Force -ErrorAction SilentlyContinue

Write-Host 'Removed RightConvert and its Explorer menu.'
if (Test-Path $Dest) { Write-Host "Some files in $Dest were in use. Delete that folder after closing open windows." }
Write-Host 'Tools installed with winget were kept. Remove them with:'
foreach ($id in 'Gyan.FFmpeg', 'ImageMagick.ImageMagick', 'oschwartz10612.Poppler', 'JohnMacFarlane.Pandoc', 'TheDocumentFoundation.LibreOffice') {
    Write-Host "  winget uninstall --id $id"
}
if ($Pause) { Read-Host 'Press Enter to close' | Out-Null }
