$ErrorActionPreference = "Stop"

Set-Location -LiteralPath $PSScriptRoot

# ---------------------------------------------------------------------------
# Pre-fetch the ML models so the frozen daemon is fully offline/self-contained.
# Skipped automatically when already present (e.g. a local cache). The STT model
# is ~140 MB and the wake-word ONNX models are a few MB; the frozen interpreter
# cannot reliably reach HuggingFace/GitHub at runtime, so we bundle them here.
# ---------------------------------------------------------------------------
$models = Join-Path $PSScriptRoot "models"
$stt = Join-Path $models "faster-whisper-base.en"
$ow = Join-Path $models "openwakeword"
New-Item -ItemType Directory -Force -Path $stt, $ow | Out-Null

function Get-Model($url, $out) {
    if (Test-Path -LiteralPath $out) {
        Write-Output "cached: $(Split-Path $out -Leaf)"
        return
    }
    Write-Output "download: $url"
    & curl.exe -sS -L --retry 3 -o $out $url
    if (-not (Test-Path -LiteralPath $out)) {
        throw "failed to download $url"
    }
}

$hf = "https://huggingface.co/Systran/faster-whisper-base.en/resolve/main"
Get-Model "$hf/config.json"    (Join-Path $stt "config.json")
Get-Model "$hf/tokenizer.json" (Join-Path $stt "tokenizer.json")
Get-Model "$hf/vocabulary.txt" (Join-Path $stt "vocabulary.txt")
Get-Model "$hf/model.bin"      (Join-Path $stt "model.bin")

$gh = "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1"
Get-Model "$gh/hey_jarvis_v0.1.onnx" (Join-Path $ow "hey_jarvis_v0.1.onnx")
Get-Model "$gh/embedding_model.onnx"  (Join-Path $ow "embedding_model.onnx")
Get-Model "$gh/melspectrogram.onnx"   (Join-Path $ow "melspectrogram.onnx")

python -m PyInstaller pyinstaller/blankslate.spec --noconfirm --clean

$src = Join-Path $PSScriptRoot "dist/BlankslateDaemon"
$dst = Join-Path $PSScriptRoot "../hud/src-tauri/resources/daemon"

if (Test-Path -LiteralPath $dst) {
    Remove-Item -Recurse -Force -LiteralPath $dst
}
New-Item -ItemType Directory -Force -Path $dst | Out-Null
Copy-Item -Recurse -Force -Path "$src/*" -Destination $dst

Write-Output "Bundled daemon copied to $dst"
