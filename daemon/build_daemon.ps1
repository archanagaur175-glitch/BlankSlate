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

Write-Output "Bundled daemon copied to $dst"
