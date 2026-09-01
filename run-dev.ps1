$ErrorActionPreference = "Stop"
$BundledPython = "C:\Users\Omar\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$Python = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } elseif (Test-Path -LiteralPath $BundledPython) { $BundledPython } else { throw "Python 3.11+ is required for development." }
& $Python -m dubstudio

