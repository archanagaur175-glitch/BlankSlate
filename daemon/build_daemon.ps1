$ErrorActionPreference = "Stop"

Set-Location -LiteralPath $PSScriptRoot

python -m PyInstaller pyinstaller/blankslate.spec --noconfirm --clean

$src = Join-Path $PSScriptRoot "dist/BlankslateDaemon"
$dst = Join-Path $PSScriptRoot "../hud/src-tauri/resources/daemon"

if (Test-Path -LiteralPath $dst) {
    Remove-Item -Recurse -Force -LiteralPath $dst
}
New-Item -ItemType Directory -Force -Path $dst | Out-Null
Copy-Item -Recurse -Force -Path "$src/*" -Destination $dst

function Measure-Folder($p) {
    $items = Get-ChildItem -Recurse -LiteralPath $p -ErrorAction SilentlyContinue
    $bytes = ($items | Where-Object { -not $_.PSIsContainer } | Measure-Object -Property Length -Sum).Sum
    $dlls = ($items | Where-Object { $_.Extension -ieq '.dll' }).Count
    $mb = if ($bytes) { [math]::Round($bytes / 1MB, 1) } else { 0 }
    $top = $items | Where-Object { -not $_.PSIsContainer } | Sort-Object Length -Descending | Select-Object -First 8 | ForEach-Object { "$($_.Name): $([math]::Round($_.Length/1MB,1))MB" }
    return "size=${mb}MB dlls=$dlls`n  " + ($top -join "`n  ")
}

Write-Output "Bundled daemon copied to $dst"
Write-Output "COLLECT folder (dist/BlankslateDaemon):`n  $(Measure-Folder $src)"
Write-Output "Tauri resources/daemon:`n  $(Measure-Folder $dst)"
