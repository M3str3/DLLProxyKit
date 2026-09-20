# Requires elevation. Usage:
#   sudo powershell -NoProfile -File tests\setup-testpath.ps1

$dir = "C:\Pruebax64\bin"
New-Item -ItemType Directory -Force -Path $dir | Out-Null

$user = $env:USERNAME
icacls "C:\Pruebax64" /grant "${user}:(OI)(CI)M" /T

$machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
$entry = "C:\Pruebax64\bin"
if ($machine -notlike "*$entry*") {
    $next = $machine.TrimEnd(";") + ";" + $entry
    [Environment]::SetEnvironmentVariable("Path", $next, "Machine")
}

Write-Host "dir exists:" (Test-Path $dir)
Write-Host "acl:"
icacls "C:\Pruebax64"
Write-Host "machine PATH entry:"
([Environment]::GetEnvironmentVariable("Path", "Machine") -split ";") |
    Where-Object { $_ -like "*Prueba*" }
