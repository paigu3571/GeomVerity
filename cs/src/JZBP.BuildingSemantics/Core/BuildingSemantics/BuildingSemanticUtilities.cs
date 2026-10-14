// SPDX-License-Identifier: MPL-2.0
// Copyright (c) 2026 张田; 著作权人、原作者及维护者：张田；其他贡献者和第三方保留各自权利。
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

namespace JZBP.BuildingSemantics.Core
{
    public static class ProjectProfileValidator
    {
        public static ProfileValidationResult Validate(ProjectProfile? profile)
        {
            var result = new ProfileValidationResult();
            if (profile == null)
            {
                Add(result, BuildingSemanticReasonCodes.ProfileInvalid, "项目配置为空。");
                return result;
            }

            if (!string.Equals(profile.SchemaVersion, BuildingSemanticSchema.ProfileV1, StringComparison.Ordinal))
                Add(result, BuildingSemanticReasonCodes.ProfileInvalid, "不支持的项目配置 schema_version。");
            if (string.IsNullOrWhiteSpace(profile.ProjectId))
                Add(result, BuildingSemanticReasonCodes.ProfileInvalid, "project_id 不能为空。");
            if (!string.Equals(profile.Units, "mm", StringComparison.OrdinalIgnoreCase)
                || Math.Abs(profile.UnitScaleToMillimeters - 1.0) > 1e-9)
            {
                Add(result, BuildingSemanticReasonCodes.UnitProfileRequired, "首版必须由 ProjectProfile 明确指定毫米，且换算系数为 1.0。");
            }

            if (profile.AdapterPriority == null
                || profile.AdapterPriority.Count == 0
                || !string.Equals(profile.AdapterPriority[0], "T20", StringComparison.OrdinalIgnoreCase))
            {
                Add(result, BuildingSemanticReasonCodes.ProfileInvalid, "adapter_priority 第一项必须是 T20。");
            }

            if (profile.Thresholds == null
                || profile.Thresholds.AcceptedConfidence < 0.5
                || profile.Thresholds.AcceptedConfidence > 1.0
                || profile.Thresholds.ReviewConfidence < 0.0
                || profile.Thresholds.ReviewConfidence >= profile.Thresholds.AcceptedConfidence)
            {
                Add(result, BuildingSemanticReasonCodes.ProfileInvalid, "置信度阈值无效。");
            }

            foreach (DrawingProfileRule drawing in profile.Drawings ?? new List<DrawingProfileRule>())
            {
                if (string.IsNullOrWhiteSpace(drawing.DrawingId)
                    || !IsSha256(drawing.Sha256))
                {
                    Add(result, BuildingSemanticReasonCodes.ProfileInvalid, "drawing 条目必须具有 drawing_id 和 64 位 SHA-256。");
                }
            }

            var regionCodes = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (ObservationRegion region in profile.ObservationRegions ?? new List<ObservationRegion>())
            {
                if (string.IsNullOrWhiteSpace(region.Code) || !regionCodes.Add(region.Code))
                    Add(result, BuildingSemanticReasonCodes.ProfileInvalid, "观察区域 code 不能为空或重复。");

                if (region.State == ObservationRegionState.Frozen)
                {
                    if (!IsSha256(region.DrawingHash)
                        || region.PolygonWcsMillimeters == null
                        || region.PolygonWcsMillimeters.Count < 3
                        || string.IsNullOrWhiteSpace(region.FrozenBy)
                        || string.IsNullOrWhiteSpace(region.FrozenAtUtc))
                    {
                        Add(result, BuildingSemanticReasonCodes.ProfileInvalid, "冻结观察区必须包含图纸哈希、至少三个坐标点和冻结审计信息。");
                    }
                }
                else if (region.PolygonWcsMillimeters != null && region.PolygonWcsMillimeters.Count > 0)
                {
                    Add(result, BuildingSemanticReasonCodes.ProfileInvalid, "未冻结观察区不得预填坐标，避免实施者自行选择区域。");
                }
            }

            if (profile.RuleState == SemanticRuleState.Frozen
                && (profile.ObservationRegions ?? new List<ObservationRegion>()).Count > 0)
            {
                if (string.IsNullOrWhiteSpace(profile.RulesFrozenBy)
                    || string.IsNullOrWhiteSpace(profile.RulesFrozenAtUtc))
                {
                    Add(result, BuildingSemanticReasonCodes.ProfileInvalid, "规则冻结状态必须包含 rules_frozen_by 和 rules_frozen_at_utc 审计信息。");
                }

                List<string> pending = (profile.ObservationRegions ?? new List<ObservationRegion>())
                    .Where(region => region.State != ObservationRegionState.Frozen)
                    .Select(region => region.Code)
                    .OrderBy(code => code, StringComparer.Ordinal)
                    .ToList();
                if (pending.Count > 0)
                    Add(result, BuildingSemanticReasonCodes.ObservationRegionNotFrozen, "规则冻结前必须先冻结全部观察区坐标: " + string.Join(",", pending));
            }

            foreach (LayerNormalizationRule rule in profile.LayerNormalization ?? new List<LayerNormalizationRule>())
            {
                try
                {
                    RegexOptions options = rule.IgnoreCase ? RegexOptions.IgnoreCase : RegexOptions.None;
                    _ = new Regex(rule.Pattern ?? string.Empty, options | RegexOptions.CultureInvariant);
                }
                catch (ArgumentException ex)
                {
                    Add(result, BuildingSemanticReasonCodes.ProfileInvalid, "图层规范化正则无效 " + rule.Id + ": " + ex.Message);
                }
            }

            foreach (RoomUseRule rule in profile.RoomUseDictionary ?? new List<RoomUseRule>())
            {
                if (string.IsNullOrWhiteSpace(rule.UseCode)
                    || !Regex.IsMatch(rule.UseCode, "^[A-Z0-9_]+$", RegexOptions.CultureInvariant))
                {
                    Add(result, BuildingSemanticReasonCodes.ProfileInvalid,
                        "房间用途 use_code 必须为大写稳定码。");
                }
                if (!Enum.TryParse(rule.SemanticType, true, out SemanticObjectType _))
                {
                    Add(result, BuildingSemanticReasonCodes.ProfileInvalid,
                        "房间用途 " + rule.UseCode + " 的 semantic_type 无效。");
                }
                if (string.IsNullOrWhiteSpace(rule.RulePack)
                    || !Regex.IsMatch(rule.RulePack, "^[a-z0-9_]+$", RegexOptions.CultureInvariant))
                {
                    Add(result, BuildingSemanticReasonCodes.ProfileInvalid,
                        "房间用途 " + rule.UseCode + " 的 rule_pack 必须为小写稳定码。");
                }
                if (rule.Keywords == null
                    || rule.Keywords.Count == 0
                    || rule.Keywords.Any(string.IsNullOrWhiteSpace))
                {
                    Add(result, BuildingSemanticReasonCodes.ProfileInvalid,
                        "房间用途 " + rule.UseCode + " 必须包含非空关键词。");
                }
                if ((rule.ExcludedKeywords ?? new List<string>()).Any(string.IsNullOrWhiteSpace))
                {
                    Add(result, BuildingSemanticReasonCodes.ProfileInvalid,
                        "房间用途 " + rule.UseCode + " 的 excluded_keywords 不得包含空值。");
                }
            }

            var semanticRuleIds = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (GeometrySemanticRule rule in profile.GeometrySemanticRules ?? new List<GeometrySemanticRule>())
            {
                if (string.IsNullOrWhiteSpace(rule.Id) || !semanticRuleIds.Add(rule.Id))
                    Add(result, BuildingSemanticReasonCodes.ProfileInvalid, "几何语义规则 id 不能为空或重复。");

                if (!Enum.TryParse(rule.SemanticType, true, out CadFactKind semanticKind)
                    || !IsPromotableSemanticKind(semanticKind))
                {
                    Add(result, BuildingSemanticReasonCodes.ProfileInvalid,
                        "几何语义规则 " + rule.Id + " 的 semantic_type 不是可提升的建筑对象类型。");
                }

                if (rule.NormalizedLayers == null
                    || rule.NormalizedLayers.Count == 0
                    || rule.NormalizedLayers.Any(string.IsNullOrWhiteSpace))
                {
                    Add(result, BuildingSemanticReasonCodes.ProfileInvalid,
                        "几何语义规则 " + rule.Id + " 必须给出非空 normalized_layers。");
                }

                if (rule.FeatureKinds == null
                    || rule.FeatureKinds.Count == 0
                    || rule.FeatureKinds.Contains(GeometryFeatureKind.None))
                {
                    Add(result, BuildingSemanticReasonCodes.ProfileInvalid,
                        "几何语义规则 " + rule.Id + " 必须给出可计算的 feature_kinds。");
                }

                if ((rule.RequiredProperties ?? new Dictionary<string, string>())
                    .Any(item => string.IsNullOrWhiteSpace(item.Key) || string.IsNullOrWhiteSpace(item.Value)))
                {
                    Add(result, BuildingSemanticReasonCodes.ProfileInvalid,
                        "几何语义规则 " + rule.Id + " 的 required_properties 不得包含空键或空值。");
                }

                if (!IsFinite(rule.MinimumAreaSquareMillimeters)
                    || !IsFinite(rule.MaximumAreaSquareMillimeters)
                    || rule.MinimumAreaSquareMillimeters < 0
                    || rule.MaximumAreaSquareMillimeters <= rule.MinimumAreaSquareMillimeters)
                {
                    Add(result, BuildingSemanticReasonCodes.ProfileInvalid,
                        "几何语义规则 " + rule.Id + " 的面积范围无效。");
                }

                if (!IsFinite(rule.Confidence)
                    || rule.Confidence < (profile.Thresholds?.ReviewConfidence ?? 0.0)
                    || rule.Confidence > 1.0)
                {
                    Add(result, BuildingSemanticReasonCodes.ProfileInvalid,
                        "几何语义规则 " + rule.Id + " 的 confidence 无效。");
                }

                if (!string.IsNullOrWhiteSpace(rule.Classification)
                    && (semanticKind != CadFactKind.Wall
                        || !Enum.TryParse(rule.Classification, true, out WallClassification _)))
                {
                    Add(result, BuildingSemanticReasonCodes.ProfileInvalid,
                        "几何语义规则 " + rule.Id + " 的 classification 不是有效墙分类。");
                }

                bool usesRoomLabel = rule.LabelMode == GeometrySemanticLabelMode.UniqueContainedRoomUse
                                     || rule.LabelMode == GeometrySemanticLabelMode.UniqueContainedRoomUseAndArea;
                if (usesRoomLabel)
                {
                    if (semanticKind != CadFactKind.Space)
                    {
                        Add(result, BuildingSemanticReasonCodes.ProfileInvalid,
                            "几何语义规则 " + rule.Id + " 的房间文字关联模式只能用于 Space。");
                    }
                    if (rule.LabelLayers == null
                        || rule.LabelLayers.Count == 0
                        || rule.LabelLayers.Any(string.IsNullOrWhiteSpace))
                    {
                        Add(result, BuildingSemanticReasonCodes.ProfileInvalid,
                            "几何语义规则 " + rule.Id + " 必须给出房间名称文字图层。");
                    }
                }

                if (rule.LabelMode == GeometrySemanticLabelMode.UniqueContainedRoomUseAndArea)
                {
                    if (rule.AreaLabelLayers == null
                        || rule.AreaLabelLayers.Count == 0
                        || rule.AreaLabelLayers.Any(string.IsNullOrWhiteSpace))
                    {
                        Add(result, BuildingSemanticReasonCodes.ProfileInvalid,
                            "几何语义规则 " + rule.Id + " 必须给出房间面积文字图层。");
                    }
                    if (!IsFinite(rule.MaximumAreaLabelRelativeDifference)
                        || rule.MaximumAreaLabelRelativeDifference <= 0
                        || rule.MaximumAreaLabelRelativeDifference > 0.25)
                    {
                        Add(result, BuildingSemanticReasonCodes.ProfileInvalid,
                            "几何语义规则 " + rule.Id + " 的面积文字相对误差必须在 (0, 0.25] 内。");
                    }
                }

                if (rule.LabelMode == GeometrySemanticLabelMode.UniqueContainedRoomUse
                    && ((rule.AreaLabelLayers?.Count ?? 0) != 0
                        || rule.MaximumAreaLabelRelativeDifference != 0))
                {
                    Add(result, BuildingSemanticReasonCodes.ProfileInvalid,
                        "几何语义规则 " + rule.Id + " 的纯房名模式不得配置面积文字条件。");
                }
            }

            result.IsValid = result.ReasonCodes.Count == 0;
            return result;
        }

        private static bool IsPromotableSemanticKind(CadFactKind kind)
        {
            return kind == CadFactKind.Storey
                   || kind == CadFactKind.Space
                   || kind == CadFactKind.Wall
                   || kind == CadFactKind.Column
                   || kind == CadFactKind.Opening
                   || kind == CadFactKind.Door
                   || kind == CadFactKind.Window
                   || kind == CadFactKind.Shaft
                   || kind == CadFactKind.Stair
                   || kind == CadFactKind.Ramp
                   || kind == CadFactKind.Zone;
        }

        private static bool IsFinite(double value)
        {
            return !double.IsNaN(value) && !double.IsInfinity(value);
        }

        public static List<string> ValidateHoldoutFreeze(ProjectProfile? profile, string drawingHash)
        {
            return (profile?.ObservationRegions ?? new List<ObservationRegion>())
                .Where(region => region.Role == ObservationRegionRole.Holdout)
                .Where(region => string.Equals(region.DrawingHash, drawingHash, StringComparison.OrdinalIgnoreCase)
                                 || string.IsNullOrWhiteSpace(region.DrawingHash))
                .Where(region => region.State != ObservationRegionState.Frozen)
                .Select(region => region.Code)
                .OrderBy(code => code, StringComparer.Ordinal)
                .ToList();
        }

        public static DrawingProfileRule? FindDrawing(ProjectProfile? profile, string drawingHash)
        {
            DrawingProfileRule? exact = FindExactDrawing(profile, drawingHash);
            if (exact != null || profile?.AllowUnlistedDrawings != true || !IsSha256(drawingHash))
                return exact;

            return new DrawingProfileRule
            {
                DrawingId = "generic-" + drawingHash.Substring(0, 12).ToLowerInvariant(),
                Sha256 = drawingHash,
                Role = GenericUnlistedReviewRole
            };
        }

        public static DrawingProfileRule? FindExactDrawing(ProjectProfile? profile, string drawingHash)
        {
            return (profile?.Drawings ?? new List<DrawingProfileRule>())
                .FirstOrDefault(item => string.Equals(item.Sha256, drawingHash, StringComparison.OrdinalIgnoreCase));
        }

        public static bool IsGenericReviewDrawing(DrawingProfileRule? drawing)
        {
            return string.Equals(drawing?.Role, GenericUnlistedReviewRole, StringComparison.Ordinal);
        }

        /// <summary>
        /// 已登记图纸沿用配置中的项目身份；未登记图纸只借用通用识别规则，
        /// 项目身份按源 DWG 哈希自动隔离。这样无需预登记也不会写回规则模板项目。
        /// </summary>
        public static string ResolveRuntimeProjectId(
            ProjectProfile? profile,
            DrawingProfileRule? drawing,
            string drawingHash)
        {
            if (IsGenericReviewDrawing(drawing) && IsSha256(drawingHash))
                return "auto-" + drawingHash.Substring(0, 12).ToLowerInvariant();
            return profile?.ProjectId ?? string.Empty;
        }

        internal const string GenericUnlistedReviewRole = "generic_unlisted_review";

        private static void Add(ProfileValidationResult result, string reasonCode, string message)
        {
            if (!result.ReasonCodes.Contains(reasonCode, StringComparer.Ordinal))
                result.ReasonCodes.Add(reasonCode);
            result.Messages.Add(message);
        }

        private static bool IsSha256(string value)
        {
            if (string.IsNullOrWhiteSpace(value) || value.Length != 64)
                return false;
            return value.All(character => Uri.IsHexDigit(character));
        }
    }

    internal static class ProjectProfileDiscovery
    {
        internal static LoadedProjectProfile RequireMatchingProfile(string path, string drawingHash)
        {
            LoadedProjectProfile loaded = BuildingSemanticJson.LoadProfile(path);
            if (ProjectProfileValidator.FindDrawing(loaded.Profile, drawingHash) == null)
                throw new InvalidDataException(BuildingSemanticReasonCodes.DrawingHashMismatch + ": 显式 ProjectProfile 不包含当前图纸哈希，也未允许通用未登记图纸。");
            return loaded;
        }

        internal static LoadedProjectProfile? ResolveExistingThenInstalled(
            IEnumerable<string> existingRoots,
            string? installedProfilesRoot,
            string drawingHash)
        {
            LoadedProjectProfile? existing = ResolveAutomatic(existingRoots, drawingHash);
            if (existing != null || string.IsNullOrWhiteSpace(installedProfilesRoot))
                return existing;
            return ResolveAutomatic(new[] { installedProfilesRoot! }, drawingHash);
        }

        internal static string? FindInstalledProfilesRoot(string assemblyPath)
        {
            if (string.IsNullOrWhiteSpace(assemblyPath))
                return null;
            DirectoryInfo? ancestor = new FileInfo(Path.GetFullPath(assemblyPath)).Directory;
            for (; ancestor != null; ancestor = ancestor.Parent)
            {
                string candidate = Path.Combine(ancestor.FullName, "profiles");
                if (Directory.Exists(candidate))
                    return candidate;
            }
            return null;
        }

        private static LoadedProjectProfile? ResolveAutomatic(IEnumerable<string> roots, string drawingHash)
        {
            var exactMatches = new List<LoadedProjectProfile>();
            var genericMatches = new List<LoadedProjectProfile>();
            foreach (string root in roots.Where(Directory.Exists).Distinct(StringComparer.OrdinalIgnoreCase))
            {
                foreach (string path in Directory.EnumerateFiles(root, "*.json", SearchOption.TopDirectoryOnly)
                             .OrderBy(value => value, StringComparer.OrdinalIgnoreCase))
                {
                    try
                    {
                        LoadedProjectProfile candidate = BuildingSemanticJson.LoadProfile(path);
                        DrawingProfileRule? rule = ProjectProfileValidator.FindDrawing(candidate.Profile, drawingHash);
                        if (rule == null)
                            continue;
                        if (ProjectProfileValidator.IsGenericReviewDrawing(rule))
                            genericMatches.Add(candidate);
                        else
                            exactMatches.Add(candidate);
                    }
                    catch
                    {
                        // 非本 schema 或无效配置不参与自动匹配；显式路径会直接报告错误。
                    }
                }
            }
            if (exactMatches.Count == 1)
                return exactMatches[0];
            if (exactMatches.Count > 1)
                throw new InvalidDataException("多个 ProjectProfile 同时匹配当前图纸，请用 JZBP_PROFILE 显式指定。");
            if (genericMatches.Count == 1)
                return genericMatches[0];
            if (genericMatches.Count > 1)
                throw new InvalidDataException("多个 ProjectProfile 允许通用未登记图纸，请用 JZBP_PROFILE 显式指定一个。");
            return null;
        }
    }

    /// <summary>
    /// 将项目身份映射到磁盘产物目录。配置的 output_root 属于配置项目本身；
    /// 自动项目空间使用其同级目录，避免通用图纸写入 001/002 等正式项目目录。
    /// </summary>
    public static class BuildingSemanticProjectScope
    {
        public static string ResolveOutputDirectory(
            ProjectProfile profile,
            string drawingPath,
            string drawingId,
            string runtimeProjectId)
        {
            if (profile == null)
                throw new ArgumentNullException(nameof(profile));

            bool configuredOutputRoot = !string.IsNullOrWhiteSpace(profile.OutputRoot);
            string root = !configuredOutputRoot
                ? Path.Combine(Path.GetDirectoryName(drawingPath) ?? string.Empty, "building-semantics-artifacts")
                : Path.GetFullPath(Environment.ExpandEnvironmentVariables(profile.OutputRoot));
            if (!string.Equals(runtimeProjectId, profile.ProjectId, StringComparison.Ordinal))
            {
                if (configuredOutputRoot)
                    root = Directory.GetParent(root)?.FullName ?? root;
                root = Path.Combine(root, MakeSafeFileName(runtimeProjectId));
            }
            return Path.Combine(root, MakeSafeFileName(drawingId));
        }

        private static string MakeSafeFileName(string value)
        {
            string safe = value ?? string.Empty;
            foreach (char invalid in Path.GetInvalidFileNameChars())
                safe = safe.Replace(invalid, '_');
            return string.IsNullOrWhiteSpace(safe) ? "drawing" : safe;
        }
    }

    /// <summary>
    /// 与 AutoCAD 类型无关的 T20 对象判定策略，供适配器和离线契约测试共同使用。
    /// 未命中标注/明确越界白名单的 T20 代理默认要求解释器，禁止未知代理绕过失败闭合。
    /// </summary>
    public static class T20ObjectPolicy
    {
        public static bool IsT20(string dxfName, string className, string runtimeTypeName = "")
        {
            string value = SearchText(dxfName, className, runtimeTypeName);
            return value.Contains("TCH_") || value.Contains("TDB") || value.Contains("TANGENT") || value.Contains("天正");
        }

        public static CadFactKind Classify(string dxfName, string className, string runtimeTypeName = "")
        {
            string value = SearchText(dxfName, className, runtimeTypeName);
            if (ContainsAny(value, "TDBTEXT", "TCH_TEXT", "TDBMTEXT", "TCH_MTEXT")) return CadFactKind.Text;
            if (ContainsAny(value, "TDBCURTAINWALL", "TCH_CURTAIN_WALL", "TDBWALL", "TCH_WALL")) return CadFactKind.Wall;
            if (ContainsAny(value, "TDBOPENING", "TCH_OPENING")) return CadFactKind.Opening;
            if (ContainsAny(value, "TDBSPACE", "TCH_SPACE")) return CadFactKind.Space;
            if (ContainsAny(value, "TDBCOLUMN", "TCH_COLUMN")) return CadFactKind.Column;
            if (ContainsAny(value, "TDBDOOR", "TCH_DOOR")) return CadFactKind.Door;
            if (ContainsAny(value, "TDBWINDOW", "TCH_WINDOW")) return CadFactKind.Window;
            if (ContainsAny(value, "TDBCROSSSTAIR", "TCH_CROSSSTAIR", "TDBSTAIR", "TDBLINESTAIR", "TDBMULTISTAIR", "TCH_STAIR", "TCH_LINESTAIR", "TCH_MULTISTAIR")) return CadFactKind.Stair;
            if (ContainsAny(value, "TDBRAMP", "TCH_RAMP")) return CadFactKind.Ramp;
            if (ContainsAny(value, "TDBSHAFT", "TCH_SHAFT")) return CadFactKind.Shaft;
            if (ContainsAny(value, "TDBSTOREY", "TCH_STOREY")) return CadFactKind.Storey;
            if (ContainsAny(value, "TDBFIREZONE", "TCH_FIRE_ZONE", "TDBDEFENSEZONE", "TCH_DEFENSE_ZONE")) return CadFactKind.Zone;
            return CadFactKind.Unknown;
        }

        public static bool IsAnnotation(string dxfName, string className, string runtimeTypeName = "")
        {
            string value = SearchText(dxfName, className, runtimeTypeName);
            return ContainsAny(value,
                "TEXT", "MTEXT", "DIM", "DIMENSION", "ANNO", "AXIS", "TAG", "SYMB", "SYMBOL",
                "INDEX", "LEADER", "COORD", "ELEVATION", "RUPTURE", "PROMPTMARK", "DRAWINGNAME",
                "POLYPATHARRAY", "PATH_ARRAY", "SHEET");
        }

        public static bool IsExplicitlyOutOfScope(string dxfName, string className, string runtimeTypeName = "")
        {
            string value = SearchText(dxfName, className, runtimeTypeName);
            return ContainsAny(value,
                "TCH_PIPEFITTING", "TDBPIPEFITTING", "TCH_PIPEVALVE", "TDBPIPEVALVE",
                "TCH_PIPE", "TDBPIPE", "TCH_EQUIPMENT", "TDBEQUIPMENT",
                "TCH_HANDRAIL", "TDBHANDRAIL", "TCH_SLAB", "TDBSLAB");
        }

        public static bool ProxyRequiresInterpreter(string dxfName, string className, string runtimeTypeName = "")
        {
            return IsT20(dxfName, className, runtimeTypeName)
                   && !IsAnnotation(dxfName, className, runtimeTypeName)
                   && !IsExplicitlyOutOfScope(dxfName, className, runtimeTypeName);
        }

        private static string SearchText(params string[] values)
        {
            return string.Join("|", values ?? Array.Empty<string>()).ToUpperInvariant();
        }

        private static bool ContainsAny(string value, params string[] terms)
        {
            return terms.Any(value.Contains);
        }
    }

    /// <summary>
    /// T20 墙在内存分解后常同时返回精确墙边线和仅用于显示的 Hatch。
    /// 只有所有非 Hatch 子对象都已精确读取，且至少存在两条精确曲线边界时，
    /// 才允许省略不能再次分解的辅助 Hatch；其余情况继续失败闭合。
    /// </summary>
    public static class T20WallGeometryPolicy
    {
        public static bool CanOmitAuxiliaryHatch(
            int totalEntityChildren,
            int exactEntityChildren,
            int exactCurveChildren,
            int auxiliaryHatchChildren,
            bool hasOtherFailure)
        {
            return !hasOtherFailure
                   && totalEntityChildren > 0
                   && auxiliaryHatchChildren > 0
                   && exactCurveChildren >= 2
                   && exactEntityChildren + auxiliaryHatchChildren == totalEntityChildren;
        }
    }

    public static class SemanticSensitivityPolicy
    {
        public static bool HasFireEvidence(IDictionary<string, string> properties)
        {
            return HasPositiveProperty(properties, "IsFireProof")
                   || HasPositiveProperty(properties, "FireRating")
                   || ValuesContain(properties, "防火", "消防", "FIRE");
        }

        public static bool HasCivilDefenseEvidence(IDictionary<string, string> properties)
        {
            return HasPositiveProperty(properties, "CivilDefense")
                   || ValuesContain(properties, "人防", "防护", "CIVILDEFENSE", "CIVIL_DEFENSE");
        }

        public static bool HasPositiveProperty(IDictionary<string, string> properties, string name)
        {
            if (properties == null)
                return false;
            KeyValuePair<string, string> match = properties
                .FirstOrDefault(item => string.Equals(item.Key, name, StringComparison.OrdinalIgnoreCase));
            if (string.IsNullOrWhiteSpace(match.Key) || string.IsNullOrWhiteSpace(match.Value))
                return false;

            string normalized = match.Value.Trim().ToUpperInvariant();
            if (normalized == "FALSE" || normalized == "NO" || normalized == "N" || normalized == "否"
                || normalized == "无" || normalized == "NONE" || normalized == "NULL")
                return false;
            if (double.TryParse(normalized, NumberStyles.Float, CultureInfo.InvariantCulture, out double number))
                return number > 0;
            return true;
        }

        private static bool ValuesContain(IDictionary<string, string> properties, params string[] terms)
        {
            string value = string.Join("|", (properties ?? new Dictionary<string, string>()).Values).ToUpperInvariant();
            return terms.Any(term => value.Contains(term.ToUpperInvariant()));
        }
    }

    public static class LayerNameNormalizer
    {
        public static string Normalize(string layerName, ProjectProfile? profile)
        {
            string value = layerName ?? string.Empty;
            foreach (LayerNormalizationRule rule in profile?.LayerNormalization ?? new List<LayerNormalizationRule>())
            {
                RegexOptions options = RegexOptions.CultureInvariant;
                if (rule.IgnoreCase)
                    options |= RegexOptions.IgnoreCase;
                value = Regex.Replace(value, rule.Pattern ?? string.Empty, rule.Replacement ?? string.Empty, options);
            }

            return value.Trim();
        }
    }

    public static class RoomUseClassifier
    {
        public static RoomUseMatch Match(string rawLabel, ProjectProfile? profile)
        {
            string normalized = Normalize(rawLabel);
            foreach (RoomUseRule rule in profile?.RoomUseDictionary ?? new List<RoomUseRule>())
            {
                bool excluded = (rule.ExcludedKeywords ?? new List<string>())
                    .Select(Normalize)
                    .Where(value => !string.IsNullOrWhiteSpace(value))
                    .Any(value => normalized.IndexOf(value, StringComparison.OrdinalIgnoreCase) >= 0);
                if (excluded)
                    continue;

                foreach (string keyword in rule.Keywords ?? new List<string>())
                {
                    if (normalized.IndexOf(Normalize(keyword), StringComparison.OrdinalIgnoreCase) < 0)
                        continue;

                    SemanticObjectType type = SemanticObjectType.Space;
                    if (!Enum.TryParse(rule.SemanticType, true, out type))
                        type = SemanticObjectType.Space;
                    return new RoomUseMatch
                    {
                        IsMatch = true,
                        UseCode = rule.UseCode ?? string.Empty,
                        SemanticType = type,
                        Keyword = keyword ?? string.Empty,
                        RulePack = string.IsNullOrWhiteSpace(rule.RulePack)
                            ? BuildingSemanticRulePacks.Common
                            : rule.RulePack
                    };
                }
            }

            return new RoomUseMatch
            {
                IsMatch = false,
                UseCode = "UNKNOWN",
                SemanticType = SemanticObjectType.Space
            };
        }

        public static string Normalize(string value)
        {
            if (string.IsNullOrWhiteSpace(value))
                return string.Empty;
            return value
                .Replace("\\P", " ")
                .Replace("\r", " ")
                .Replace("\n", " ")
                .Replace("{", string.Empty)
                .Replace("}", string.Empty)
                .Replace(" ", string.Empty)
                .Trim()
                .ToUpperInvariant();
        }
    }

    public sealed class RoomUseMatch
    {
        public bool IsMatch { get; set; }
        public string UseCode { get; set; } = string.Empty;
        public SemanticObjectType SemanticType { get; set; }
        public string Keyword { get; set; } = string.Empty;
        public string RulePack { get; set; } = string.Empty;
    }

    /// <summary>
    /// T20 交叉楼梯可能把仅用于标注方向的 TCH_ARROW 作为顶层子对象返回。
    /// 只有根对象明确为 TCH_CROSSSTAIR、其余子对象均已精确读取且至少存在
    /// 两个精确几何子对象时，才允许省略这些箭头；任何其他失败继续失败闭合。
    /// </summary>
    public static class T20CrossStairGeometryPolicy
    {
        public static bool IsCrossStair(string dxfName, string className)
        {
            return string.Equals(dxfName, "TCH_CROSSSTAIR", StringComparison.OrdinalIgnoreCase)
                   && string.Equals(className, "TDbCrossStair", StringComparison.OrdinalIgnoreCase);
        }

        public static bool IsAuxiliaryArrow(string dxfName, string className)
        {
            return string.Equals(dxfName, "TCH_ARROW", StringComparison.OrdinalIgnoreCase)
                   && string.Equals(className, "TDbSymbArrow", StringComparison.OrdinalIgnoreCase);
        }

        public static bool CanOmitAuxiliaryArrows(
            int totalEntityChildren,
            int exactEntityChildren,
            int auxiliaryArrowChildren,
            bool hasOtherFailure)
        {
            return !hasOtherFailure
                   && totalEntityChildren > 0
                   && auxiliaryArrowChildren > 0
                   && exactEntityChildren >= 2
                   && exactEntityChildren + auxiliaryArrowChildren == totalEntityChildren;
        }
    }

    public static class SemanticGeometryAlgorithms
    {
        public static bool IsUsable(SemanticGeometry? geometry, bool requireExact)
        {
            if (geometry == null || geometry.Kind == GeometryKind.None || !geometry.Bounds.IsValid)
                return false;
            if (requireExact && !geometry.IsExact)
                return false;
            return geometry.Paths != null
                   && geometry.Paths.Any(path => path != null && path.Count > 0 && path.All(IsFinite));
        }

        public static SemanticBounds CalculateBounds(IEnumerable<IEnumerable<SemanticPoint>> paths)
        {
            var points = (paths ?? Enumerable.Empty<IEnumerable<SemanticPoint>>())
                .Where(path => path != null)
                .SelectMany(path => path)
                .Where(IsFinite)
                .ToList();
            if (points.Count == 0)
                return new SemanticBounds { IsValid = false };

            return new SemanticBounds
            {
                MinX = points.Min(point => point.X),
                MinY = points.Min(point => point.Y),
                MinZ = points.Min(point => point.Z),
                MaxX = points.Max(point => point.X),
                MaxY = points.Max(point => point.Y),
                MaxZ = points.Max(point => point.Z),
                IsValid = true
            };
        }

        public static SemanticPoint RepresentativePoint(SemanticGeometry? geometry)
        {
            if (geometry?.Bounds == null || !geometry.Bounds.IsValid)
                return new SemanticPoint();
            return new SemanticPoint(
                (geometry.Bounds.MinX + geometry.Bounds.MaxX) * 0.5,
                (geometry.Bounds.MinY + geometry.Bounds.MaxY) * 0.5,
                (geometry.Bounds.MinZ + geometry.Bounds.MaxZ) * 0.5);
        }

        public static bool ContainsPoint(SemanticGeometry? geometry, SemanticPoint? point)
        {
            if (geometry == null || point == null || geometry.Paths == null)
                return false;
            List<SemanticPoint>? polygon = geometry.Paths.FirstOrDefault(path => path != null && path.Count >= 3);
            if (polygon == null)
                return false;

            bool inside = false;
            int previous = polygon.Count - 1;
            for (int current = 0; current < polygon.Count; current++)
            {
                SemanticPoint a = polygon[current];
                SemanticPoint b = polygon[previous];
                bool crosses = (a.Y > point.Y) != (b.Y > point.Y);
                if (crosses)
                {
                    double intersection = (b.X - a.X) * (point.Y - a.Y) / (b.Y - a.Y) + a.X;
                    if (point.X < intersection)
                        inside = !inside;
                }
                previous = current;
            }

            return inside;
        }

        public static bool BoundsIntersect(SemanticGeometry? first, SemanticGeometry? second, double expansion)
        {
            if (first?.Bounds == null || second?.Bounds == null
                || !first.Bounds.IsValid || !second.Bounds.IsValid)
                return false;

            return first.Bounds.MinX - expansion <= second.Bounds.MaxX
                   && first.Bounds.MaxX + expansion >= second.Bounds.MinX
                   && first.Bounds.MinY - expansion <= second.Bounds.MaxY
                   && first.Bounds.MaxY + expansion >= second.Bounds.MinY;
        }

        public static bool Intersects2D(SemanticGeometry? first, SemanticGeometry? second)
        {
            if (!BoundsIntersect(first, second, 0)
                || first?.Paths == null
                || second?.Paths == null)
            {
                return false;
            }

            List<SemanticPoint> firstPoints = first.Paths
                .Where(path => path != null)
                .SelectMany(path => path)
                .Where(IsFinite)
                .ToList();
            List<SemanticPoint> secondPoints = second.Paths
                .Where(path => path != null)
                .SelectMany(path => path)
                .Where(IsFinite)
                .ToList();
            if (firstPoints.Any(point => ContainsPoint(second, point))
                || secondPoints.Any(point => ContainsPoint(first, point)))
            {
                return true;
            }

            List<(SemanticPoint Start, SemanticPoint End)> firstSegments = BuildSegments(first);
            List<(SemanticPoint Start, SemanticPoint End)> secondSegments = BuildSegments(second);
            return firstSegments.Any(a => secondSegments.Any(b => SegmentsIntersect(a.Start, a.End, b.Start, b.End)));
        }

        private static List<(SemanticPoint Start, SemanticPoint End)> BuildSegments(SemanticGeometry geometry)
        {
            var result = new List<(SemanticPoint Start, SemanticPoint End)>();
            foreach (List<SemanticPoint> path in geometry.Paths ?? new List<List<SemanticPoint>>())
            {
                List<SemanticPoint> points = (path ?? new List<SemanticPoint>()).Where(IsFinite).ToList();
                for (int index = 1; index < points.Count; index++)
                    result.Add((points[index - 1], points[index]));
                if (geometry.IsClosed && points.Count >= 3 && !SamePoint2D(points[0], points[points.Count - 1]))
                    result.Add((points[points.Count - 1], points[0]));
            }
            return result;
        }

        private static bool SegmentsIntersect(
            SemanticPoint firstStart,
            SemanticPoint firstEnd,
            SemanticPoint secondStart,
            SemanticPoint secondEnd)
        {
            const double epsilon = 1e-7;
            double o1 = Orientation(firstStart, firstEnd, secondStart);
            double o2 = Orientation(firstStart, firstEnd, secondEnd);
            double o3 = Orientation(secondStart, secondEnd, firstStart);
            double o4 = Orientation(secondStart, secondEnd, firstEnd);
            if ((o1 > epsilon && o2 < -epsilon || o1 < -epsilon && o2 > epsilon)
                && (o3 > epsilon && o4 < -epsilon || o3 < -epsilon && o4 > epsilon))
            {
                return true;
            }

            return Math.Abs(o1) <= epsilon && OnSegment(firstStart, firstEnd, secondStart, epsilon)
                   || Math.Abs(o2) <= epsilon && OnSegment(firstStart, firstEnd, secondEnd, epsilon)
                   || Math.Abs(o3) <= epsilon && OnSegment(secondStart, secondEnd, firstStart, epsilon)
                   || Math.Abs(o4) <= epsilon && OnSegment(secondStart, secondEnd, firstEnd, epsilon);
        }

        private static double Orientation(SemanticPoint start, SemanticPoint end, SemanticPoint point)
        {
            return (end.X - start.X) * (point.Y - start.Y)
                   - (end.Y - start.Y) * (point.X - start.X);
        }

        private static bool OnSegment(
            SemanticPoint start,
            SemanticPoint end,
            SemanticPoint point,
            double epsilon)
        {
            return point.X >= Math.Min(start.X, end.X) - epsilon
                   && point.X <= Math.Max(start.X, end.X) + epsilon
                   && point.Y >= Math.Min(start.Y, end.Y) - epsilon
                   && point.Y <= Math.Max(start.Y, end.Y) + epsilon;
        }

        private static bool SamePoint2D(SemanticPoint first, SemanticPoint second)
        {
            return first.X == second.X && first.Y == second.Y;
        }

        public static double BoundsCenterDistance(SemanticGeometry? first, SemanticGeometry? second)
        {
            SemanticPoint a = RepresentativePoint(first);
            SemanticPoint b = RepresentativePoint(second);
            double dx = a.X - b.X;
            double dy = a.Y - b.Y;
            return Math.Sqrt(dx * dx + dy * dy);
        }

        public static bool IsFinite(SemanticPoint? point)
        {
            return point != null
                   && !double.IsNaN(point.X) && !double.IsInfinity(point.X)
                   && !double.IsNaN(point.Y) && !double.IsInfinity(point.Y)
                   && !double.IsNaN(point.Z) && !double.IsInfinity(point.Z);
        }
    }

    public static class BuildingSemanticStableId
    {
        [ThreadStatic]
        private static SHA256? _threadSha256;

        public static string Create(string prefix, params string[] parts)
        {
            string material = string.Join("\u001f", parts ?? Array.Empty<string>());
            byte[] bytes = GetThreadSha256().ComputeHash(Encoding.UTF8.GetBytes(material));
            return prefix + "_" + ToHex(bytes).Substring(0, 24).ToLowerInvariant();
        }

        public static string Sha256File(string path)
        {
            using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
            using (SHA256 sha = SHA256.Create())
                return ToHex(sha.ComputeHash(stream));
        }

        public static string Sha256Text(string text)
        {
            return ToHex(GetThreadSha256().ComputeHash(Encoding.UTF8.GetBytes(text ?? string.Empty)));
        }

        private static SHA256 GetThreadSha256()
        {
            return _threadSha256 ?? (_threadSha256 = SHA256.Create());
        }

        public static string ToHex(byte[] bytes)
        {
            var builder = new StringBuilder(bytes.Length * 2);
            foreach (byte value in bytes)
                builder.Append(value.ToString("X2", CultureInfo.InvariantCulture));
            return builder.ToString();
        }
    }
}
