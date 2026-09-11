param([string]$Python = "python")
$ErrorActionPreference = "Stop"
$taskApp = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$taskVsWhere = Join-Path "${env:ProgramFiles(x86)}" "Microsoft Visual Studio/Installer/vswhere.exe"
$taskVsRoot = if (Test-Path -LiteralPath $taskVsWhere) {
    & $taskVsWhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
}
if (-not $taskVsRoot) { throw "MSVC C compiler not found. Run the C test with your native C compiler first." }
$taskVcVars = Join-Path $taskVsRoot "VC/Auxiliary/Build/vcvars64.bat"
Push-Location -LiteralPath $taskApp
try {
    New-Item -ItemType Directory -Path "build/tests" -Force | Out-Null
    $taskCommand = 'call "' + $taskVcVars + '" >nul && cl /nologo /std:c11 /W4 /WX /utf-8 /D_CRT_SECURE_NO_WARNINGS /IInclude tests\test_firmware_core.c Source\tactile_protocol.c Source\tactile_stream.c /Fo:build\tests\ /Fe:build\tests\test_firmware_core.exe && build\tests\test_firmware_core.exe build\tests\protocol_vectors.bin'
    & cmd.exe /d /c $taskCommand
    if ($LASTEXITCODE -ne 0) { throw "Native C tests failed." }
    foreach ($taskProfile in 1..6) {
        $taskProfileCommand = 'call "' + $taskVcVars + '" >nul && cl /nologo /std:c11 /W4 /WX /utf-8 /D_CRT_SECURE_NO_WARNINGS /DTACTILE_PROFILE=' + $taskProfile + ' /IInclude tests\test_board_profile.c Source\tactile_protocol.c /Fo:build\tests\ /Fe:build\tests\test_board_profile_' + $taskProfile + '.exe && build\tests\test_board_profile_' + $taskProfile + '.exe build\tests\profile_' + $taskProfile + '.bin'
        & cmd.exe /d /c $taskProfileCommand
        if ($LASTEXITCODE -ne 0) { throw "Board profile $taskProfile failed." }
    }
    & $Python -m unittest discover -s tests -p "test_protocol_v2.py" -v
    if ($LASTEXITCODE -ne 0) { throw "Independent protocol tests failed." }
} finally {
    Pop-Location
}
