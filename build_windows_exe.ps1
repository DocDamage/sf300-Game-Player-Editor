param(
    [switch]$OneFile
)

$ErrorActionPreference = "Stop"

if (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonExe = "python"
    $PythonBaseArgs = @()
}
elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $PythonExe = "py"
    $PythonBaseArgs = @("-3")
}
else {
    throw "Python was not found on PATH."
}

function Invoke-Python {
    param([string[]]$Arguments)
    & $PythonExe @PythonBaseArgs @Arguments
}

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$distPath = Join-Path $ProjectRoot "dist"
$workPath = Join-Path $ProjectRoot "build\\pyinstaller"
$specPath = Join-Path $ProjectRoot "build\\spec"

New-Item -ItemType Directory -Force -Path $distPath, $workPath, $specPath | Out-Null

Invoke-Python -Arguments @("-m", "pip", "install", "pyinstaller")

$hasTkDnD = $false
try {
    Invoke-Python -Arguments @("-c", "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('tkinterdnd2') else 1)")
    $hasTkDnD = ($LASTEXITCODE -eq 0)
}
catch {
    $hasTkDnD = $false
}

$args = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--windowed",
    "--name", "SF3000 Game Manager",
    "--distpath", $distPath,
    "--workpath", $workPath,
    "--specpath", $specPath
)

if ($OneFile) {
    $args += "--onefile"
}

if ($hasTkDnD) {
    $args += @("--collect-all", "tkinterdnd2")
}

$args += (Join-Path $ProjectRoot "sf3000_manager.py")

Invoke-Python -Arguments $args

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE."
}

$outputPath = if ($OneFile) {
    Join-Path $distPath "SF3000 Game Manager.exe"
}
else {
    Join-Path $distPath "SF3000 Game Manager"
}

Write-Host ""
Write-Host "Build complete:" -ForegroundColor Green
Write-Host $outputPath
