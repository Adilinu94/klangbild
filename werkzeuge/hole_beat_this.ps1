# Holt das Beat-This-Modell (final0, ONNX) in die Assets der Engine.
# Das Modell ist MIT-lizenziert, wird aber wegen der 79 MB nicht eingecheckt
# (*.onnx steht in .gitignore). Nach dem Klonen einmal ausfuehren.
#
#   powershell -ExecutionPolicy Bypass -File werkzeuge/hole_beat_this.ps1

$ErrorActionPreference = "Stop"
$wurzel = Split-Path -Parent $PSScriptRoot
$ziel = Join-Path $wurzel "android/engine/src/main/assets/beat_this.onnx"
$url = "https://raw.githubusercontent.com/mosynthkey/beat_this_cpp/main/onnx/beat_this.onnx"
$soll = "c5c1466e08abdb03fdeb50668a06f244b787d564c212490482231a9cfbe9ccbd"

if (Test-Path $ziel) {
    $ist = (Get-FileHash $ziel -Algorithm SHA256).Hash.ToLower()
    if ($ist -eq $soll) {
        Write-Host "Modell ist vorhanden und stimmt ($([math]::Round((Get-Item $ziel).Length / 1MB, 1)) MB)."
        exit 0
    }
    Write-Host "Vorhandene Datei weicht ab, wird ersetzt."
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ziel) | Out-Null
$ProgressPreference = "SilentlyContinue"
Write-Host "Lade $url ..."
Invoke-WebRequest -Uri $url -OutFile $ziel -UseBasicParsing -TimeoutSec 600

$ist = (Get-FileHash $ziel -Algorithm SHA256).Hash.ToLower()
if ($ist -ne $soll) {
    Remove-Item $ziel
    throw "Pruefsumme falsch: $ist (erwartet $soll)"
}
Write-Host "Fertig: $ziel ($([math]::Round((Get-Item $ziel).Length / 1MB, 1)) MB)"
