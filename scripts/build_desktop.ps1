param(
 [switch]$SkipInstall,
 [string]$OutputDirectory = 'dist/desktop',
 [string]$VenvDirectory = 'dist/desktop-build/venv',
 [string]$BasePython = 'python'
)
$ErrorActionPreference='Stop'
$desktopRoot=Split-Path $PSScriptRoot -Parent
function Resolve-BuildPath([string]$Value) {
 $resolved=if([IO.Path]::IsPathRooted($Value)){[IO.Path]::GetFullPath($Value)}else{[IO.Path]::GetFullPath((Join-Path $desktopRoot $Value))}
 $allowed=[IO.Path]::GetFullPath((Join-Path $desktopRoot 'dist'))+[IO.Path]::DirectorySeparatorChar
 if(-not $resolved.StartsWith($allowed,[StringComparison]::OrdinalIgnoreCase)){throw '构建目录必须位于当前仓库dist/内。'}
 return $resolved
}
Push-Location -LiteralPath $desktopRoot
try {
 $artifactRoot=Resolve-BuildPath $OutputDirectory
 $venvRoot=Resolve-BuildPath $VenvDirectory
 $buildRoot=Resolve-BuildPath 'dist/desktop-build/isolated'
 New-Item -ItemType Directory -Force -Path $buildRoot | Out-Null
 $buildPython=Join-Path $venvRoot 'Scripts/python.exe'
 if(-not(Test-Path -LiteralPath $buildPython)){
  if($SkipInstall){throw '隔离环境不存在，请先不带-SkipInstall构建。'}
  & $BasePython -m venv $venvRoot
  if($LASTEXITCODE -ne 0){throw '创建干净venv失败。'}
 }
 $config=Get-Content -Raw -LiteralPath (Join-Path $venvRoot 'pyvenv.cfg')
 if($config -notmatch 'include-system-site-packages\s*=\s*false'){throw '构建venv不能读取全局site-packages。'}
 if(-not $SkipInstall){
  & $buildPython -I -m pip --isolated install --disable-pip-version-check '.[desktop]' 'pyinstaller>=6,<7'
  if($LASTEXITCODE -ne 0){throw '隔离环境依赖安装失败；未回退到全局环境。'}
 } else {
  # 跳过依赖更新时仍刷新本项目，防止复用旧页面/源码。
  & $buildPython -I -m pip --isolated install --disable-pip-version-check --no-deps --no-build-isolation .
  if($LASTEXITCODE -ne 0){throw '刷新本项目失败，不使用旧安装包。'}
 }
 & $buildPython -I -c "import importlib.util,sys; forbidden=['llvmlite','pyarrow','scipy','pandas','matplotlib']; found=[m for m in forbidden if importlib.util.find_spec(m)]; print('isolated_prefix='+sys.prefix); print('forbidden_packages='+str(found)); sys.exit(bool(found))"
 if($LASTEXITCODE -ne 0){throw '隔离环境含非必要重型库；请使用新的干净venv目录。'}
 & $buildPython -I -m pip --isolated freeze | Set-Content -LiteralPath (Join-Path $buildRoot 'requirements-freeze.txt') -Encoding utf8
 $rulesInput=(Resolve-Path -LiteralPath 'rules').Path
 $samplesInput=(Resolve-Path -LiteralPath 'samples').Path
 $assetsInput=(Resolve-Path -LiteralPath 'python/cst/assets').Path
 $pyinstallerArgs=@('--noconfirm','--windowed','--onedir','--name','GeomVerity','--paths',(Join-Path $desktopRoot 'python'),'--collect-submodules','cst','--collect-all','webview','--collect-all','shapely','--collect-all','pydantic','--add-data',($rulesInput+';cst/resources/rules'),'--add-data',($samplesInput+';samples'),'--add-data',($assetsInput+';cst/assets'),'--distpath',$artifactRoot,'--workpath',(Join-Path $buildRoot 'build'),'--specpath',$buildRoot)
 # 只收当前源码文件；避免collect-all把已删除的安装缓存资源重新带入。
 foreach($sourceFile in (Get-ChildItem -LiteralPath (Join-Path $desktopRoot 'python/cst') -File)) {
  if($sourceFile.Extension -in @('.py','.html','.yaml','.json')){$pyinstallerArgs+=@('--add-data',($sourceFile.FullName+';cst'))}
 }
 foreach($module in @('llvmlite','pyarrow','scipy','pandas','matplotlib')){$pyinstallerArgs+=@('--exclude-module',$module)}
 & $buildPython -I -m PyInstaller @pyinstallerArgs scripts/desktop_entry.py
 if($LASTEXITCODE -ne 0){throw '隔离环境打包失败，请检查构建日志。'}
 & $buildPython -I scripts/verify_desktop_resources.py --package (Join-Path $artifactRoot 'GeomVerity') --output (Join-Path $artifactRoot 'resource-verification.json')
 if($LASTEXITCODE -ne 0){throw '包内源码/UI资源一致性检查失败。'}
 Write-Host ('打开 '+(Join-Path $artifactRoot 'GeomVerity/GeomVerity.exe'))
 Write-Host '整个目录均需保留；仅含公开samples，桌面需WebView2，可加--browser。'
} finally {Pop-Location}
