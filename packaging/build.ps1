param(
  [string]$Python = "python",
  [string]$Version = "0.1.3",
  [string]$Repository = "",
  [string]$ExpectedPublisher = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BuildRoot = Join-Path $ProjectRoot "build"
$BundleRoot = Join-Path $BuildRoot "bundle\AlviStudio"
$ArtifactRoot = Join-Path $ProjectRoot "artifacts"
$ToolsRoot = Join-Path $ProjectRoot ".build-tools"
$DownloadRoot = Join-Path $BuildRoot "downloads"
$env:PYINSTALLER_CONFIG_DIR = Join-Path $BuildRoot "pyinstaller-cache"

function Assert-NativeSuccess([string]$Step) {
  if ($LASTEXITCODE -ne 0) { throw "$Step failed with exit code $LASTEXITCODE" }
}

if (Test-Path -LiteralPath $BundleRoot) {
  $ResolvedBundle = (Resolve-Path -LiteralPath $BundleRoot).Path
  if (-not $ResolvedBundle.StartsWith($BuildRoot, [StringComparison]::OrdinalIgnoreCase)) { throw "Unsafe bundle path: $ResolvedBundle" }
  Remove-Item -Recurse -Force -LiteralPath $ResolvedBundle
}
New-Item -ItemType Directory -Force -Path $BuildRoot, $BundleRoot, $ArtifactRoot, $ToolsRoot, $DownloadRoot | Out-Null

& $Python -m pip install --disable-pip-version-check --target $ToolsRoot "pyinstaller>=6.12,<7"
Assert-NativeSuccess "Installing PyInstaller"
$env:PYTHONPATH = $ToolsRoot
$AssetPath = Join-Path $ProjectRoot "dubstudio\assets"
& $Python -m PyInstaller `
  --noconfirm `
  --clean `
  --noconsole `
  --onedir `
  --name AlviStudio `
  --distpath (Join-Path $BuildRoot "pyinstaller") `
  --workpath (Join-Path $BuildRoot "pyinstaller-work") `
  --specpath $BuildRoot `
  --add-data "$AssetPath;dubstudio/assets" `
  (Join-Path $ProjectRoot "launcher.py")
Assert-NativeSuccess "Building the desktop executable"

Copy-Item -Recurse -Force (Join-Path $BuildRoot "pyinstaller\AlviStudio\*") $BundleRoot
Copy-Item -Force (Join-Path $ProjectRoot "LICENSE") $BundleRoot
Copy-Item -Force (Join-Path $ProjectRoot "README.md") $BundleRoot
Copy-Item -Force (Join-Path $ProjectRoot "THIRD_PARTY_NOTICES.md") $BundleRoot
New-Item -ItemType Directory -Force -Path (Join-Path $BundleRoot "app") | Out-Null
Copy-Item -Force (Join-Path $ProjectRoot "requirements-engine.txt") (Join-Path $BundleRoot "app\requirements-engine.txt")
$UpdateConfig = @{ repository = $Repository; expected_publisher = $ExpectedPublisher } | ConvertTo-Json
Set-Content -LiteralPath (Join-Path $BundleRoot "app\update-config.json") -Value $UpdateConfig -Encoding UTF8

# Private embeddable Python lives under the selected installation folder.
$RuntimeRoot = Join-Path $BundleRoot "runtime\python"
New-Item -ItemType Directory -Force -Path $RuntimeRoot | Out-Null
$PythonZip = Join-Path $DownloadRoot "python-3.12.8-embed-amd64.zip"
if (-not (Test-Path -LiteralPath $PythonZip)) {
  Invoke-WebRequest "https://www.python.org/ftp/python/3.12.8/python-3.12.8-embed-amd64.zip" -OutFile $PythonZip
}
Expand-Archive -LiteralPath $PythonZip -DestinationPath $RuntimeRoot -Force
$PthFile = Join-Path $RuntimeRoot "python312._pth"
$Pth = Get-Content -LiteralPath $PthFile
$Pth = $Pth -replace "#import site", "import site"
$Pth += "Lib\site-packages"
Set-Content -LiteralPath $PthFile -Value $Pth -Encoding ASCII
New-Item -ItemType Directory -Force -Path (Join-Path $RuntimeRoot "Lib\site-packages") | Out-Null

$GetPip = Join-Path $DownloadRoot "get-pip.py"
if (-not (Test-Path -LiteralPath $GetPip)) {
  Invoke-WebRequest "https://bootstrap.pypa.io/get-pip.py" -OutFile $GetPip
}
& (Join-Path $RuntimeRoot "python.exe") $GetPip --no-warn-script-location
Assert-NativeSuccess "Bootstrapping private pip"
& (Join-Path $RuntimeRoot "python.exe") -m pip install --disable-pip-version-check "huggingface-hub>=0.28"
Assert-NativeSuccess "Installing the private model downloader"
Copy-Item -Recurse -Force (Join-Path $ProjectRoot "dubstudio") (Join-Path $RuntimeRoot "Lib\site-packages\dubstudio")
Copy-Item -Recurse -Force (Join-Path $ProjectRoot "dubstudio_engine") (Join-Path $RuntimeRoot "Lib\site-packages\dubstudio_engine")

# Bundle FFmpeg; it never needs to be installed system-wide.
$FfmpegZip = Join-Path $DownloadRoot "ffmpeg-release-essentials.zip"
if (-not (Test-Path -LiteralPath $FfmpegZip)) {
  Invoke-WebRequest "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" -OutFile $FfmpegZip
}
$FfmpegExtract = Join-Path $BuildRoot "ffmpeg-extracted"
if (Test-Path -LiteralPath $FfmpegExtract) { Remove-Item -Recurse -Force -LiteralPath $FfmpegExtract }
Expand-Archive -LiteralPath $FfmpegZip -DestinationPath $FfmpegExtract
$FfmpegBin = Get-ChildItem -LiteralPath $FfmpegExtract -Directory | Select-Object -First 1 | ForEach-Object { Join-Path $_.FullName "bin" }
New-Item -ItemType Directory -Force -Path (Join-Path $BundleRoot "tools\ffmpeg\bin") | Out-Null
Copy-Item -Force (Join-Path $FfmpegBin "ffmpeg.exe"), (Join-Path $FfmpegBin "ffprobe.exe") (Join-Path $BundleRoot "tools\ffmpeg\bin")

$Makensis = $null
$MakensisCommand = Get-Command makensis.exe -ErrorAction SilentlyContinue
if ($MakensisCommand) {
  $Makensis = $MakensisCommand.Source
}
if (-not $Makensis) {
  $MakensisCandidates = @(
    (Join-Path $env:ProgramFiles "NSIS\makensis.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "NSIS\makensis.exe")
  )
  $Makensis = $MakensisCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
}
if (-not $Makensis) { throw "NSIS makensis.exe was not found" }
& $Makensis "/DBUNDLE_DIR=$BundleRoot" "/DOUTPUT_DIR=$ArtifactRoot" "/DAPP_VERSION=$Version" (Join-Path $PSScriptRoot "DubStudio.nsi")
Assert-NativeSuccess "Building the Windows installer"
$Installer = Join-Path $ArtifactRoot "Alvi-Studio-Setup.exe"
$Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Installer).Hash.ToLowerInvariant()
Set-Content -LiteralPath "$Installer.sha256" -Value "$Hash  Alvi-Studio-Setup.exe" -Encoding ASCII
Write-Host "Built $Installer"
