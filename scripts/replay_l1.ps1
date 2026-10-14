# SPDX-License-Identifier: MPL-2.0
param([Parameter(Mandatory=$true)][string]$L1Json, [string]$Profile)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
if (-not $Profile) { $Profile=Join-Path $taskRoot 'cs/profiles/generic.project-profile.v1.json' }
dotnet run --project (Join-Path $taskRoot 'cs/tests/BuildingSemantics.ContractTests/BuildingSemantics.ContractTests.csproj') --configuration Release -- --layers-replay $L1Json $Profile
exit $LASTEXITCODE
