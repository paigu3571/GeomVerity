// SPDX-License-Identifier: MPL-2.0
// Copyright (c) 2026 张田; 著作权人、原作者及维护者：张田；其他贡献者和第三方保留各自权利。
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.Colors;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.GraphicsInterface;
using Autodesk.AutoCAD.Runtime;
using JZBP.BuildingSemantics.Core;
using JZBP.BuildingSemantics.Infrastructure.Cad;
using Newtonsoft.Json;

using AcadApplication = Autodesk.AutoCAD.ApplicationServices.Application;
using AcadException = Autodesk.AutoCAD.Runtime.Exception;
using Drawing = System.Drawing;
using WinForms = System.Windows.Forms;

[assembly: CommandClass(typeof(JZBP.BuildingSemantics.Commands.BuildingSemanticsCommands))]

namespace JZBP.BuildingSemantics.Commands
{
    /// <summary>
    /// 建筑平面统一语义只读入口。
    /// JZBPSCAN 仅以 ForRead 事务扫描并输出 JSON/HTML；JZBPVIEW 仅创建瞬态 Drawable。
    /// </summary>
    public sealed class BuildingSemanticsCommands
    {
#if T20_GEOMETRY_DIAGNOSTIC_ASSEMBLY
        [CommandMethod("JZBPSCAN_DIAG", CommandFlags.Modal)]
#else
        [CommandMethod("JZBPSCAN", CommandFlags.Modal)]
#endif
        public void ScanCurrentDrawing()
        {
            Document document = AcadApplication.DocumentManager.MdiActiveDocument;
            if (document == null)
                return;

            try
            {
                var scanClock = Stopwatch.StartNew();
                string drawingPath = ResolveDrawingPath(document);
                if (!string.Equals(Path.GetExtension(drawingPath), ".dwg", StringComparison.OrdinalIgnoreCase))
                    throw new InvalidOperationException("只允许以 .dwg 为输入，.bak 不作为识图输入。");

                var file = new FileInfo(drawingPath);
                string sourceHashBefore = BuildingSemanticStableId.Sha256File(drawingPath);
                LoadedProjectProfile loadedProfile = ResolveProfile(drawingPath, sourceHashBefore);
                DrawingProfileRule? drawingRule = ProjectProfileValidator.FindDrawing(loadedProfile.Profile, sourceHashBefore);
                if (drawingRule == null)
                    throw new InvalidDataException("当前 DWG 的 SHA-256 不在项目配置白名单中。");

                int dbmodBefore = ReadDbmod();
                AnalysisRequest request = CreateAnalysisRequest(
                    loadedProfile,
                    drawingRule,
                    drawingPath,
                    sourceHashBefore,
                    file);

                BuildingRecognitionBundle layers;
                // T20 在打开图纸时可能自行置位活动图 DBMOD。正式识图始终从同一路径重新
                // 只读侧载磁盘数据库，避免把未保存的活动图状态冒充磁盘 SHA-256 对应内容。
                using (var scanDatabase = new Database(false, true))
                {
                    scanDatabase.ReadDwgFile(
                        drawingPath,
                        FileOpenMode.OpenForReadAndAllShare,
                        false,
                        string.Empty);
                    var provider = new AutoCadBuildingFactProvider(scanDatabase);
                    var service = new BuildingSemanticService(provider);
                    layers = service.AnalyzeLayers(request);
                }

                int dbmodAfter = ReadDbmod();
                string sourceHashAfter = BuildingSemanticStableId.Sha256File(drawingPath);
                BuildingSemanticSnapshot snapshot = layers.SemanticSnapshot;
                snapshot.ProducerBinarySha256 = ResolveProducerBinaryHash();
                ScanIntegrityPolicy.Apply(
                    snapshot,
                    sourceHashBefore,
                    sourceHashAfter,
                    dbmodBefore,
                    dbmodAfter,
                    ScanInputMode.DiskSideDatabase,
                    true);
                RecognitionLayerProvenance.Apply(layers, snapshot.ProducerBinarySha256);
                RecognitionLayerIntegrityPolicy.Apply(
                    layers,
                    sourceHashBefore,
                    sourceHashAfter,
                    dbmodBefore,
                    dbmodAfter,
                    ScanInputMode.DiskSideDatabase,
                    true);

                string outputDirectory = ResolveOutputDirectory(
                    loadedProfile.Profile,
                    drawingPath,
                    drawingRule.DrawingId,
                    request.RuntimeProjectId);
                string primitiveJsonPath = Path.Combine(outputDirectory, "cad-primitives.v1.json");
                string geometryJsonPath = Path.Combine(outputDirectory, "building-geometry.v1.json");
                string rawSemanticJsonPath = Path.Combine(outputDirectory, "building-semantics.raw.v1.json");
                string overrideJsonPath = Path.Combine(outputDirectory, "building-semantics.override.v1.json");
                string jsonPath = Path.Combine(outputDirectory, "building-semantics.v1.json");
                string htmlPath = Path.Combine(outputDirectory, "building-semantics.v1.review.html");
                BuildingSemanticJson.WriteUtf8(primitiveJsonPath, BuildingSemanticJson.SerializePrimitiveSnapshot(layers.PrimitiveSnapshot));
                BuildingSemanticJson.WriteUtf8(geometryJsonPath, BuildingSemanticJson.SerializeGeometrySnapshot(layers.GeometrySnapshot));
                snapshot.Metrics.AnalysisElapsedMilliseconds = scanClock.ElapsedMilliseconds;
                BuildingSemanticJson.WriteUtf8(rawSemanticJsonPath, BuildingSemanticJson.SerializeSnapshot(snapshot));

                SemanticOverrideApplicationResult? overrideResult = null;
                string overrideFailure = string.Empty;
                if (File.Exists(overrideJsonPath))
                {
                    try
                    {
                        BuildingSemanticOverrideDocument overrideDocument = BuildingSemanticJson.DeserializeOverride(
                            File.ReadAllText(overrideJsonPath));
                        overrideResult = BuildingSemanticOverrideResolver.Apply(snapshot, overrideDocument);
                        snapshot = overrideResult.Snapshot;
                    }
                    catch (System.Exception overrideException)
                    {
                        overrideFailure = overrideException.Message;
                        snapshot = BuildingSemanticOverrideResolver.FailClosed(snapshot, overrideFailure);
                    }
                }

                layers.SemanticSnapshot = snapshot;
                BuildingSemanticJson.WriteUtf8(jsonPath, BuildingSemanticJson.SerializeSnapshot(snapshot));
                BuildingSemanticJson.WriteUtf8(htmlPath, BuildingSemanticHtmlReport.Build(layers, loadedProfile.Profile));

                BuildingSemanticRuntimeCache.Store(document.Database, snapshot, loadedProfile.Profile, jsonPath);
                WriteSummary(
                    document.Editor,
                    layers,
                    loadedProfile.Profile.ProjectId,
                    primitiveJsonPath,
                    geometryJsonPath,
                    jsonPath,
                    htmlPath);
                document.Editor.WriteMessage("\n[JZBP] 原始语义JSON: " + rawSemanticJsonPath);
                if (overrideResult != null && overrideResult.Applied)
                {
                    document.Editor.WriteMessage("\n[JZBP] L3修正覆盖=" + overrideResult.OverrideId
                                                 + "，已应用=" + overrideResult.AppliedChangeCount.ToString(CultureInfo.InvariantCulture)
                                                 + "；规范语义JSON保持 Review。\n");
                }
                else if (!string.IsNullOrWhiteSpace(overrideFailure))
                {
                    document.Editor.WriteMessage("\n[JZBP] L3修正覆盖拒绝=" + overrideFailure
                                                 + "；规范语义JSON已 Failed 闭合，原始 L3 仍保留。\n");
                }
                if (ProjectProfileValidator.IsGenericReviewDrawing(drawingRule))
                {
                    document.Editor.WriteMessage(
                        "\n[JZBP] 通用离线模式：当前图纸无需预登记哈希；SHA-256 仅用于结果追溯，L3 全部保持 Review。\n");
                }
            }
            catch (AcadException ex)
            {
                document.Editor.WriteMessage("\n[JZBP] AutoCAD 只读扫描失败 [" + ex.ErrorStatus + "]: " + ex.Message + "\n");
            }
            catch (System.Exception ex)
            {
                document.Editor.WriteMessage("\n[JZBP] 扫描失败: " + ex.Message + "\n");
            }
        }

#if T20_GEOMETRY_DIAGNOSTIC_ASSEMBLY
        [CommandMethod("JZBPREGION_DIAG", CommandFlags.Modal)]
#else
        [CommandMethod("JZBPREGION", CommandFlags.Modal)]
#endif
        public void CaptureObservationRegion()
        {
            Document document = AcadApplication.DocumentManager.MdiActiveDocument;
            if (document == null)
                return;

            Editor editor = document.Editor;
            try
            {
                string drawingPath = ResolveDrawingPath(document);
                string sourceHashBefore = BuildingSemanticStableId.Sha256File(drawingPath);
                LoadedProjectProfile loadedProfile = ResolveProfile(drawingPath, sourceHashBefore);
                DrawingProfileRule? drawingRule = ProjectProfileValidator.FindDrawing(loadedProfile.Profile, sourceHashBefore);
                if (drawingRule == null)
                    throw new InvalidDataException("当前 DWG 不在项目配置白名单中。");

                List<ObservationRegion> candidates = (loadedProfile.Profile.ObservationRegions ?? new List<ObservationRegion>())
                    .Where(region => string.Equals(region.DrawingHash, sourceHashBefore, StringComparison.OrdinalIgnoreCase))
                    .OrderBy(region => region.Code, StringComparer.Ordinal)
                    .ToList();
                if (candidates.Count == 0)
                    throw new InvalidDataException("当前 DWG 没有待人工圈定的观察区域。");

                string labels = string.Join(", ", candidates.Select(region => region.Code + "=" + region.Name));
                var keywordOptions = new PromptKeywordOptions("\n请选择观察区 [" + labels + "]: ")
                {
                    AllowNone = false
                };
                foreach (ObservationRegion region in candidates)
                    keywordOptions.Keywords.Add(region.Code);
                PromptResult keywordResult = editor.GetKeywords(keywordOptions);
                if (keywordResult.Status != PromptStatus.OK)
                    return;

                ObservationRegion selectedRegion = candidates.Single(region =>
                    string.Equals(region.Code, keywordResult.StringResult, StringComparison.OrdinalIgnoreCase));
                int dbmodBefore = ReadDbmod();

                PromptPointResult firstResult = editor.GetPoint(
                    new PromptPointOptions("\n请框选 " + selectedRegion.Code + "（" + selectedRegion.Name + "）的第一角点: "));
                if (firstResult.Status != PromptStatus.OK)
                    return;
                PromptPointResult secondResult = editor.GetCorner(
                    new PromptCornerOptions("\n请选择对角点: ", firstResult.Value));
                if (secondResult.Status != PromptStatus.OK)
                    return;

                Matrix3d ucsToWcs = editor.CurrentUserCoordinateSystem;
                double z = firstResult.Value.Z;
                var ucsCorners = new[]
                {
                    new Point3d(firstResult.Value.X, firstResult.Value.Y, z),
                    new Point3d(secondResult.Value.X, firstResult.Value.Y, z),
                    new Point3d(secondResult.Value.X, secondResult.Value.Y, z),
                    new Point3d(firstResult.Value.X, secondResult.Value.Y, z)
                };
                List<Point3d> wcsCorners = ucsCorners.Select(point => point.TransformBy(ucsToWcs)).ToList();
                if (wcsCorners[0].DistanceTo(wcsCorners[1]) < 1000.0
                    || wcsCorners[1].DistanceTo(wcsCorners[2]) < 1000.0)
                {
                    throw new InvalidDataException("观察区每条边至少应为 1000 mm，请重新框选。");
                }

                var preview = new Autodesk.AutoCAD.DatabaseServices.Polyline(4)
                {
                    Closed = true,
                    Color = Color.FromColorIndex(ColorMethod.ByAci, 6),
                    LineWeight = LineWeight.LineWeight070,
                    ConstantWidth = 50.0,
                    Elevation = wcsCorners[0].Z
                };
                for (int index = 0; index < wcsCorners.Count; index++)
                    preview.AddVertexAt(index, new Point2d(wcsCorners[index].X, wcsCorners[index].Y), 0, 0, 0);

                TransientManager manager = TransientManager.CurrentTransientManager;
                var viewports = new IntegerCollection();
                bool previewAdded = manager.AddTransient(
                    preview,
                    TransientDrawingMode.DirectShortTerm,
                    129,
                    viewports);
                bool confirmed = false;
                try
                {
                    editor.Regen();
                    var confirmOptions = new PromptKeywordOptions(
                        "\n紫色框为 " + selectedRegion.Code + "（" + selectedRegion.Name + "），确认保存选择回执? [Yes/No] <Yes>: ")
                    {
                        AllowNone = true
                    };
                    confirmOptions.Keywords.Add("Yes");
                    confirmOptions.Keywords.Add("No");
                    PromptResult confirmResult = editor.GetKeywords(confirmOptions);
                    confirmed = confirmResult.Status == PromptStatus.None
                                || (confirmResult.Status == PromptStatus.OK
                                    && string.Equals(confirmResult.StringResult, "Yes", StringComparison.OrdinalIgnoreCase));
                }
                finally
                {
                    if (previewAdded)
                    {
                        try { manager.EraseTransient(preview, viewports); }
                        catch { }
                    }
                    preview.Dispose();
                    editor.Regen();
                }

                if (!confirmed)
                {
                    editor.WriteMessage("\n[JZBP] 已取消 " + selectedRegion.Code + "，未写回执，DWG 未修改。\n");
                    return;
                }

                int dbmodAfter = ReadDbmod();
                string sourceHashAfter = BuildingSemanticStableId.Sha256File(drawingPath);
                if (dbmodBefore < 0
                    || dbmodAfter < 0
                    || dbmodBefore != dbmodAfter
                    || !string.Equals(sourceHashBefore, sourceHashAfter, StringComparison.OrdinalIgnoreCase))
                {
                    throw new InvalidDataException(
                        "圈区期间活动图 DBMOD 或磁盘 DWG 字节发生变化，禁止写入选择回执。");
                }

                string runtimeProjectId = ProjectProfileValidator.ResolveRuntimeProjectId(
                    loadedProfile.Profile,
                    drawingRule,
                    sourceHashBefore);
                string outputDirectory = ResolveOutputDirectory(
                    loadedProfile.Profile,
                    drawingPath,
                    drawingRule.DrawingId,
                    runtimeProjectId);
                string receiptPath = Path.Combine(outputDirectory, "observation-region-selections.v1.json");
                ObservationRegionSelectionReceiptSet receipt = LoadSelectionReceipt(receiptPath);
                receipt.ProjectId = runtimeProjectId;
                receipt.ProfileSha256 = loadedProfile.Sha256;
                receipt.DrawingId = drawingRule.DrawingId ?? string.Empty;
                receipt.DrawingSha256 = sourceHashBefore;
                receipt.Selections.RemoveAll(item =>
                    string.Equals(item.RegionCode, selectedRegion.Code, StringComparison.OrdinalIgnoreCase));
                receipt.Selections.Add(new ObservationRegionSelectionReceipt
                {
                    RegionCode = selectedRegion.Code ?? string.Empty,
                    RegionName = selectedRegion.Name ?? string.Empty,
                    Role = selectedRegion.Role.ToString(),
                    ConfirmedBy = "user_in_cad",
                    ConfirmedAtUtc = DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture),
                    PolygonWcsMillimeters = wcsCorners
                        .Select(point => new SemanticPoint(point.X, point.Y, point.Z))
                        .ToList()
                });
                receipt.Selections = receipt.Selections
                    .OrderBy(item => item.RegionCode, StringComparer.Ordinal)
                    .ToList();
                BuildingSemanticJson.WriteUtf8(
                    receiptPath,
                    JsonConvert.SerializeObject(receipt, Formatting.Indented));

                editor.WriteMessage("\n[JZBP] 已记录 " + selectedRegion.Code
                                    + " 的用户确认坐标；DBMOD " + dbmodBefore + "=>" + dbmodAfter
                                    + "，DWG 字节不变=True。\n[JZBP] 回执: " + receiptPath + "\n");
            }
            catch (AcadException ex)
            {
                editor.WriteMessage("\n[JZBP] 圈区失败 [" + ex.ErrorStatus + "]: " + ex.Message + "\n");
            }
            catch (System.Exception ex)
            {
                editor.WriteMessage("\n[JZBP] 圈区失败: " + ex.Message + "\n");
            }
        }

        private static ObservationRegionSelectionReceiptSet LoadSelectionReceipt(string path)
        {
            if (!File.Exists(path))
                return new ObservationRegionSelectionReceiptSet();

            ObservationRegionSelectionReceiptSet? receipt = JsonConvert.DeserializeObject<ObservationRegionSelectionReceiptSet>(
                File.ReadAllText(path));
            if (receipt == null
                || !string.Equals(
                    receipt.SchemaVersion,
                    ObservationRegionSelectionReceiptSet.CurrentSchemaVersion,
                    StringComparison.Ordinal))
            {
                throw new InvalidDataException("既有观察区选择回执 schema 无效，拒绝覆盖。");
            }
            receipt.Selections = receipt.Selections ?? new List<ObservationRegionSelectionReceipt>();
            return receipt;
        }
#if !T20_GEOMETRY_DIAGNOSTIC_ASSEMBLY
        [CommandMethod("JZBPVIEW", CommandFlags.Modal)]
#endif
        public void ToggleSemanticView()
        {
            Document document = AcadApplication.DocumentManager.MdiActiveDocument;
            if (document == null)
                return;

            try
            {
                Editor editor = document.Editor;
                editor.WriteMessage(
                    "\n[JZBP] 请在弹出窗口选择房间、电气房间、井道、特殊区域、墙、柱、门窗洞口、楼梯、全部或清除。\n");
                string viewMode = SelectViewMode(editor) ?? string.Empty;
                if (string.IsNullOrWhiteSpace(viewMode))
                    return;
                if (string.Equals(viewMode, "Hide", StringComparison.OrdinalIgnoreCase))
                {
                    int removed = BuildingSemanticTransientView.Clear();
                    editor.Regen();
                    editor.WriteMessage("\n[JZBP] 已清除 " + removed.ToString(CultureInfo.InvariantCulture)
                                        + " 个瞬态高亮；DWG 未创建实体。\n");
                    return;
                }

                BuildingSemanticSnapshot snapshot = LoadSnapshotForCurrentDrawing(document);
                string semanticPayloadHash = ValidateActiveDrawingForView(document, snapshot);
                if (snapshot.Status == AnalysisRunStatus.Failed)
                    editor.WriteMessage("\n[JZBP] 注意：快照状态为 Failed，仅显示其中可复核对象，不代表识别成功。\n");
                double roomPatternScale;
                using (ViewTableRecord view = editor.GetCurrentView())
                    roomPatternScale = Math.Max(100.0, Math.Min(500.0, view.Height / 250.0));
                int objectCount;
                int drawableCount = BuildingSemanticTransientView.Show(
                    document.Database,
                    snapshot,
                    viewMode,
                    roomPatternScale,
                    out objectCount);
                editor.Regen();
                editor.WriteMessage("\n[JZBP] 筛选=" + viewMode
                                    + "，对象=" + objectCount.ToString(CultureInfo.InvariantCulture)
                                    + "，瞬态图形=" + drawableCount.ToString(CultureInfo.InvariantCulture)
                                    + "，房间/井道/特殊区域=虚线边界+斜线填充，显示尺度="
                                    + roomPatternScale.ToString("0", CultureInfo.InvariantCulture) + "mm"
                                    + "；颜色: 普通房间=青, 电气房间=橙黄, 井道=天蓝, 特殊区域=蓝, 普通/未知墙=黄, 剪力墙=红色虚线+斜线, 柱=紫, 洞口=红, 门=橙, 窗=蓝, 楼梯=绿。"
                                    + "\n[JZBP] 显示载荷=" + semanticPayloadHash
                                    + "；再次执行 JZBPVIEW 可切换筛选或选择 Hide 清除，DWG 未创建实体。\n");
            }
            catch (AcadException ex)
            {
                document.Editor.WriteMessage("\n[JZBP] AutoCAD 瞬态显示失败 [" + ex.ErrorStatus + "]: " + ex.Message + "\n");
            }
            catch (System.Exception ex)
            {
                document.Editor.WriteMessage("\n[JZBP] 瞬态显示失败: " + ex.Message + "\n");
            }
        }

        private static string? SelectViewMode(Editor editor)
        {
            try
            {
                string? selected = null;
                using (var form = new WinForms.Form
                {
                    Text = "建筑语义显示",
                    ClientSize = new Drawing.Size(500, 200),
                    StartPosition = WinForms.FormStartPosition.CenterParent,
                    FormBorderStyle = WinForms.FormBorderStyle.FixedDialog,
                    MaximizeBox = false,
                    MinimizeBox = false,
                    ShowInTaskbar = false,
                    AutoScaleMode = WinForms.AutoScaleMode.Dpi,
                    Font = new Drawing.Font("Microsoft YaHei UI", 9F)
                })
                {
                    var label = new WinForms.Label
                    {
                        Text = "选择显示内容（只读瞬态，不创建 CAD 实体）",
                        AutoSize = true,
                        Location = new Drawing.Point(12, 12)
                    };
                    var panel = new WinForms.FlowLayoutPanel
                    {
                        Location = new Drawing.Point(12, 40),
                        Size = new Drawing.Size(476, 148),
                        WrapContents = true
                    };
                    foreach ((string Mode, string Label) item in new[]
                             {
                                 ("Room", "房间 Room"),
                                 ("Electrical", "电气房间 Electrical"),
                                 ("Shaft", "井道 Shaft"),
                                 ("Zone", "特殊区域 Zone"),
                                 ("Wall", "墙 Wall"),
                                 ("Column", "柱 Column"),
                                 ("Opening", "门窗洞口 Opening"),
                                 ("Stair", "楼梯 Stair"),
                                 ("Roof", "屋面线 RoofLine"),
                                 ("All", "全部 All"),
                                 ("Hide", "清除 Hide")
                             })
                    {
                        var button = new WinForms.Button
                        {
                            Text = item.Label,
                            Tag = item.Mode,
                            Size = new Drawing.Size(112, 38),
                            Margin = new WinForms.Padding(3)
                        };
                        button.Click += (_, __) =>
                        {
                            selected = (string)button.Tag;
                            form.DialogResult = WinForms.DialogResult.OK;
                        };
                        panel.Controls.Add(button);
                        if (string.Equals(item.Mode, "Room", StringComparison.Ordinal))
                            form.AcceptButton = button;
                    }
                    form.Controls.Add(label);
                    form.Controls.Add(panel);
                    return AcadApplication.ShowModalDialog(form) == WinForms.DialogResult.OK
                        ? selected
                        : null;
                }
            }
            catch (System.Exception ex)
            {
                editor.WriteMessage("\n[JZBP] 鼠标选择窗口不可用，转为键盘选择: " + ex.Message + "\n");
                var options = new PromptKeywordOptions("\n选择显示类型")
                {
                    AllowNone = true,
                    AppendKeywordsToMessage = true
                };
                foreach (string keyword in new[] { "Room", "Electrical", "Shaft", "Zone", "Wall", "Column", "Opening", "Stair", "Roof", "All", "Hide" })
                    options.Keywords.Add(keyword);
                options.Keywords.Default = "Room";
                PromptResult result = editor.GetKeywords(options);
                return result.Status == PromptStatus.OK
                    ? result.StringResult
                    : result.Status == PromptStatus.None ? "Room" : null;
            }
        }

        private static BuildingSemanticSnapshot LoadSnapshotForCurrentDrawing(Document document)
        {
            string drawingPath = ResolveDrawingPath(document);
            string drawingHash = BuildingSemanticStableId.Sha256File(drawingPath);
            LoadedProjectProfile profile = ResolveProfile(drawingPath, drawingHash);
            DrawingProfileRule? rule = ProjectProfileValidator.FindDrawing(profile.Profile, drawingHash);
            if (rule == null)
                throw new InvalidDataException("当前 DWG 不在项目配置白名单中。");
            string runtimeProjectId = ProjectProfileValidator.ResolveRuntimeProjectId(
                profile.Profile,
                rule,
                drawingHash);
            if (BuildingSemanticRuntimeCache.TryGet(
                    document.Database,
                    drawingHash,
                    profile.Sha256,
                    runtimeProjectId,
                    out BuildingSemanticSnapshot cached))
            {
                return cached;
            }

            string outputDirectory = ResolveOutputDirectory(
                profile.Profile,
                drawingPath,
                rule.DrawingId,
                runtimeProjectId);
            string jsonPath = Path.Combine(outputDirectory, "building-semantics.v1.json");
            if (!File.Exists(jsonPath))
                throw new FileNotFoundException("尚无 building-semantics.v1.json，请先执行 JZBPSCAN。", jsonPath);

            BuildingSemanticSnapshot snapshot = BuildingSemanticJson.DeserializeSnapshot(File.ReadAllText(jsonPath));
            if (!string.Equals(snapshot.Drawing.Sha256, drawingHash, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException(BuildingSemanticReasonCodes.SnapshotDrawingMismatch + ": 快照与当前 DWG 哈希不一致。");
            if (!string.Equals(snapshot.Profile.Sha256, profile.Sha256, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException(BuildingSemanticReasonCodes.SnapshotDrawingMismatch + ": 快照与当前 ProjectProfile 哈希不一致，请重新扫描。");
            if (!string.Equals(snapshot.Profile.ProjectId, runtimeProjectId, StringComparison.Ordinal))
                throw new InvalidDataException(BuildingSemanticReasonCodes.SnapshotDrawingMismatch + ": 快照项目空间与当前 DWG 不一致，请重新扫描。");
            ValidateCanonicalSemanticView(outputDirectory, snapshot);
            BuildingSemanticRuntimeCache.Store(document.Database, snapshot, profile.Profile, jsonPath);
            return snapshot;
        }

        private static string ValidateActiveDrawingForView(
            Document document,
            BuildingSemanticSnapshot expectedSnapshot)
        {
            string drawingPath = ResolveDrawingPath(document);
            string sourceHashBefore = BuildingSemanticStableId.Sha256File(drawingPath);
            if (!string.Equals(expectedSnapshot.Drawing.Sha256, sourceHashBefore, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidDataException(BuildingSemanticReasonCodes.SnapshotDrawingMismatch
                                               + ": 快照与当前磁盘 DWG 哈希不一致。");
            }

            LoadedProjectProfile loadedProfile = ResolveProfile(drawingPath, sourceHashBefore);
            DrawingProfileRule? drawingRule = ProjectProfileValidator.FindDrawing(loadedProfile.Profile, sourceHashBefore);
            if (drawingRule == null)
                throw new InvalidDataException("当前 DWG 不在项目配置白名单中。");
            var file = new FileInfo(drawingPath);
            AnalysisRequest request = CreateAnalysisRequest(
                loadedProfile,
                drawingRule,
                drawingPath,
                sourceHashBefore,
                file);

            int dbmodBefore = ReadDbmod();
            var provider = new AutoCadBuildingFactProvider(document.Database);
            var service = new BuildingSemanticService(provider);
            BuildingSemanticSnapshot activeSnapshot = service.Analyze(request);
            int dbmodAfter = ReadDbmod();
            string sourceHashAfter = BuildingSemanticStableId.Sha256File(drawingPath);

            if (dbmodBefore < 0
                || dbmodAfter < 0
                || dbmodBefore != dbmodAfter
                || !string.Equals(sourceHashBefore, sourceHashAfter, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidDataException(
                    BuildingSemanticReasonCodes.ActiveDrawingModifiedDuringViewValidation
                    + ": JZBPVIEW 复算期间活动图 DBMOD 或源 DWG 字节发生变化，禁止显示快照。");
            }

            string outputDirectory = ResolveOutputDirectory(
                loadedProfile.Profile,
                drawingPath,
                drawingRule.DrawingId,
                request.RuntimeProjectId);
            BuildingSemanticSnapshot comparisonSnapshot = LoadRawSemanticSnapshot(outputDirectory, expectedSnapshot);
            string expectedViewPayloadHash = BuildingSemanticDeterminism.ComputeViewPayload(comparisonSnapshot);
            string actualViewPayloadHash = BuildingSemanticDeterminism.ComputeViewPayload(activeSnapshot);
            if (!string.Equals(expectedViewPayloadHash, actualViewPayloadHash, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidDataException(
                    BuildingSemanticReasonCodes.ActiveDrawingSemanticMismatch
                    + ": 活动图中用于高亮的对象类型、分类、状态或几何与磁盘侧载快照不一致，可能存在未保存编辑；禁止高亮。"
                    + " 快照=" + expectedViewPayloadHash.Substring(0, 12)
                    + "/" + comparisonSnapshot.Objects.Count + "[" + DescribeSemanticTypes(comparisonSnapshot) + "]，"
                    + "活动=" + actualViewPayloadHash.Substring(0, 12)
                    + "/" + activeSnapshot.Objects.Count + "[" + DescribeSemanticTypes(activeSnapshot) + "]。");
            }

            string expectedAuditPayloadHash = BuildingSemanticDeterminism.ComputeSemanticPayload(comparisonSnapshot);
            string actualAuditPayloadHash = BuildingSemanticDeterminism.ComputeSemanticPayload(activeSnapshot);
            if (!string.Equals(expectedAuditPayloadHash, actualAuditPayloadHash, StringComparison.OrdinalIgnoreCase))
            {
                document.Editor.WriteMessage(
                    "\n[JZBP] 提示：活动图与磁盘快照的代理核账/复核诊断存在解释器差异，"
                    + "但高亮对象的类型、分类、状态和几何一致；已按显示载荷安全通过。\n");
            }

            return BuildingSemanticDeterminism.ComputeViewPayload(expectedSnapshot);
        }

        private static BuildingSemanticSnapshot LoadRawSemanticSnapshot(
            string outputDirectory,
            BuildingSemanticSnapshot fallback)
        {
            string rawPath = Path.Combine(outputDirectory, "building-semantics.raw.v1.json");
            if (!File.Exists(rawPath))
                return fallback;
            BuildingSemanticSnapshot raw = BuildingSemanticJson.DeserializeSnapshot(File.ReadAllText(rawPath));
            if (!string.Equals(raw.Drawing.Sha256, fallback.Drawing.Sha256, StringComparison.OrdinalIgnoreCase)
                || !string.Equals(raw.Profile.Sha256, fallback.Profile.Sha256, StringComparison.OrdinalIgnoreCase)
                || !string.Equals(raw.Profile.ProjectId, fallback.Profile.ProjectId, StringComparison.Ordinal))
                throw new InvalidDataException(BuildingSemanticReasonCodes.SnapshotDrawingMismatch
                                               + ": 原始 L3 与规范 L3 的图纸或项目身份不一致。");
            return raw;
        }

        private static void ValidateCanonicalSemanticView(
            string outputDirectory,
            BuildingSemanticSnapshot canonical)
        {
            BuildingSemanticSnapshot raw = LoadRawSemanticSnapshot(outputDirectory, canonical);
            if (ReferenceEquals(raw, canonical))
                return; // 兼容 0.2.7 及更早、尚未输出 raw 文件的快照。

            BuildingSemanticSnapshot expected = raw;
            string overridePath = Path.Combine(outputDirectory, "building-semantics.override.v1.json");
            if (File.Exists(overridePath))
            {
                try
                {
                    BuildingSemanticOverrideDocument document = BuildingSemanticJson.DeserializeOverride(
                        File.ReadAllText(overridePath));
                    expected = BuildingSemanticOverrideResolver.Apply(raw, document).Snapshot;
                }
                catch (System.Exception ex)
                {
                    expected = BuildingSemanticOverrideResolver.FailClosed(raw, ex.Message);
                }
            }

            if (!string.Equals(expected.DeterministicContentHash, canonical.DeterministicContentHash,
                    StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException(BuildingSemanticReasonCodes.SnapshotContentHashMismatch
                                               + ": 规范 L3 不是由当前原始 L3 与审核覆盖生成，请重新扫描。");
        }

        private static string DescribeSemanticTypes(BuildingSemanticSnapshot snapshot)
        {
            return string.Join(",", (snapshot.Objects ?? new List<SemanticObject>())
                .GroupBy(item => item.Type)
                .OrderBy(group => group.Key)
                .Select(group => group.Key + "=" + group.Count().ToString(CultureInfo.InvariantCulture)));
        }

        private static AnalysisRequest CreateAnalysisRequest(
            LoadedProjectProfile loadedProfile,
            DrawingProfileRule drawingRule,
            string drawingPath,
            string drawingHash,
            FileInfo file)
        {
            return new AnalysisRequest
            {
                Profile = loadedProfile.Profile,
                ProfileHash = loadedProfile.Sha256,
                RuntimeProjectId = ProjectProfileValidator.ResolveRuntimeProjectId(
                    loadedProfile.Profile,
                    drawingRule,
                    drawingHash),
                DrawingPath = drawingPath,
                DrawingHash = drawingHash,
                DrawingId = drawingRule.DrawingId,
                SourceFileLength = file.Length,
                SourceLastWriteUtc = file.LastWriteTimeUtc
            };
        }

        private static LoadedProjectProfile ResolveProfile(string drawingPath, string drawingHash)
        {
            string explicitPath = Environment.GetEnvironmentVariable("JZBP_PROFILE");
            if (!string.IsNullOrWhiteSpace(explicitPath))
                return ProjectProfileDiscovery.RequireMatchingProfile(explicitPath, drawingHash);

            var roots = new List<string>();
            string configuredRoot = Environment.GetEnvironmentVariable("JZBP_PROFILE_ROOT");
            if (!string.IsNullOrWhiteSpace(configuredRoot))
                roots.Add(configuredRoot);
            // 未指定配置时使用随插件发布的通用配置，不按图纸所在目录猜测项目配置。
            string? installedProfilesRoot = ProjectProfileDiscovery.FindInstalledProfilesRoot(
                typeof(BuildingSemanticsCommands).Assembly.Location);
            LoadedProjectProfile? discovered = ProjectProfileDiscovery.ResolveExistingThenInstalled(
                roots,
                installedProfilesRoot,
                drawingHash);
            if (discovered != null)
                return discovered;
            throw new FileNotFoundException(
                "插件的通用配置文件缺失。请保留DLL旁的profiles目录；自定义配置可放任意位置并用JZBP_PROFILE指定文件或JZBP_PROFILE_ROOT指定目录。图纸无需放在配置目录。",
                drawingPath);
        }

        private static string ResolveOutputDirectory(
            ProjectProfile profile,
            string drawingPath,
            string drawingId,
            string runtimeProjectId)
        {
            return BuildingSemanticProjectScope.ResolveOutputDirectory(
                profile,
                drawingPath,
                drawingId,
                runtimeProjectId);
        }

        private static string ResolveDrawingPath(Document document)
        {
            var candidates = new List<string>();
            try
            {
                string prefix = Convert.ToString(AcadApplication.GetSystemVariable("DWGPREFIX"), CultureInfo.InvariantCulture) ?? string.Empty;
                string name = Convert.ToString(AcadApplication.GetSystemVariable("DWGNAME"), CultureInfo.InvariantCulture) ?? string.Empty;
                if (!string.IsNullOrWhiteSpace(name))
                    candidates.Add(Path.Combine(prefix, name));
            }
            catch
            {
                // 某些宿主或无活动文档状态无法读取系统变量，继续使用只读文档属性。
            }

            candidates.Add(document.Name);
            candidates.Add(document.Database.Filename);
            foreach (string candidate in candidates
                         .Where(value => !string.IsNullOrWhiteSpace(value))
                         .Select(value => value.Trim().Trim('"'))
                         .Distinct(StringComparer.OrdinalIgnoreCase))
            {
                try
                {
                    string fullPath = Path.GetFullPath(candidate);
                    if (File.Exists(fullPath)
                        && string.Equals(Path.GetExtension(fullPath), ".dwg", StringComparison.OrdinalIgnoreCase))
                    {
                        return fullPath;
                    }
                }
                catch
                {
                    // 保留其余候选；最终仍由 DWG 后缀、存在性和配置哈希三重门槛校验。
                }
            }

            string observed = string.Join(" | ", candidates
                .Where(value => !string.IsNullOrWhiteSpace(value))
                .Select(value => value.Trim())
                .Distinct(StringComparer.OrdinalIgnoreCase));
            throw new FileNotFoundException(
                "当前活动文档没有可读取的 DWG 路径；BAK 仍禁止作为输入。候选=" + observed);
        }

        private static int ReadDbmod()
        {
            try
            {
                return Convert.ToInt32(AcadApplication.GetSystemVariable("DBMOD"), CultureInfo.InvariantCulture);
            }
            catch
            {
                return -1;
            }
        }

        private static string ResolveProducerBinaryHash()
        {
            string location = typeof(BuildingSemanticsCommands).Assembly.Location;
            return string.IsNullOrWhiteSpace(location) || !File.Exists(location)
                ? string.Empty
                : BuildingSemanticStableId.Sha256File(location);
        }

        private static void WriteSummary(
            Editor editor,
            BuildingRecognitionBundle layers,
            string profileProjectId,
            string primitiveJsonPath,
            string geometryJsonPath,
            string jsonPath,
            string htmlPath)
        {
            BuildingSemanticSnapshot snapshot = layers.SemanticSnapshot;
            editor.WriteMessage("\n[JZBP] 项目空间=" + snapshot.Profile.ProjectId);
            if (!string.Equals(snapshot.Profile.ProjectId, profileProjectId, StringComparison.Ordinal))
            {
                editor.WriteMessage("（未登记图纸自动隔离；规则模板=" + profileProjectId + "）");
            }
            editor.WriteMessage("\n[JZBP] 三层状态: 图元=" + layers.PrimitiveSnapshot.Status
                                + " (" + layers.PrimitiveSnapshot.Metrics.PrimitiveCount + ")"
                                + "，几何=" + layers.GeometrySnapshot.Status
                                + " (" + layers.GeometrySnapshot.Metrics.GeometryFactCount + ")"
                                + "，语义=" + snapshot.Status);
            editor.WriteMessage("\n[JZBP] 状态=" + snapshot.Status
                                + "，对象=" + snapshot.Metrics.SemanticObjectCount
                                + " (Accepted=" + snapshot.Metrics.AcceptedObjectCount
                                + ", Review=" + snapshot.Metrics.ReviewObjectCount
                                + ", Rejected=" + snapshot.Metrics.RejectedObjectCount + ")"
                                + "，顶层代理=" + snapshot.Metrics.TopLevelProxyObjectCount
                                + "，可达实例=" + snapshot.Metrics.ReachableProxyInstanceCount
                                + "，耗时=" + snapshot.Metrics.AnalysisElapsedMilliseconds + "ms");
            int unresolvedSpaceLabels = snapshot.Findings.Count(item =>
                string.Equals(
                    item.ReasonCode,
                    BuildingSemanticReasonCodes.KnownSpaceLabelUnresolved,
                    StringComparison.Ordinal));
            if (unresolvedSpaceLabels > 0)
            {
                editor.WriteMessage("\n[JZBP] 制图复核: 已知空间名称未形成唯一墙围合="
                                    + unresolvedSpaceLabels
                                    + "；明细见 HTML/语义 JSON 的 KNOWN_SPACE_LABEL_UNRESOLVED。");
            }
            editor.WriteMessage("\n[JZBP] 原图字节不变=" + snapshot.Integrity.SourceBytesUnchanged
                                + "，扫描输入=" + snapshot.Integrity.ScanInputMode
                                + "，输入只读=" + snapshot.Integrity.InputDatabaseReadOnly
                                + "，活动图DBMOD不变=" + snapshot.Integrity.DbmodUnchanged
                                + " (" + snapshot.Integrity.DbmodBefore + "=>" + snapshot.Integrity.DbmodAfter + ")");
            editor.WriteMessage("\n[JZBP] 图元JSON: " + primitiveJsonPath);
            editor.WriteMessage("\n[JZBP] 几何JSON: " + geometryJsonPath);
            editor.WriteMessage("\n[JZBP] 语义JSON: " + jsonPath);
            editor.WriteMessage("\n[JZBP] HTML: " + htmlPath + "\n");
        }

    }

    internal sealed class ObservationRegionSelectionReceiptSet
    {
        public const string CurrentSchemaVersion = "building-semantics-observation-region-selection.v1";

        [JsonProperty("schema_version")]
        public string SchemaVersion { get; set; } = CurrentSchemaVersion;

        [JsonProperty("project_id")]
        public string ProjectId { get; set; } = string.Empty;

        [JsonProperty("profile_sha256")]
        public string ProfileSha256 { get; set; } = string.Empty;

        [JsonProperty("drawing_id")]
        public string DrawingId { get; set; } = string.Empty;

        [JsonProperty("drawing_sha256")]
        public string DrawingSha256 { get; set; } = string.Empty;

        [JsonProperty("selections")]
        public List<ObservationRegionSelectionReceipt> Selections { get; set; } = new List<ObservationRegionSelectionReceipt>();
    }

    internal sealed class ObservationRegionSelectionReceipt
    {
        [JsonProperty("region_code")]
        public string RegionCode { get; set; } = string.Empty;

        [JsonProperty("region_name")]
        public string RegionName { get; set; } = string.Empty;

        [JsonProperty("role")]
        public string Role { get; set; } = string.Empty;

        [JsonProperty("confirmed_by")]
        public string ConfirmedBy { get; set; } = string.Empty;

        [JsonProperty("confirmed_at_utc")]
        public string ConfirmedAtUtc { get; set; } = string.Empty;

        [JsonProperty("polygon_wcs_millimeters")]
        public List<SemanticPoint> PolygonWcsMillimeters { get; set; } = new List<SemanticPoint>();
    }
    internal static class BuildingSemanticRuntimeCache
    {
        private static readonly object SyncRoot = new object();
        private static Database? _database;
        private static string _snapshotJson = string.Empty;
        private static string _drawingHash = string.Empty;
        private static string _profileHash = string.Empty;
        private static string _projectId = string.Empty;

        public static void Store(Database database, BuildingSemanticSnapshot snapshot, ProjectProfile profile, string jsonPath)
        {
            if (database == null)
                throw new ArgumentNullException(nameof(database));
            if (snapshot == null)
                throw new ArgumentNullException(nameof(snapshot));

            string actualHash = BuildingSemanticDeterminism.Compute(snapshot);
            if (string.IsNullOrWhiteSpace(snapshot.DeterministicContentHash)
                || !string.Equals(snapshot.DeterministicContentHash, actualHash, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidDataException(BuildingSemanticReasonCodes.SnapshotContentHashMismatch
                                               + ": 禁止缓存内容哈希无效的快照。");
            }

            string canonicalJson = BuildingSemanticJson.SerializeSnapshot(snapshot);
            lock (SyncRoot)
            {
                _database = database;
                _drawingHash = snapshot.Drawing.Sha256 ?? string.Empty;
                _profileHash = snapshot.Profile.Sha256 ?? string.Empty;
                _projectId = snapshot.Profile.ProjectId ?? string.Empty;
                _snapshotJson = canonicalJson;
            }
        }

        public static bool TryGet(
            Database database,
            string drawingHash,
            string profileHash,
            string projectId,
            out BuildingSemanticSnapshot snapshot)
        {
            lock (SyncRoot)
            {
                bool match = ReferenceEquals(_database, database)
                             && !string.IsNullOrWhiteSpace(_snapshotJson)
                             && string.Equals(_drawingHash, drawingHash, StringComparison.OrdinalIgnoreCase)
                             && string.Equals(_profileHash, profileHash, StringComparison.OrdinalIgnoreCase)
                             && string.Equals(_projectId, projectId, StringComparison.Ordinal);
                if (!match)
                {
                    snapshot = new BuildingSemanticSnapshot();
                    return false;
                }

                try
                {
                    BuildingSemanticSnapshot candidate = BuildingSemanticJson.DeserializeSnapshot(_snapshotJson);
                    if (!string.Equals(candidate.Drawing.Sha256, drawingHash, StringComparison.OrdinalIgnoreCase)
                        || !string.Equals(candidate.Profile.Sha256, profileHash, StringComparison.OrdinalIgnoreCase)
                        || !string.Equals(candidate.Profile.ProjectId, projectId, StringComparison.Ordinal))
                    {
                        ClearUnsafe();
                        snapshot = new BuildingSemanticSnapshot();
                        return false;
                    }

                    // 每次反序列化一份新对象，调用方无法通过修改返回值污染缓存中的权威快照。
                    snapshot = candidate;
                    return true;
                }
                catch
                {
                    ClearUnsafe();
                    snapshot = new BuildingSemanticSnapshot();
                    return false;
                }
            }
        }

        private static void ClearUnsafe()
        {
            _database = null;
            _snapshotJson = string.Empty;
            _drawingHash = string.Empty;
            _profileHash = string.Empty;
            _projectId = string.Empty;
        }
    }

    internal static class BuildingSemanticTransientView
    {
        private static readonly List<Entity> Drawables = new List<Entity>();
        private static Database? _database;
        private static int _subDrawingMode = 128;

        public static bool IsVisibleFor(Database database)
        {
            return ReferenceEquals(_database, database) && Drawables.Count > 0;
        }

        public static int Show(
            Database database,
            BuildingSemanticSnapshot snapshot,
            string viewMode,
            double roomBandWidth,
            out int objectCount)
        {
            Clear();
            _database = database;
            TransientManager manager = TransientManager.CurrentTransientManager;
            var viewports = new IntegerCollection();
            int subDrawingMode = 128;
            manager.GetFreeSubDrawingMode(TransientDrawingMode.DirectShortTerm, viewports, ref subDrawingMode);
            _subDrawingMode = subDrawingMode > 0 ? subDrawingMode : 128;
            List<SemanticObject> selectedObjects = snapshot.Objects
                .Where(item => MatchesViewMode(item, viewMode))
                .ToList();
            objectCount = selectedObjects.Count;
            foreach (SemanticObject item in selectedObjects)
            {
                short colorIndex = GetTypeColorIndex(item);
                foreach (Entity drawable in CreateDrawables(item, colorIndex, roomBandWidth))
                {
                    bool added = manager.AddTransient(
                        drawable,
                        TransientDrawingMode.DirectShortTerm,
                        _subDrawingMode,
                        viewports);
                    if (added)
                        Drawables.Add(drawable);
                    else
                        drawable.Dispose();
                }
            }
            return Drawables.Count;
        }

        private static bool MatchesViewMode(SemanticObject item, string viewMode)
        {
            if (string.Equals(viewMode, "All", StringComparison.OrdinalIgnoreCase))
                return true;
            if (string.Equals(viewMode, "Room", StringComparison.OrdinalIgnoreCase))
                return item.Type == SemanticObjectType.Space;
            if (string.Equals(viewMode, "Electrical", StringComparison.OrdinalIgnoreCase))
                return IsElectricalSpace(item);
            if (string.Equals(viewMode, "Shaft", StringComparison.OrdinalIgnoreCase))
                return item.Type == SemanticObjectType.Shaft;
            if (string.Equals(viewMode, "Zone", StringComparison.OrdinalIgnoreCase))
                return item.Type == SemanticObjectType.Zone;
            if (string.Equals(viewMode, "Wall", StringComparison.OrdinalIgnoreCase))
                return item.Type == SemanticObjectType.Wall;
            if (string.Equals(viewMode, "Column", StringComparison.OrdinalIgnoreCase))
                return item.Type == SemanticObjectType.Column;
            if (string.Equals(viewMode, "Opening", StringComparison.OrdinalIgnoreCase))
            {
                return item.Type == SemanticObjectType.Opening
                       || item.Type == SemanticObjectType.Door
                       || item.Type == SemanticObjectType.Window;
            }
            if (string.Equals(viewMode, "Stair", StringComparison.OrdinalIgnoreCase))
                return item.Type == SemanticObjectType.Stair;
            if (string.Equals(viewMode, "Roof", StringComparison.OrdinalIgnoreCase))
                return item.Type == SemanticObjectType.RoofLine;
            return false;
        }

        private static short GetTypeColorIndex(SemanticObject item)
        {
            if (IsElectricalSpace(item))
                return 30;
            if (item.Type == SemanticObjectType.Wall
                && string.Equals(item.Classification, WallClassification.Shear.ToString(), StringComparison.OrdinalIgnoreCase))
            {
                return 1;
            }

            switch (item.Type)
            {
                case SemanticObjectType.Space: return 4;
                case SemanticObjectType.Shaft: return 140;
                case SemanticObjectType.Zone: return 5;
                case SemanticObjectType.Wall: return 2;
                case SemanticObjectType.Column: return 6;
                case SemanticObjectType.Opening: return 1;
                case SemanticObjectType.Door: return 30;
                case SemanticObjectType.Window: return 5;
                case SemanticObjectType.Stair: return 3;
                case SemanticObjectType.RoofLine: return 170;
                default: return 7;
            }
        }

        private static bool IsElectricalSpace(SemanticObject item)
        {
            return item.Type == SemanticObjectType.Space
                   && (string.Equals(item.UseCode, "ELECTRICAL_ROOM", StringComparison.Ordinal)
                       || string.Equals(item.UseCode, "FIRE_CONTROL_ROOM", StringComparison.Ordinal));
        }

        public static int Clear()
        {
            int count = Drawables.Count;
            if (count == 0)
            {
                _database = null;
                _subDrawingMode = 128;
                return 0;
            }

            TransientManager manager = TransientManager.CurrentTransientManager;
            var viewports = new IntegerCollection();
            bool erased = false;
            try
            {
                erased = manager.EraseTransients(
                    TransientDrawingMode.DirectShortTerm,
                    _subDrawingMode,
                    viewports);
            }
            catch { }
            if (!erased)
            {
                foreach (Entity drawable in Drawables)
                {
                    try { manager.EraseTransient(drawable, viewports); }
                    catch { }
                }
            }
            foreach (Entity drawable in Drawables)
                drawable.Dispose();
            Drawables.Clear();
            _database = null;
            _subDrawingMode = 128;
            return count;
        }

        private static IEnumerable<Entity> CreateDrawables(
            SemanticObject item,
            short colorIndex,
            double roomBandWidth)
        {
            var result = new List<Entity>();
            SemanticGeometry geometry = item.Geometry ?? new SemanticGeometry();
            foreach (List<SemanticPoint> path in geometry.Paths ?? new List<List<SemanticPoint>>())
            {
                if (path.Count == 1)
                {
                    var circle = new Circle(
                        new Point3d(path[0].X, path[0].Y, path[0].Z),
                        Vector3d.ZAxis,
                        200.0)
                    {
                        Color = Color.FromColorIndex(ColorMethod.ByAci, colorIndex),
                        LineWeight = LineWeight.LineWeight050
                    };
                    result.Add(circle);
                    continue;
                }
                if (path.Count < 2)
                    continue;

                bool shouldClose = path.Count >= 3
                                   && (geometry.Kind == GeometryKind.Polygon
                                       || item.Type == SemanticObjectType.RoofLine && geometry.IsClosed
                                       || item.Type == SemanticObjectType.Space
                                       || item.Type == SemanticObjectType.Shaft
                                       || item.Type == SemanticObjectType.Column
                                       || item.Type == SemanticObjectType.Zone);

                bool patternedWall = item.Type == SemanticObjectType.Wall
                                     && string.Equals(
                                         item.Classification,
                                         WallClassification.Shear.ToString(),
                                         StringComparison.OrdinalIgnoreCase);
                if ((item.Type == SemanticObjectType.Space
                     || item.Type == SemanticObjectType.Shaft
                     || item.Type == SemanticObjectType.Zone
                     || patternedWall) && shouldClose)
                {
                    AddRoomPattern(result, path, colorIndex, roomBandWidth);
                    continue;
                }

                var polyline = new Autodesk.AutoCAD.DatabaseServices.Polyline(path.Count)
                {
                    Color = Color.FromColorIndex(ColorMethod.ByAci, colorIndex),
                    LineWeight = LineWeight.LineWeight050,
                    ConstantWidth = item.Status == DecisionStatus.Accepted ? 25.0 : 50.0
                };
                for (int index = 0; index < path.Count; index++)
                    polyline.AddVertexAt(index, new Point2d(path[index].X, path[index].Y), 0, 0, 0);
                polyline.Closed = shouldClose;
                result.Add(polyline);
            }
            return result;
        }

        private static void AddRoomPattern(
            ICollection<Entity> result,
            IReadOnlyList<SemanticPoint> path,
            short colorIndex,
            double displayScale)
        {
            int count = path.Count;
            if (count > 2 && Distance2d(path[0], path[count - 1]) < 0.001)
                count--;
            if (count < 3)
                return;

            double dashLength = Math.Max(300.0, displayScale * 2.0);
            double period = dashLength * 1.75;
            for (int index = 0; index < count; index++)
            {
                SemanticPoint start = path[index];
                SemanticPoint end = path[(index + 1) % count];
                double length = Distance2d(start, end);
                if (length < 0.001)
                    continue;
                for (double cursor = 0; cursor < length; cursor += period)
                {
                    double from = cursor / length;
                    double to = Math.Min(length, cursor + dashLength) / length;
                    AddLine(result, Interpolate(start, end, from), Interpolate(start, end, to), colorIndex);
                }
            }

            double originX = path[0].X;
            double originY = path[0].Y;
            double minimum = double.MaxValue;
            double maximum = double.MinValue;
            for (int index = 0; index < count; index++)
            {
                double value = path[index].X - originX - (path[index].Y - originY);
                minimum = Math.Min(minimum, value);
                maximum = Math.Max(maximum, value);
            }

            double spacing = Math.Max(450.0, displayScale * 3.0);
            double range = maximum - minimum;
            if (range < 0.001)
                return;
            if (range / spacing > 120.0)
                spacing = range / 120.0;

            double first = Math.Floor(minimum / spacing) * spacing;
            for (double value = first; value <= maximum; value += spacing)
            {
                var intersections = new List<Point3d>();
                for (int index = 0; index < count; index++)
                {
                    SemanticPoint start = path[index];
                    SemanticPoint end = path[(index + 1) % count];
                    double startValue = start.X - originX - (start.Y - originY);
                    double endValue = end.X - originX - (end.Y - originY);
                    bool crosses = startValue <= value && value < endValue
                                   || endValue <= value && value < startValue;
                    if (!crosses || Math.Abs(endValue - startValue) < 0.001)
                        continue;
                    intersections.Add(Interpolate(start, end, (value - startValue) / (endValue - startValue)));
                }

                intersections.Sort((left, right) => (left.X + left.Y).CompareTo(right.X + right.Y));
                for (int index = 0; index + 1 < intersections.Count; index += 2)
                    AddLine(result, intersections[index], intersections[index + 1], colorIndex);
            }
        }

        private static double Distance2d(SemanticPoint start, SemanticPoint end)
        {
            double x = end.X - start.X;
            double y = end.Y - start.Y;
            return Math.Sqrt(x * x + y * y);
        }

        private static Point3d Interpolate(SemanticPoint start, SemanticPoint end, double amount)
        {
            return new Point3d(
                start.X + (end.X - start.X) * amount,
                start.Y + (end.Y - start.Y) * amount,
                start.Z + (end.Z - start.Z) * amount);
        }

        private static void AddLine(ICollection<Entity> result, Point3d start, Point3d end, short colorIndex)
        {
            result.Add(new Line(start, end)
            {
                Color = Color.FromColorIndex(ColorMethod.ByAci, colorIndex),
                LineWeight = LineWeight.LineWeight050
            });
        }
    }
}
