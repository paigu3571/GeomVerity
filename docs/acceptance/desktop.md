# 可选桌面工作台

安装`python -m pip install ".[desktop,dxf]"`，运行`python -m cst.desktop`。Windows需WebView2；`scripts/build_desktop.ps1`可在本地生成实验EXE。

选择配套JSON目录，点击分析；选择旧、新两版可生成变化Viewer；导出按钮生成证据包。输入是JSON，不直接选择DWG。整个GeomVerity构建文件夹需保留，不能仅复制EXE。

既有源码和打包探针已打开本机窗口并读取A图73个空间、17项finding；完整点选、缩放和导出仍待人工验收。核心分析不依赖桌面。

窗口打不开时检查运行时，输入报错时核对三层文件是否齐全。二进制留在dist，不进入源码仓库，依赖原许可见NOTICE及构建的licenses目录。
