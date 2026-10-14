param()
$ErrorActionPreference='Stop'
$desktopRoot=Split-Path $PSScriptRoot -Parent
Push-Location -LiteralPath $desktopRoot
try {
 New-Item -ItemType Directory -Force '.local/desktop-experiment' | Out-Null
 $rulesInput=(Resolve-Path -LiteralPath 'rules').Path
 python -m pip install '.[desktop,dxf]' pyinstaller
 if ($LASTEXITCODE -ne 0) { throw '桌面依赖未安装完成，请检查网络。' }
 python -m PyInstaller --noconfirm --windowed --onedir --name GeomVerity --paths python --collect-all cst --collect-all webview --collect-all shapely --collect-all pydantic --add-data ($rulesInput+';cst/resources/rules') --distpath dist/desktop --workpath .local/desktop-experiment/build --specpath .local/desktop-experiment scripts/desktop_entry.py
 if ($LASTEXITCODE -ne 0) { throw '桌面打包未完成，请保存报错。' }
 Write-Host '打开 dist/desktop/GeomVerity/GeomVerity.exe；首次运行需系统WebView2。'
} finally { Pop-Location }
