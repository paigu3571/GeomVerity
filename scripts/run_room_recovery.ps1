# SPDX-License-Identifier: MPL-2.0
param([Parameter(Mandatory=$true)][string]$InputDirectory,[string]$OutputDirectory='dist/recovery')
$ErrorActionPreference='Stop'
$inputPath=(Resolve-Path -LiteralPath $InputDirectory).Path
$projectRoot=Split-Path -Parent $PSScriptRoot
$out=if ([System.IO.Path]::IsPathRooted($OutputDirectory)) { $OutputDirectory } else { Join-Path $projectRoot $OutputDirectory }
Push-Location -LiteralPath $projectRoot
try {
    $env:PYTHONUTF8='1'
    python -m cst recover $inputPath --all-unresolved --output $out --public-label sample
    if ($LASTEXITCODE -ne 0) { throw '房名和围合诊断失败，请核对三层输入及错误信息。' }
    python -m cst lights $out --output $out
    if ($LASTEXITCODE -ne 0) { throw '灯具候选生成失败，请检查规则与几何输入。' }
    python -m cst view $out --output "$out/semantic_view.html" --generated "$out/lighting_candidates.json"
    if ($LASTEXITCODE -ne 0) { throw '查看器生成失败。' }
    python -m cst report $out --output "$out/l4_report.html"
    if ($LASTEXITCODE -ne 0) { throw '规则报告生成失败。' }
    Write-Host "结果：$out"
} finally { Pop-Location }
