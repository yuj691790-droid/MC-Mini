$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $javaCompiler = Get-Command javac -ErrorAction SilentlyContinue
    $bridgeSource = Get-Item OptiFineBridge.java
    $bridgeClass = Get-Item java\OptiFineBridge.class -ErrorAction SilentlyContinue
    if ($javaCompiler) {
        New-Item -ItemType Directory -Force java | Out-Null
        & $javaCompiler.Source --release 8 -d java OptiFineBridge.java
        if ($LASTEXITCODE) { throw 'Java bridge build failed (use JDK 9+)' }
    } elseif (-not $bridgeClass -or $bridgeClass.LastWriteTime -lt $bridgeSource.LastWriteTime) {
        throw 'Compiling the OptiFine bridge needs javac (JDK 9+) on PATH; alternatively keep a prebuilt java/OptiFineBridge.class newer than OptiFineBridge.java.'
    } else {
        Write-Host 'javac not found: reusing the existing java\OptiFineBridge.class.' -ForegroundColor Yellow
    }
    python fetch_aria2.py
    if ($LASTEXITCODE) { throw 'aria2 preparation failed' }
    python -m venv .venv
    if ($LASTEXITCODE) { throw 'venv creation failed' }
    & .\.venv\Scripts\python.exe -m pip install pyinstaller==6.20.0
    if ($LASTEXITCODE) { throw 'PyInstaller installation failed' }
    & .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name MC-Mini --add-data 'sources.json;.' --add-data 'java;java' --add-data 'aria2;aria2' app.py
    if ($LASTEXITCODE) { throw 'Build failed' }
    Copy-Item -LiteralPath aria2 -Destination dist -Recurse -Force
} finally {
    Pop-Location
}
