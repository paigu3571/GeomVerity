// SPDX-License-Identifier: MPL-2.0
// Copyright (c) 2026 张田; 著作权人、原作者及维护者：张田；其他贡献者和第三方保留各自权利。
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Net;
using System.Text;
using Newtonsoft.Json;
using Newtonsoft.Json.Converters;
using Newtonsoft.Json.Serialization;

namespace JZBP.BuildingSemantics.Core
{
    public static class BuildingSemanticJson
    {
        private static readonly JsonSerializerSettings Settings = CreateSettings(false);
        private static readonly JsonSerializerSettings StrictSettings = CreateSettings(true);

        public static string SerializeSnapshot(BuildingSemanticSnapshot snapshot)
        {
            return JsonConvert.SerializeObject(snapshot, Formatting.None, Settings);
        }

        public static string SerializePrimitiveSnapshot(CadPrimitiveSnapshot snapshot)
        {
            return JsonConvert.SerializeObject(snapshot, Formatting.None, Settings);
        }

        public static string SerializeGeometrySnapshot(BuildingGeometrySnapshot snapshot)
        {
            return JsonConvert.SerializeObject(snapshot, Formatting.None, Settings);
        }

        public static BuildingSemanticSnapshot DeserializeSnapshot(string json)
        {
            BuildingSemanticSnapshot? snapshot = JsonConvert.DeserializeObject<BuildingSemanticSnapshot>(json, StrictSettings);
            if (snapshot == null || !string.Equals(snapshot.SchemaVersion, BuildingSemanticSchema.SnapshotV1, StringComparison.Ordinal))
                throw new InvalidDataException("不是受支持的 building-semantics.v1 快照。");
            string actualHash = BuildingSemanticDeterminism.Compute(snapshot);
            if (string.IsNullOrWhiteSpace(snapshot.DeterministicContentHash)
                || !string.Equals(snapshot.DeterministicContentHash, actualHash, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidDataException(BuildingSemanticReasonCodes.SnapshotContentHashMismatch + ": 快照内容与 deterministic_content_hash 不一致。");
            }
            return snapshot;
        }

        public static string SerializeOverride(BuildingSemanticOverrideDocument document)
        {
            return JsonConvert.SerializeObject(document, Formatting.None, Settings);
        }

        public static BuildingSemanticOverrideDocument DeserializeOverride(string json)
        {
            BuildingSemanticOverrideDocument? document =
                JsonConvert.DeserializeObject<BuildingSemanticOverrideDocument>(json, StrictSettings);
            if (document == null || !string.Equals(document.SchemaVersion, BuildingSemanticSchema.OverrideV1, StringComparison.Ordinal))
                throw new InvalidDataException("不是受支持的 building-semantics.override.v1 文件。");
            return document;
        }

        public static CadPrimitiveSnapshot DeserializePrimitiveSnapshot(string json)
        {
            CadPrimitiveSnapshot? snapshot = JsonConvert.DeserializeObject<CadPrimitiveSnapshot>(json, StrictSettings);
            return ValidatePrimitiveSnapshot(snapshot);
        }

        public static CadPrimitiveSnapshot LoadPrimitiveSnapshot(string path)
        {
            if (string.IsNullOrWhiteSpace(path))
                throw new ArgumentException("图元快照路径为空。", nameof(path));
            using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read,
                       FileShare.ReadWrite | FileShare.Delete, 1048576, FileOptions.SequentialScan))
            using (var textReader = new StreamReader(stream, new UTF8Encoding(false, true), true, 1048576))
            using (var jsonReader = new JsonTextReader(textReader) { DateParseHandling = DateParseHandling.None })
            {
                CadPrimitiveSnapshot? snapshot = JsonSerializer.Create(StrictSettings)
                    .Deserialize<CadPrimitiveSnapshot>(jsonReader);
                return ValidatePrimitiveSnapshot(snapshot);
            }
        }

        private static CadPrimitiveSnapshot ValidatePrimitiveSnapshot(CadPrimitiveSnapshot? snapshot)
        {
            if (snapshot == null || !string.Equals(snapshot.SchemaVersion, BuildingSemanticSchema.PrimitiveSnapshotV1, StringComparison.Ordinal))
                throw new InvalidDataException("不是受支持的 cad-primitives.v1 快照。");
            string actualHash = UsesCanonicalBinaryV2(snapshot.DeterministicHashAlgorithm)
                ? RecognitionLayerDeterminism.Compute(snapshot)
                : RecognitionLayerDeterminism.ComputeLegacyTextV1(snapshot);
            if (string.IsNullOrWhiteSpace(snapshot.DeterministicContentHash)
                || !string.Equals(snapshot.DeterministicContentHash, actualHash, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidDataException(BuildingSemanticReasonCodes.SnapshotContentHashMismatch
                                               + ": 图元层内容与 deterministic_content_hash 不一致。");
            }
            return snapshot;
        }

        public static BuildingGeometrySnapshot DeserializeGeometrySnapshot(string json)
        {
            BuildingGeometrySnapshot? snapshot = JsonConvert.DeserializeObject<BuildingGeometrySnapshot>(json, StrictSettings);
            if (snapshot == null || !string.Equals(snapshot.SchemaVersion, BuildingSemanticSchema.GeometrySnapshotV1, StringComparison.Ordinal))
                throw new InvalidDataException("不是受支持的 building-geometry.v1 快照。");
            string actualHash = UsesCanonicalBinaryV2(snapshot.DeterministicHashAlgorithm)
                ? RecognitionLayerDeterminism.Compute(snapshot)
                : RecognitionLayerDeterminism.ComputeLegacyTextV1(snapshot);
            if (string.IsNullOrWhiteSpace(snapshot.DeterministicContentHash)
                || !string.Equals(snapshot.DeterministicContentHash, actualHash, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidDataException(BuildingSemanticReasonCodes.SnapshotContentHashMismatch
                                               + ": 几何层内容与 deterministic_content_hash 不一致。");
            }
            return snapshot;
        }

        public static LoadedProjectProfile LoadProfile(string path)
        {
            if (string.IsNullOrWhiteSpace(path))
                throw new ArgumentException("项目配置路径为空。", nameof(path));
            string fullPath = Path.GetFullPath(path);
            string json = File.ReadAllText(fullPath, Encoding.UTF8);
            ProjectProfile? profile = JsonConvert.DeserializeObject<ProjectProfile>(json, StrictSettings);
            if (profile == null)
                throw new InvalidDataException("项目配置反序列化为空。");
            ProfileValidationResult validation = ProjectProfileValidator.Validate(profile);
            if (!validation.IsValid)
                throw new InvalidDataException(string.Join("；", validation.Messages));
            return new LoadedProjectProfile
            {
                Path = fullPath,
                Sha256 = BuildingSemanticStableId.Sha256File(fullPath),
                Profile = profile
            };
        }

        public static void WriteUtf8(string path, string content)
        {
            string? directory = Path.GetDirectoryName(Path.GetFullPath(path));
            if (!string.IsNullOrWhiteSpace(directory))
                Directory.CreateDirectory(directory);
            File.WriteAllText(path, content ?? string.Empty, new UTF8Encoding(false));
        }

        private static JsonSerializerSettings CreateSettings(bool strict)
        {
            var resolver = new DefaultContractResolver
            {
                NamingStrategy = new SnakeCaseNamingStrategy
                {
                    ProcessDictionaryKeys = false,
                    OverrideSpecifiedNames = false
                }
            };
            var settings = new JsonSerializerSettings
            {
                ContractResolver = resolver,
                Culture = CultureInfo.InvariantCulture,
                DateParseHandling = DateParseHandling.None,
                FloatFormatHandling = FloatFormatHandling.String,
                Formatting = Formatting.None,
                MissingMemberHandling = strict ? MissingMemberHandling.Error : MissingMemberHandling.Ignore,
                NullValueHandling = NullValueHandling.Include
            };
            settings.Converters.Add(new StringEnumConverter(new SnakeCaseNamingStrategy(), false));
            return settings;
        }

        private static bool UsesCanonicalBinaryV2(string declaredAlgorithm)
        {
            return string.Equals(declaredAlgorithm, RecognitionLayerDeterminism.CanonicalBinaryV2, StringComparison.Ordinal);
        }
    }

    public sealed class LoadedProjectProfile
    {
        public string Path { get; set; } = string.Empty;
        public string Sha256 { get; set; } = string.Empty;
        public ProjectProfile Profile { get; set; } = new ProjectProfile();
    }

    public static class BuildingSemanticHtmlReport
    {
        public static string Build(BuildingRecognitionBundle layers, ProjectProfile profile)
        {
            if (layers == null)
                throw new ArgumentNullException(nameof(layers));
            return BuildCore(layers.SemanticSnapshot, profile, layers);
        }

        public static string Build(BuildingSemanticSnapshot snapshot, ProjectProfile profile)
        {
            return BuildCore(snapshot, profile, null);
        }

        private static string BuildCore(BuildingSemanticSnapshot snapshot, ProjectProfile profile, BuildingRecognitionBundle? layers)
        {
            if (snapshot == null)
                throw new ArgumentNullException(nameof(snapshot));

            string statusClass = snapshot.Status == AnalysisRunStatus.Accepted
                ? "accepted"
                : snapshot.Status == AnalysisRunStatus.Review ? "review" : "failed";
            var html = new StringBuilder(64 * 1024);
            html.Append("<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">");
            html.Append("<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">");
            html.Append("<title>建筑平面统一语义复核</title><style>");
            html.Append("body{font-family:'Microsoft YaHei',Arial,sans-serif;margin:0;background:#f4f6f8;color:#1f2937}main{max-width:1480px;margin:auto;padding:24px}");
            html.Append("h1{font-size:26px;margin:0 0 8px}h2{font-size:19px;margin-top:30px}.muted{color:#64748b}.banner{padding:16px 20px;border-radius:8px;margin:18px 0;font-weight:700}");
            html.Append(".banner.accepted{background:#dcfce7;color:#166534}.banner.review{background:#fef3c7;color:#92400e}.banner.failed{background:#fee2e2;color:#991b1b}");
            html.Append(".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}.card{background:white;border:1px solid #e2e8f0;border-radius:8px;padding:14px}.value{font-size:24px;font-weight:700}");
            html.Append("table{width:100%;border-collapse:collapse;background:white;font-size:13px}th,td{border:1px solid #e2e8f0;padding:8px;text-align:left;vertical-align:top}th{background:#eef2f7;position:sticky;top:0}");
            html.Append(".tag{display:inline-block;border-radius:999px;padding:2px 8px;font-size:12px}.tag.accepted{background:#dcfce7;color:#166534}.tag.review{background:#fef3c7;color:#92400e}.tag.rejected,.tag.error{background:#fee2e2;color:#991b1b}");
            html.Append("code{font-family:Consolas,monospace;word-break:break-all}.notice{background:#fff;border-left:4px solid #f59e0b;padding:12px 16px}.scroll{overflow:auto;max-height:680px}</style></head><body><main>");
            html.Append("<h1>建筑平面统一语义复核报告</h1><div class=\"muted\">schema: ").Append(E(snapshot.SchemaVersion)).Append(" ｜ deterministic hash: <code>").Append(E(snapshot.DeterministicContentHash)).Append("</code></div>");
            html.Append("<div class=\"banner ").Append(statusClass).Append("\">")
                .Append(layers == null ? "运行状态：" : "语义层状态：").Append(E(snapshot.Status.ToString()))
                .Append("　原因码：").Append(E(string.Join(", ", snapshot.ReasonCodes))).Append("</div>");

            if (layers != null)
            {
                html.Append("<h2>三层识别状态</h2><div class=\"grid\">");
                AddCard(html, "L1 图元层", layers.PrimitiveSnapshot.Status + " / " + layers.PrimitiveSnapshot.Primitives.Count.ToString(CultureInfo.InvariantCulture));
                AddCard(html, "L2 几何层", layers.GeometrySnapshot.Status + " / " + layers.GeometrySnapshot.Facts.Count.ToString(CultureInfo.InvariantCulture));
                AddCard(html, "L3 语义层", snapshot.Status + " / " + snapshot.Objects.Count.ToString(CultureInfo.InvariantCulture));
                html.Append("</div><p><a href=\"cad-primitives.v1.json\">图元 JSON</a> ｜ <a href=\"building-geometry.v1.json\">几何 JSON</a> ｜ <a href=\"building-semantics.raw.v1.json\">原始语义 JSON</a> ｜ <a href=\"building-semantics.v1.json\">规范语义 JSON</a></p>");
                html.Append("<div class=\"notice\">图元层记录原始对象；几何层记录形状与量测；只有语义层给出工程用途和复核结论。图元/几何已提取不等于墙、门或房间已确认。多路径未确定内外环时不提供净面积。</div>");
                if (snapshot.ReasonCodes.Contains(BuildingSemanticReasonCodes.ObservationRegionNotFrozen))
                    html.Append("<p class=\"notice\">当前人工观察区尚未冻结，第三层正向对象被门禁清空；这不代表前两层数据丢失。先核实三层扫描，再由用户指认区域，不可据此提前调留出区语义。</p>");
            }

            html.Append("<div class=\"grid\">");
            AddCard(html, "语义对象", snapshot.Metrics.SemanticObjectCount.ToString(CultureInfo.InvariantCulture));
            AddCard(html, "Accepted", snapshot.Metrics.AcceptedObjectCount.ToString(CultureInfo.InvariantCulture));
            AddCard(html, "Review", snapshot.Metrics.ReviewObjectCount.ToString(CultureInfo.InvariantCulture));
            AddCard(html, "Rejected", snapshot.Metrics.RejectedObjectCount.ToString(CultureInfo.InvariantCulture));
            AddCard(html, "关系", snapshot.Metrics.RelationCount.ToString(CultureInfo.InvariantCulture));
            AddCard(html, "顶层代理对象", snapshot.Metrics.TopLevelProxyObjectCount.ToString(CultureInfo.InvariantCulture));
            AddCard(html, "可达代理实例", snapshot.Metrics.ReachableProxyInstanceCount.ToString(CultureInfo.InvariantCulture));
            AddCard(html, "唯一代理 Handle", snapshot.Metrics.UniqueProxyHandleCount.ToString(CultureInfo.InvariantCulture));
            AddCard(html, "明确越界代理", snapshot.Metrics.IgnoredOutOfScopeProxyCount.ToString(CultureInfo.InvariantCulture));
            AddCard(html, "待复核代理", snapshot.Metrics.ReviewUnknownProxyCount.ToString(CultureInfo.InvariantCulture));
            AddCard(html, "分析耗时 ms", snapshot.Metrics.AnalysisElapsedMilliseconds.ToString(CultureInfo.InvariantCulture));
            html.Append("</div>");

            html.Append("<h2>输入与追溯</h2><table><tbody>");
            AddKeyValue(html, "图纸", snapshot.Drawing.FileName);
            AddKeyValue(html, "Drawing ID", snapshot.Drawing.DrawingId);
            AddKeyValue(html, "源图 SHA-256", snapshot.Drawing.Sha256);
            AddKeyValue(html, "项目配置", snapshot.Profile.ProjectId + " / " + snapshot.Profile.ProfileVersion);
            AddKeyValue(html, "配置 SHA-256", snapshot.Profile.Sha256);
            AddKeyValue(html, "生产 DLL SHA-256", snapshot.ProducerBinarySha256);
            AddKeyValue(html, "事实适配器", snapshot.FactProviderId);
            AddKeyValue(html, "坐标与单位", snapshot.Drawing.CoordinateSystem + " / " + snapshot.Drawing.GeometryUnits);
            AddKeyValue(html, "源文件字节不变", snapshot.Integrity.SourceBytesUnchanged + " (" + snapshot.Integrity.SourceHashBefore + " => " + snapshot.Integrity.SourceHashAfter + ")");
            AddKeyValue(html, "扫描输入", snapshot.Integrity.ScanInputMode + " / read-only=" + snapshot.Integrity.InputDatabaseReadOnly);
            AddKeyValue(html, "活动图 DBMOD 不变", snapshot.Integrity.DbmodUnchanged + " (" + snapshot.Integrity.DbmodBefore + " => " + snapshot.Integrity.DbmodAfter + ")");
            AddKeyValue(html, "活动图扫描开始 DBMOD=0", snapshot.Integrity.DbmodCleanAtStart.ToString());
            html.Append("</tbody></table>");

            List<ObservationRegion> pendingRegions = (profile?.ObservationRegions ?? new List<ObservationRegion>())
                .Where(item => item.State != ObservationRegionState.Frozen)
                .OrderBy(item => item.Code, StringComparer.Ordinal)
                .ToList();
            if (pendingRegions.Count > 0)
            {
                html.Append("<h2>人工区域门槛</h2><div class=\"notice\">以下区域尚未由用户首次校准并冻结坐标：<strong>")
                    .Append(E(string.Join("、", pendingRegions.Select(item => item.Code))))
                    .Append("</strong>。本报告不声称完成 B1-B4/G1 视觉验收，留出区不得据此调参。</div>");
            }

            html.Append("<h2>复核发现</h2><div class=\"scroll\"><table><thead><tr><th>级别</th><th>原因码</th><th>对象</th><th>Handle</th><th>说明</th></tr></thead><tbody>");
            foreach (ReviewFinding finding in snapshot.Findings)
            {
                html.Append("<tr><td><span class=\"tag ").Append(E(finding.Severity.ToString().ToLowerInvariant())).Append("\">").Append(E(finding.Severity.ToString())).Append("</span></td>");
                html.Append("<td><code>").Append(E(finding.ReasonCode)).Append("</code></td><td><code>").Append(E(finding.SemanticId)).Append("</code></td><td><code>").Append(E(finding.SourceHandle)).Append("</code></td><td>").Append(E(finding.Message)).Append("</td></tr>");
            }
            if (snapshot.Findings.Count == 0)
                html.Append("<tr><td colspan=\"5\">无复核发现。</td></tr>");
            html.Append("</tbody></table></div>");

            html.Append("<h2>语义对象</h2><div class=\"scroll\"><table><thead><tr><th>状态</th><th>类型</th><th>分类/用途</th><th>原始名称</th><th>置信度</th><th>Handle</th><th>有效图层</th><th>证据</th></tr></thead><tbody>");
            foreach (SemanticObject item in snapshot.Objects)
            {
                html.Append("<tr><td><span class=\"tag ").Append(E(item.Status.ToString().ToLowerInvariant())).Append("\">").Append(E(item.Status.ToString())).Append("</span></td>");
                html.Append("<td>").Append(E(item.Type.ToString())).Append("</td><td>").Append(E(string.Join(" / ", new[] { item.Classification, item.UseCode }.Where(value => !string.IsNullOrWhiteSpace(value))))).Append("</td>");
                html.Append("<td>").Append(E(item.RawLabel)).Append("</td><td>").Append(item.Confidence.ToString("0.000", CultureInfo.InvariantCulture)).Append("</td>");
                html.Append("<td><code>").Append(E(item.Source.Handle)).Append("</code></td><td><code>").Append(E(item.Source.EffectiveLayer)).Append("</code></td><td>");
                html.Append(E(string.Join("；", item.Evidence.Select(evidence => evidence.Code + "=" + evidence.Value)))).Append("</td></tr>");
            }
            html.Append("</tbody></table></div>");

            html.Append("<h2>代理对象核账</h2><div class=\"scroll\"><table><thead><tr><th>归类</th><th>Handle</th><th>DXF/Class</th><th>有效图层</th><th>原因码</th></tr></thead><tbody>");
            foreach (ProxyLedgerEntry entry in snapshot.ProxyLedger)
            {
                html.Append("<tr><td>").Append(E(entry.Disposition.ToString())).Append("</td><td><code>").Append(E(entry.Handle)).Append("</code></td>");
                html.Append("<td><code>").Append(E(entry.OriginalDxfName + " / " + entry.OriginalClassName)).Append("</code></td><td><code>").Append(E(entry.EffectiveLayer)).Append("</code></td><td><code>").Append(E(entry.ReasonCode)).Append("</code></td></tr>");
            }
            html.Append("</tbody></table></div>");

            html.Append("<p class=\"muted\">本报告只表达只读识图结果；Review/Rejected 不得作为自动照明、火警或桥架布置的确定输入。</p>");
            html.Append("</main></body></html>");
            return html.ToString();
        }

        private static void AddCard(StringBuilder html, string label, string value)
        {
            html.Append("<div class=\"card\"><div class=\"muted\">").Append(E(label)).Append("</div><div class=\"value\">").Append(E(value)).Append("</div></div>");
        }

        private static void AddKeyValue(StringBuilder html, string key, string value)
        {
            html.Append("<tr><th>").Append(E(key)).Append("</th><td><code>").Append(E(value)).Append("</code></td></tr>");
        }

        private static string E(string value)
        {
            return WebUtility.HtmlEncode(value ?? string.Empty);
        }
    }
}
