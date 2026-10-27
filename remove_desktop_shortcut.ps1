<#
.SYNOPSIS
    Remove the "School Attendance & Marks Manager" desktop shortcut.

.NOTES
    Only the shortcut is deleted. The application, its database and its
    backups are never touched.
#>
$ErrorActionPreference = "Stop"

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "School Attendance & Marks Manager.lnk"

if (Test-Path $shortcutPath) {
    Remove-Item $shortcutPath -Force
    Write-Host "Removed shortcut: $shortcutPath"
}
else {
    Write-Host "No shortcut found at: $shortcutPath"
}

Write-Host "Application files and school data were left untouched."
