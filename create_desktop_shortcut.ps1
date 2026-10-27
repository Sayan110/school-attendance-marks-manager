<#
.SYNOPSIS
    Create the "School Attendance & Marks Manager" desktop shortcut.

.DESCRIPTION
    Prefers the packaged EXE (dist\SchoolAttendanceManager\SchoolAttendanceManager.exe).
    Falls back to the local .venv (or PATH pythonw) running main.py, so the shortcut
    still works on a development copy that has not been packaged yet.
#>
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$exe = Join-Path $root "dist\SchoolAttendanceManager\SchoolAttendanceManager.exe"
$icon = Join-Path $root "app.ico"

$desktop = [Environment]::GetFolderPath("Desktop")
if ([string]::IsNullOrWhiteSpace($desktop)) {
    throw "Could not locate the Desktop folder for this user."
}

$shortcutPath = Join-Path $desktop "School Attendance & Marks Manager.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)

if (Test-Path $exe) {
    $shortcut.TargetPath = $exe
    $shortcut.Arguments = ""
    $shortcut.WorkingDirectory = Split-Path -Parent $exe
    if (Test-Path $icon) { $shortcut.IconLocation = "$icon,0" } else { $shortcut.IconLocation = "$exe,0" }
    $mode = "packaged EXE"
}
else {
    $pythonw = Join-Path $root ".venv\Scripts\pythonw.exe"
    if (-not (Test-Path $pythonw)) {
        $found = Get-Command pythonw.exe -ErrorAction SilentlyContinue
        if ($null -eq $found) {
            throw "Neither the packaged EXE nor pythonw.exe was found. Run setup.bat or build_exe.bat first."
        }
        $pythonw = $found.Source
    }
    $shortcut.TargetPath = $pythonw
    $shortcut.Arguments = '"' + (Join-Path $root "main.py") + '"'
    $shortcut.WorkingDirectory = $root
    if (Test-Path $icon) { $shortcut.IconLocation = "$icon,0" }
    $mode = "Python source (pythonw.exe)"
}

$shortcut.Description = "School Attendance & Marks Manager - SHIKSHA VIKASH ENGLISH HIGH SCHOOL"
$shortcut.WindowStyle = 1
$shortcut.Save()

Write-Host "Created shortcut: $shortcutPath"
Write-Host "Launch target:    $($shortcut.TargetPath)"
Write-Host "Mode:             $mode"
Write-Host "Working folder:   $($shortcut.WorkingDirectory)"
Write-Host "Icon:             $($shortcut.IconLocation)"
