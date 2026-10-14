# SPDX-License-Identifier: MPL-2.0
param([string]$PluginPath,[string]$OutputDirectory='dist/cad-load')
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
if (-not $PluginPath) { $PluginPath=Join-Path $projectRoot 'cs/src/JZBP.BuildingSemantics/bin/x64/Release/net48/JZBP.BuildingSemantics.dll' }
$plugin=(Resolve-Path -LiteralPath $PluginPath).Path
$profile=Join-Path (Split-Path -Parent $plugin) 'profiles/generic.project-profile.v1.json'
if (-not (Test-Path -LiteralPath $profile)) { throw '插件目录缺少通用配置，请按docs/guides/cad-build.md重新构建。' }
$outDir=if ([System.IO.Path]::IsPathRooted($OutputDirectory)) { $OutputDirectory } else { Join-Path $projectRoot $OutputDirectory }
New-Item -ItemType Directory -Path $outDir -Force | Out-Null
$scriptFile=Join-Path $outDir 'load-plugin.scr'
$cadPlugin=$plugin.Replace('\','/')
[System.IO.File]::WriteAllText($scriptFile,"_.NETLOAD`r`n`"$cadPlugin`"`r`n",[System.Text.Encoding]::GetEncoding(936))
Write-Host "加载脚本：$scriptFile"
Write-Host '在新的CAD进程中输入SCRIPT并选择此文件；保存图纸后输入JZBPSCAN。'
