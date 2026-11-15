<#
  Logistik Map – Setup bauen

  Aufruf aus dem Projektordner:
    powershell -ExecutionPolicy Bypass -File installer\build.ps1 [-ExpectedVersion v0.1.0] [-SkipTests]

  Ergebnis:
    installer\build\output\LogistikMap-Setup-<Version>.exe (+ .sha256)

  Voraussetzungen: Python 3.12+, Inno Setup 6 (ISCC.exe), gh (für den WinSW-Download).
  Wird lokal und in GitHub Actions (.github/workflows/release.yml) verwendet.
#>
param(
    [string]$ExpectedVersion = "",
    [switch]$SkipTests,
    [string]$Iscc = ""
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$WinSwVersion = "v2.12.0"

$root     = Split-Path -Parent $PSScriptRoot
$buildDir = Join-Path $PSScriptRoot "build"
$stage    = Join-Path $buildDir "stage"
$cache    = Join-Path $buildDir "cache"
$output   = Join-Path $buildDir "output"

function Step([string]$text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }
function Check([string]$what) { if ($LASTEXITCODE -ne 0) { throw "$what fehlgeschlagen (Code $LASTEXITCODE)" } }

Set-Location $root

# -- Version -------------------------------------------------------------------
$src = Get-Content "logistikmap\__init__.py" -Raw
if ($src -notmatch '__version__\s*=\s*"(\d+)\.(\d+)\.(\d+)"') { throw "__version__ in logistikmap\__init__.py nicht gefunden" }
$version = "$($Matches[1]).$($Matches[2]).$($Matches[3])"
$tuple = "($($Matches[1]), $($Matches[2]), $($Matches[3]), 0)"
if ($ExpectedVersion -and ($ExpectedVersion -replace '^v', '') -ne $version) {
    throw "Tag-Version $ExpectedVersion passt nicht zu __version__ ($version)"
}
Write-Host "Logistik Map $version" -ForegroundColor White

$python = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }

# -- Tests ---------------------------------------------------------------------
if (-not $SkipTests) {
    Step "Tests"
    & $python -m pytest -q
    Check "Tests"
}

# -- PyInstaller ---------------------------------------------------------------
Step "Programm bündeln (PyInstaller)"
Remove-Item -Recurse -Force $stage -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $buildDir, $cache, $output, "$stage\service" | Out-Null

@"
VSVersionInfo(
  ffi=FixedFileInfo(filevers=$tuple, prodvers=$tuple, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040704B0', [
      StringStruct('CompanyName', 'Logistik Map Contributors'),
      StringStruct('FileDescription', 'Logistik Map - Warenfluesse und Transportwege'),
      StringStruct('FileVersion', '$version'),
      StringStruct('InternalName', 'LogistikMap'),
      StringStruct('LegalCopyright', 'AGPL-3.0-or-later'),
      StringStruct('OriginalFilename', 'LogistikMap.exe'),
      StringStruct('ProductName', 'Logistik Map'),
      StringStruct('ProductVersion', '$version')])]),
    VarFileInfo([VarStruct('Translation', [1031, 1200])])
  ]
)
"@ | Set-Content "$buildDir\version_info.txt" -Encoding utf8

& $python -m PyInstaller --noconfirm --clean --onedir --console --name LogistikMap `
    --icon "$PSScriptRoot\app.ico" --version-file "$buildDir\version_info.txt" `
    --add-data "$root\logistikmap\static;static" `
    --collect-submodules uvicorn `
    --exclude-module tkinter --exclude-module pytest --exclude-module PIL `
    --distpath "$stage" --workpath "$buildDir\pyinstaller" --specpath "$buildDir" `
    "$PSScriptRoot\start.py"
Check "PyInstaller"
Move-Item "$stage\LogistikMap" "$stage\app"

Step "Selbsttest des Pakets"
& "$stage\app\LogistikMap.exe" --selftest
Check "Selbsttest"

# Sicherheitsnetz: keine Daten im Paket
$verboten = Get-ChildItem -Recurse "$stage\app" -Include *.pdf, *.db, config.json -ErrorAction SilentlyContinue
if ($verboten) { throw "Daten im Programmpaket gefunden: $($verboten.FullName -join ', ')" }

# -- WinSW (Windows-Dienst) -----------------------------------------------------
Step "WinSW $WinSwVersion"
$winsw = Join-Path $cache "WinSW-x64-$WinSwVersion.exe"
if (-not (Test-Path $winsw)) {
    gh release download $WinSwVersion --repo winsw/winsw --pattern "WinSW-x64.exe" --output $winsw --clobber
    Check "WinSW-Download"
}
Copy-Item $winsw "$stage\service\LogistikMap-Dienst.exe"
Copy-Item "$PSScriptRoot\LogistikMap-Dienst.xml" "$stage\service\"
Copy-Item "$root\LICENSE", "$root\README.md" $stage

# -- Inno Setup ----------------------------------------------------------------
Step "Setup bauen (Inno Setup)"
if (-not $Iscc) {
    $Iscc = @(
        "$PSScriptRoot\build\tools\innosetup\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $Iscc) { throw "Inno Setup 6 nicht gefunden (winget install JRSoftware.InnoSetup)" }
& $Iscc /Q "/DAppVersion=$version" "/DStageDir=$stage" "/DOutputDir=$output" "$PSScriptRoot\LogistikMap.iss"
Check "Inno Setup"

$setup = Join-Path $output "LogistikMap-Setup-$version.exe"
$hash = (Get-FileHash $setup -Algorithm SHA256).Hash.ToLower()
"$hash  LogistikMap-Setup-$version.exe" | Set-Content "$setup.sha256" -Encoding ascii -NoNewline
Get-Item $setup | ForEach-Object { Write-Host ("{0}  {1:N1} MB" -f $_.Name, ($_.Length / 1MB)) }
Write-Host "SHA256: $hash"
