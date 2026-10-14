# SPDX-License-Identifier: MPL-2.0
param([switch]$CoreOnly)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Push-Location $taskRoot
try {
    dotnet run --project 'cs/tests/BuildingSemantics.ContractTests/BuildingSemantics.ContractTests.csproj' --configuration Release
    if ($LASTEXITCODE -ne 0) { throw '核心测试未通过，请保留终端最后的FAIL信息。' }
    if (-not $CoreOnly) {
        dotnet build 'cs/src/JZBP.BuildingSemantics/JZBP.BuildingSemantics.csproj' --configuration Release --property:Platform=x64
        if ($LASTEXITCODE -ne 0) { throw '插件构建失败。请检查.NET 4.8开发包及ACAD2016_DIR；核心测试结果与插件构建结果分开记录。' }
    }
    python scripts/scan_secrets.py
    if ($LASTEXITCODE -ne 0) { throw '敏感扫描未通过，请按文件和行号检查，不要把敏感原文贴入公开Issue。' }
    Write-Host '核心测试与构建检查完成；CAD加载和扫描需在宿主中验证。'
} finally { Pop-Location }
