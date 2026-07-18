$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\env.ps1" -Quiet

Write-Host "== Project =="
Write-Host $env:PHONE_CAPTURE_LAB

Write-Host "`n== ADB =="
& $env:PHONE_CAPTURE_ADB version

Write-Host "`n== scrcpy =="
& $env:PHONE_CAPTURE_SCRCPY --version

Write-Host "`n== ffmpeg =="
ffmpeg -version | Select-Object -First 1

Write-Host "`n== Android SDK =="
Write-Host "ANDROID_HOME=$env:ANDROID_HOME"
Write-Host "JAVA_HOME=$env:JAVA_HOME"
java -version
& $env:PHONE_CAPTURE_SDKMANAGER --sdk_root=$env:ANDROID_HOME --version
if (!(Test-Path -LiteralPath (Join-Path $env:ANDROID_HOME 'platforms\android-37.0\android.jar'))) {
  throw "Android platform android-37.0 not found"
}
if (!(Test-Path -LiteralPath (Join-Path $env:ANDROID_HOME 'build-tools\37.0.0\aapt2.exe'))) {
  throw "Android build-tools 37.0.0 not found"
}
if (!(Test-Path -LiteralPath (Join-Path $env:ANDROID_HOME 'ndk\29.0.14206865\source.properties'))) {
  throw "Android NDK 29.0.14206865 not found"
}

Write-Host "`n== Python packages =="
@'
import cv2, numpy, PIL, fastapi, websockets, pydantic, psutil
import duckdb, httpx, mss, onnxruntime, vosk, soundfile, av, aiortc
import faster_whisper
from rapidocr_onnxruntime import RapidOCR
print("python ok")
print("cv2", cv2.__version__)
print("numpy", numpy.__version__)
print("fastapi", fastapi.__version__)
print("psutil", psutil.__version__)
print("duckdb", duckdb.__version__)
print("onnxruntime", onnxruntime.__version__)
print("vosk", vosk.__version__ if hasattr(vosk, "__version__") else "installed")
print("av", av.__version__)
print("aiortc", aiortc.__version__)
print("faster_whisper", faster_whisper.__version__ if hasattr(faster_whisper, "__version__") else "installed")
print("rapidocr", RapidOCR.__name__)
'@ | & $env:PHONE_CAPTURE_PYTHON -
