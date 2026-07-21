$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = "$root\src"
Set-Location $root
& .\.venv\Scripts\python.exe -m zhixingzhixue_hub.pc.workbench_server @args
