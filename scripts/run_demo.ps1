# SPDX-License-Identifier: MPL-2.0
param([switch]$SkipInstall)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Push-Location -LiteralPath $projectRoot
try {
    $env:PYTHONUTF8 = '1'
    if ($SkipInstall) { $runtimePython = 'python' }
    else {
        if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
            python -m venv .venv
            if ($LASTEXITCODE -ne 0) { throw '请先安装Python 3.11或更新版本，并勾选添加到PATH。' }
        }
        $runtimePython = Join-Path $projectRoot '.venv/Scripts/python.exe'
        & $runtimePython -m pip install -e ".[dxf]"
        if ($LASTEXITCODE -ne 0) { throw '依赖安装失败，请检查网络；不需要CAD或API密钥。' }
    }
    & $runtimePython -m cst.demo
    if ($LASTEXITCODE -ne 0) { throw '演示未完成，请保留错误信息并按运行指南排查。' }
} finally { Pop-Location }
