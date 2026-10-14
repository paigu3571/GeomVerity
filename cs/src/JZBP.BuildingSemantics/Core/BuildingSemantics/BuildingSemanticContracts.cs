// SPDX-License-Identifier: MPL-2.0
// Copyright (c) 2026 张田; 著作权人、原作者及维护者：张田；其他贡献者和第三方保留各自权利。
using System;
using System.Collections.Generic;
using System.Linq;

namespace JZBP.BuildingSemantics.Core
{
    public static class BuildingSemanticSchema
    {
        public const string SnapshotV1 = "building-semantics.v1";
        public const string PrimitiveSnapshotV1 = "cad-primitives.v1";
        public const string GeometrySnapshotV1 = "building-geometry.v1";
        public const string OverrideV1 = "building-semantics.override.v1";
        public const string FeedbackV1 = "l3-feedback.v1";
        public const string ProfileV1 = "building-semantics-project-profile.v1";
        public const string FactSnapshotV1 = "building-semantics-cad-facts.v1";
        public const string Producer = "JZBP.BuildingSemantics";
        public const string ProducerVersion = "0.3.0-dev";
    }

    public static class BuildingSemanticRulePacks
    {
        public const string Common = "common";
        public const string Basement = "basement";
        public const string GroundResidential = "ground_residential";
    }

    public static class BuildingSemanticReasonCodes
    {
        public const string Ok = "OK";
        public const string ProfileInvalid = "PROFILE_INVALID";
        public const string UnitProfileRequired = "UNIT_PROFILE_REQUIRED";
        public const string UnitMismatch = "UNIT_MISMATCH";
        public const string DrawingHashRequired = "DRAWING_HASH_REQUIRED";
        public const string DrawingHashMismatch = "DRAWING_HASH_MISMATCH";
        public const string SourceModifiedDuringScan = "SOURCE_MODIFIED_DURING_SCAN";
        public const string T20InterpreterRequired = "T20_INTERPRETER_REQUIRED";
        public const string T20NativeGeometryUnavailable = "T20_NATIVE_GEOMETRY_UNAVAILABLE";
        public const string FactProviderFailed = "FACT_PROVIDER_FAILED";
        public const string InvalidGeometry = "INVALID_GEOMETRY";
        public const string GeometryAreaRequiresLoopTopology = "GEOMETRY_AREA_REQUIRES_LOOP_TOPOLOGY";
        public const string NestedTransformFailed = "NESTED_TRANSFORM_FAILED";
        public const string UnsupportedProxyObject = "UNSUPPORTED_PROXY_OBJECT";
        public const string LowConfidence = "LOW_CONFIDENCE";
        public const string MissingEvidence = "MISSING_EVIDENCE";
        public const string AmbiguousRelation = "AMBIGUOUS_RELATION";
        public const string HoldoutRegionNotFrozen = "HOLDOUT_REGION_NOT_FROZEN";
        public const string OutputWriteFailed = "OUTPUT_WRITE_FAILED";
        public const string SnapshotDrawingMismatch = "SNAPSHOT_DRAWING_MISMATCH";
        public const string SnapshotContentHashMismatch = "SNAPSHOT_CONTENT_HASH_MISMATCH";
        public const string NoSemanticObjects = "NO_SEMANTIC_OBJECTS";
        public const string ObservationRegionNotFrozen = "OBSERVATION_REGION_NOT_FROZEN";
        public const string RulesNotFrozen = "RULES_NOT_FROZEN";
        public const string HoldoutEvaluationLocked = "HOLDOUT_EVALUATION_LOCKED";
        public const string SourceDrawingDirty = "SOURCE_DRAWING_DIRTY";
        public const string DbmodEvidenceUnavailable = "DBMOD_EVIDENCE_UNAVAILABLE";
        public const string ScanInputNotReadOnly = "SCAN_INPUT_NOT_READ_ONLY";
        public const string ActiveDrawingSemanticMismatch = "ACTIVE_DRAWING_SEMANTIC_MISMATCH";
        public const string ActiveDrawingModifiedDuringViewValidation = "ACTIVE_DRAWING_MODIFIED_DURING_VIEW_VALIDATION";
        public const string XrefHashUnavailable = "XREF_HASH_UNAVAILABLE";
        public const string XclipFilterUnreadable = "XCLIP_FILTER_UNREADABLE";
        public const string T20OutOfScopeIgnored = "T20_OUT_OF_SCOPE_IGNORED";
        public const string KnownSpaceLabelUnresolved = "KNOWN_SPACE_LABEL_UNRESOLVED";
        public const string SemanticOverrideApplied = "SEMANTIC_OVERRIDE_APPLIED";
        public const string SemanticOverrideInvalid = "SEMANTIC_OVERRIDE_INVALID";
    }

    public enum AnalysisRunStatus
    {
        Accepted,
        Review,
        Failed
    }

    public enum ScanInputMode
    {
        ActiveDocument,
        DiskSideDatabase
    }

    public enum DecisionStatus
    {
        Accepted,
        Review,
        Rejected
    }

    public enum FindingSeverity
    {
        Information,
        Review,
        Error
    }

    public enum SemanticObjectType
    {
        Storey,
        Space,
        Wall,
        Column,
        Opening,
        Door,
        Window,
        Shaft,
        Stair,
        Ramp,
        Zone,
        RoofLine
    }

    public enum WallClassification
    {
        Ordinary,
        Shear,
        Fire,
        CivilDefense,
        Unknown,
        Masonry
    }

    public enum ZoneClassification
    {
        Fire,
        CivilDefense,
        Unknown
    }

    public enum SemanticRelationType
    {
        Contains,
        BoundedBy,
        HostedBy,
        FillsOpening,
        AdjacentTo,
        Connects,
        Overlaps
    }

    public enum CadFactKind
    {
        Unknown,
        Annotation,
        Text,
        Storey,
        Space,
        Wall,
        Column,
        Opening,
        Door,
        Window,
        Shaft,
        Stair,
        Ramp,
        Zone,
        RoofLine,
        Boundary,
        BlockReference
    }

    public enum GeometryKind
    {
        None,
        Point,
        Polyline,
        Polygon,
        MultiPath,
        Bounds
    }

    public enum ProxyDisposition
    {
        SupportedFact,
        IgnoredAnnotation,
        IgnoredOutOfScope,
        ReviewUnknown
    }

    public enum SemanticRuleState
    {
        Calibration,
        Frozen
    }

    public enum ObservationRegionRole
    {
        Calibration,
        Holdout
    }

    public enum ObservationRegionState
    {
        AwaitingHumanCoordinates,
        Frozen
    }

    public sealed class AnalysisRequest
    {
        public ProjectProfile Profile { get; set; } = new ProjectProfile();
        public string ProfileHash { get; set; } = string.Empty;
        /// <summary>
        /// 本次扫描实际所属的项目空间。未登记图纸使用按 DWG 哈希生成的自动空间，
        /// 避免通用规则模板的 project_id 污染不同项目的输出与快照身份。
        /// 为空时保持兼容，继续使用 Profile.ProjectId。
        /// </summary>
        public string RuntimeProjectId { get; set; } = string.Empty;
        public string DrawingPath { get; set; } = string.Empty;
        public string DrawingHash { get; set; } = string.Empty;
        public string DrawingId { get; set; } = string.Empty;
        public long SourceFileLength { get; set; }
        public DateTime SourceLastWriteUtc { get; set; }
    }

    public interface IBuildingSemanticService
    {
        BuildingSemanticSnapshot Analyze(AnalysisRequest? request);
    }

    /// <summary>
    /// 三层识图入口。Analyze 保持既有调用契约；AnalyzeLayers 同时返回
    /// 图元层、几何层和语义层，供 OpenBuddy 与各专业工具按需复用。
    /// </summary>
    public interface IBuildingRecognitionService : IBuildingSemanticService
    {
        BuildingRecognitionBundle AnalyzeLayers(AnalysisRequest? request);
    }

    public interface ICadFactProvider
    {
        string ProviderId { get; }
        DrawingSnapshot Collect(CadFactRequest request);
    }

    public sealed class CadFactRequest
    {
        public AnalysisRequest Analysis { get; set; } = new AnalysisRequest();
    }

    public sealed class ProjectProfile
    {
        public string SchemaVersion { get; set; } = BuildingSemanticSchema.ProfileV1;
        public string ProjectId { get; set; } = string.Empty;
        public string ProfileVersion { get; set; } = "1.0.0";
        public string DisplayName { get; set; } = string.Empty;
        public string Units { get; set; } = string.Empty;
        public double UnitScaleToMillimeters { get; set; }
        public string OutputRoot { get; set; } = string.Empty;
        public bool AllowUnlistedDrawings { get; set; }
        public SemanticRuleState RuleState { get; set; } = SemanticRuleState.Calibration;
        public string RulesFrozenBy { get; set; } = string.Empty;
        public string RulesFrozenAtUtc { get; set; } = string.Empty;
        public List<string> AdapterPriority { get; set; } = new List<string>();
        public List<DrawingProfileRule> Drawings { get; set; } = new List<DrawingProfileRule>();
        public List<LayerNormalizationRule> LayerNormalization { get; set; } = new List<LayerNormalizationRule>();
        public List<GeometrySemanticRule> GeometrySemanticRules { get; set; } = new List<GeometrySemanticRule>();
        public List<RoomUseRule> RoomUseDictionary { get; set; } = new List<RoomUseRule>();
        public SemanticThresholds Thresholds { get; set; } = new SemanticThresholds();
        public List<ObservationRegion> ObservationRegions { get; set; } = new List<ObservationRegion>();
    }

    public sealed class DrawingProfileRule
    {
        public string DrawingId { get; set; } = string.Empty;
        public string FileName { get; set; } = string.Empty;
        public string Sha256 { get; set; } = string.Empty;
        public string Role { get; set; } = string.Empty;
        public string StoreyCode { get; set; } = string.Empty;
    }

    public sealed class LayerNormalizationRule
    {
        public string Id { get; set; } = string.Empty;
        public string Pattern { get; set; } = string.Empty;
        public string Replacement { get; set; } = string.Empty;
        public bool IgnoreCase { get; set; } = true;
    }

    public sealed class RoomUseRule
    {
        public string UseCode { get; set; } = string.Empty;
        public string SemanticType { get; set; } = SemanticObjectType.Space.ToString();
        public string RulePack { get; set; } = BuildingSemanticRulePacks.Common;
        public List<string> Keywords { get; set; } = new List<string>();
        public List<string> ExcludedKeywords { get; set; } = new List<string>();
    }

    /// <summary>
    /// 第三层把第二层的未命名几何提升为工程对象时使用的项目规则。
    /// 规则只消费既有 GeometryFact，不改变图元层或几何层内容。
    /// </summary>
    public sealed class GeometrySemanticRule
    {
        public string Id { get; set; } = string.Empty;
        public string SemanticType { get; set; } = string.Empty;
        public string Classification { get; set; } = string.Empty;
        public List<string> NormalizedLayers { get; set; } = new List<string>();
        public List<string> NativeClassNames { get; set; } = new List<string>();
        public List<GeometryFeatureKind> FeatureKinds { get; set; } = new List<GeometryFeatureKind>();
        public Dictionary<string, string> RequiredProperties { get; set; } = new Dictionary<string, string>(StringComparer.Ordinal);
        public bool RequireClosed { get; set; }
        public bool RequireExact { get; set; }
        public double MinimumAreaSquareMillimeters { get; set; }
        public double MaximumAreaSquareMillimeters { get; set; }
        public double Confidence { get; set; }
        public GeometrySemanticLabelMode LabelMode { get; set; }
        public List<string> LabelLayers { get; set; } = new List<string>();
        public List<string> AreaLabelLayers { get; set; } = new List<string>();
        public double MaximumAreaLabelRelativeDifference { get; set; }
    }

    public enum GeometrySemanticLabelMode
    {
        None,
        UniqueContainedRoomUse,
        UniqueContainedRoomUseAndArea
    }

    public sealed class SemanticThresholds
    {
        public double AcceptedConfidence { get; set; } = 0.97;
        public double ReviewConfidence { get; set; } = 0.40;
        public double RelationToleranceMillimeters { get; set; } = 150.0;
        public double BoundaryFallbackMinimumIou { get; set; } = 0.95;
        public int FullScanMaximumSeconds { get; set; } = 60;
        public int ReplayMaximumSeconds { get; set; } = 5;
    }

    public sealed class ObservationRegion
    {
        public string Code { get; set; } = string.Empty;
        public string Name { get; set; } = string.Empty;
        public ObservationRegionRole Role { get; set; }
        public ObservationRegionState State { get; set; } = ObservationRegionState.AwaitingHumanCoordinates;
        public string DrawingHash { get; set; } = string.Empty;
        public List<SemanticPoint> PolygonWcsMillimeters { get; set; } = new List<SemanticPoint>();
        public string FrozenBy { get; set; } = string.Empty;
        public string FrozenAtUtc { get; set; } = string.Empty;
    }

    public sealed class CadFactSnapshot
    {
        public string SchemaVersion { get; set; } = BuildingSemanticSchema.FactSnapshotV1;
        public string ProviderId { get; set; } = string.Empty;
        public bool IsSuccess { get; set; }
        public bool DetectedT20 { get; set; }
        public bool T20InterpreterAvailable { get; set; }
        public long ElapsedMilliseconds { get; set; }
        public List<string> ReasonCodes { get; set; } = new List<string>();
        public List<CadPrimitive> Primitives { get; set; } = new List<CadPrimitive>();
        public List<CadFact> Facts { get; set; } = new List<CadFact>();
        public List<ProxyLedgerEntry> ProxyLedger { get; set; } = new List<ProxyLedgerEntry>();
        public List<ProviderDiagnostic> Diagnostics { get; set; } = new List<ProviderDiagnostic>();
    }

    /// <summary>
    /// ICadFactProvider 的不可变交付边界。构造和每次读取都深拷贝可变 CAD DTO，
    /// 因此提供者或调用方后续修改原对象不会回写到已冻结的图纸事实快照。
    /// </summary>
    public sealed class DrawingSnapshot
    {
        private readonly List<string> _reasonCodes;
        private readonly List<CadPrimitive> _primitives;
        private readonly List<CadFact> _facts;
        private readonly List<ProxyLedgerEntry> _proxyLedger;
        private readonly List<ProviderDiagnostic> _diagnostics;

        private DrawingSnapshot(CadFactSnapshot source)
        {
            SchemaVersion = source.SchemaVersion ?? BuildingSemanticSchema.FactSnapshotV1;
            ProviderId = source.ProviderId ?? string.Empty;
            IsSuccess = source.IsSuccess;
            DetectedT20 = source.DetectedT20;
            T20InterpreterAvailable = source.T20InterpreterAvailable;
            ElapsedMilliseconds = source.ElapsedMilliseconds;
            _reasonCodes = new List<string>(source.ReasonCodes ?? new List<string>());
            _primitives = (source.Primitives ?? new List<CadPrimitive>())
                .Select(RecognitionLayerClone.ClonePrimitive)
                .ToList();
            _facts = (source.Facts ?? new List<CadFact>()).Select(CloneFact).ToList();
            _proxyLedger = (source.ProxyLedger ?? new List<ProxyLedgerEntry>()).Select(CloneProxy).ToList();
            _diagnostics = (source.Diagnostics ?? new List<ProviderDiagnostic>()).Select(CloneDiagnostic).ToList();
        }

        public string SchemaVersion { get; }
        public string ProviderId { get; }
        public bool IsSuccess { get; }
        public bool DetectedT20 { get; }
        public bool T20InterpreterAvailable { get; }
        public long ElapsedMilliseconds { get; }
        public IReadOnlyList<string> ReasonCodes => _reasonCodes.AsReadOnly();
        public IReadOnlyList<CadPrimitive> Primitives => _primitives.Select(RecognitionLayerClone.ClonePrimitive).ToList().AsReadOnly();
        public IReadOnlyList<CadFact> Facts => _facts.Select(CloneFact).ToList().AsReadOnly();
        public IReadOnlyList<ProxyLedgerEntry> ProxyLedger => _proxyLedger.Select(CloneProxy).ToList().AsReadOnly();
        public IReadOnlyList<ProviderDiagnostic> Diagnostics => _diagnostics.Select(CloneDiagnostic).ToList().AsReadOnly();

        public static DrawingSnapshot Freeze(CadFactSnapshot source)
        {
            if (source == null)
                throw new ArgumentNullException(nameof(source));
            return new DrawingSnapshot(source);
        }

        private static CadFact CloneFact(CadFact source)
        {
            source = source ?? new CadFact();
            return new CadFact
            {
                FactId = source.FactId ?? string.Empty,
                Kind = source.Kind,
                Source = CloneSource(source.Source),
                Geometry = CloneGeometry(source.Geometry),
                RawLabel = source.RawLabel ?? string.Empty,
                Confidence = source.Confidence,
                Properties = new Dictionary<string, string>(source.Properties ?? new Dictionary<string, string>(), StringComparer.Ordinal),
                Evidence = (source.Evidence ?? new List<SemanticEvidence>()).Select(CloneEvidence).ToList(),
                ReasonCodes = new List<string>(source.ReasonCodes ?? new List<string>())
            };
        }

        private static SourceReference CloneSource(SourceReference source)
        {
            source = source ?? new SourceReference();
            return new SourceReference
            {
                DrawingHash = source.DrawingHash ?? string.Empty,
                Handle = source.Handle ?? string.Empty,
                StablePath = source.StablePath ?? string.Empty,
                RawLayer = source.RawLayer ?? string.Empty,
                EffectiveLayer = source.EffectiveLayer ?? string.Empty,
                NormalizedLayer = source.NormalizedLayer ?? string.Empty,
                NativeDxfName = source.NativeDxfName ?? string.Empty,
                NativeClassName = source.NativeClassName ?? string.Empty,
                BlockPath = new List<string>(source.BlockPath ?? new List<string>()),
                XrefPath = new List<string>(source.XrefPath ?? new List<string>()),
                XrefHashes = new List<string>(source.XrefHashes ?? new List<string>()),
                WcsTransform = new List<double>(source.WcsTransform ?? new List<double>())
            };
        }

        private static SemanticGeometry CloneGeometry(SemanticGeometry source)
        {
            source = source ?? new SemanticGeometry();
            SemanticBounds bounds = source.Bounds ?? new SemanticBounds();
            return new SemanticGeometry
            {
                Kind = source.Kind,
                IsClosed = source.IsClosed,
                IsExact = source.IsExact,
                ExtractionMethod = source.ExtractionMethod ?? string.Empty,
                Paths = (source.Paths ?? new List<List<SemanticPoint>>())
                    .Select(path => (path ?? new List<SemanticPoint>())
                        .Select(point => point == null ? null! : new SemanticPoint(point.X, point.Y, point.Z))
                        .ToList())
                    .ToList(),
                Bounds = new SemanticBounds
                {
                    MinX = bounds.MinX,
                    MinY = bounds.MinY,
                    MinZ = bounds.MinZ,
                    MaxX = bounds.MaxX,
                    MaxY = bounds.MaxY,
                    MaxZ = bounds.MaxZ,
                    IsValid = bounds.IsValid
                }
            };
        }

        private static SemanticEvidence CloneEvidence(SemanticEvidence source)
        {
            source = source ?? new SemanticEvidence();
            return new SemanticEvidence
            {
                Code = source.Code ?? string.Empty,
                Kind = source.Kind ?? string.Empty,
                Value = source.Value ?? string.Empty,
                SourceHandle = source.SourceHandle ?? string.Empty,
                Weight = source.Weight
            };
        }

        private static ProxyLedgerEntry CloneProxy(ProxyLedgerEntry source)
        {
            source = source ?? new ProxyLedgerEntry();
            return new ProxyLedgerEntry
            {
                StablePath = source.StablePath ?? string.Empty,
                Handle = source.Handle ?? string.Empty,
                OriginalDxfName = source.OriginalDxfName ?? string.Empty,
                OriginalClassName = source.OriginalClassName ?? string.Empty,
                ApplicationDescription = source.ApplicationDescription ?? string.Empty,
                EffectiveLayer = source.EffectiveLayer ?? string.Empty,
                Disposition = source.Disposition,
                ReasonCode = source.ReasonCode ?? string.Empty
            };
        }

        private static ProviderDiagnostic CloneDiagnostic(ProviderDiagnostic source)
        {
            source = source ?? new ProviderDiagnostic();
            return new ProviderDiagnostic
            {
                Severity = source.Severity,
                ReasonCode = source.ReasonCode ?? string.Empty,
                Message = source.Message ?? string.Empty,
                StablePath = source.StablePath ?? string.Empty
            };
        }
    }

    public sealed class CadFact
    {
        public string FactId { get; set; } = string.Empty;
        public CadFactKind Kind { get; set; }
        public SourceReference Source { get; set; } = new SourceReference();
        public SemanticGeometry Geometry { get; set; } = new SemanticGeometry();
        public string RawLabel { get; set; } = string.Empty;
        public double Confidence { get; set; }
        public Dictionary<string, string> Properties { get; set; } = new Dictionary<string, string>(StringComparer.Ordinal);
        public List<SemanticEvidence> Evidence { get; set; } = new List<SemanticEvidence>();
        public List<string> ReasonCodes { get; set; } = new List<string>();
    }

    public sealed class SourceReference
    {
        public string DrawingHash { get; set; } = string.Empty;
        public string Handle { get; set; } = string.Empty;
        public string StablePath { get; set; } = string.Empty;
        public string RawLayer { get; set; } = string.Empty;
        public string EffectiveLayer { get; set; } = string.Empty;
        public string NormalizedLayer { get; set; } = string.Empty;
        public string NativeDxfName { get; set; } = string.Empty;
        public string NativeClassName { get; set; } = string.Empty;
        public List<string> BlockPath { get; set; } = new List<string>();
        public List<string> XrefPath { get; set; } = new List<string>();
        public List<string> XrefHashes { get; set; } = new List<string>();
        public List<double> WcsTransform { get; set; } = new List<double>();
    }

    public sealed class SemanticEvidence
    {
        public string Code { get; set; } = string.Empty;
        public string Kind { get; set; } = string.Empty;
        public string Value { get; set; } = string.Empty;
        public string SourceHandle { get; set; } = string.Empty;
        public double Weight { get; set; }
    }

    public sealed class SemanticPoint
    {
        public SemanticPoint()
        {
        }

        public SemanticPoint(double x, double y, double z = 0)
        {
            X = x;
            Y = y;
            Z = z;
        }

        public double X { get; set; }
        public double Y { get; set; }
        public double Z { get; set; }
    }

    public sealed class SemanticBounds
    {
        public double MinX { get; set; }
        public double MinY { get; set; }
        public double MinZ { get; set; }
        public double MaxX { get; set; }
        public double MaxY { get; set; }
        public double MaxZ { get; set; }
        public bool IsValid { get; set; }
    }

    public sealed class SemanticGeometry
    {
        public GeometryKind Kind { get; set; }
        public bool IsClosed { get; set; }
        public bool IsExact { get; set; }
        public string ExtractionMethod { get; set; } = string.Empty;
        public List<List<SemanticPoint>> Paths { get; set; } = new List<List<SemanticPoint>>();
        public SemanticBounds Bounds { get; set; } = new SemanticBounds();
    }

    public sealed class ProxyLedgerEntry
    {
        public string StablePath { get; set; } = string.Empty;
        public string Handle { get; set; } = string.Empty;
        public string OriginalDxfName { get; set; } = string.Empty;
        public string OriginalClassName { get; set; } = string.Empty;
        public string ApplicationDescription { get; set; } = string.Empty;
        public string EffectiveLayer { get; set; } = string.Empty;
        public ProxyDisposition Disposition { get; set; }
        public string ReasonCode { get; set; } = string.Empty;
    }

    public sealed class ProviderDiagnostic
    {
        public FindingSeverity Severity { get; set; }
        public string ReasonCode { get; set; } = string.Empty;
        public string Message { get; set; } = string.Empty;
        public string StablePath { get; set; } = string.Empty;
    }

    public sealed class BuildingSemanticSnapshot
    {
        public string SchemaVersion { get; set; } = BuildingSemanticSchema.SnapshotV1;
        public string Producer { get; set; } = BuildingSemanticSchema.Producer;
        public string ProducerVersion { get; set; } = BuildingSemanticSchema.ProducerVersion;
        public string ProducerBinarySha256 { get; set; } = string.Empty;
        public string GeneratedAtUtc { get; set; } = string.Empty;
        public AnalysisRunStatus Status { get; set; }
        public List<string> ReasonCodes { get; set; } = new List<string>();
        public DrawingIdentity Drawing { get; set; } = new DrawingIdentity();
        public ProfileIdentity Profile { get; set; } = new ProfileIdentity();
        public ScanIntegrityEvidence Integrity { get; set; } = new ScanIntegrityEvidence();
        public string FactProviderId { get; set; } = string.Empty;
        public string DeterministicContentHash { get; set; } = string.Empty;
        public List<SemanticObject> Objects { get; set; } = new List<SemanticObject>();
        public List<SpatialRelation> Relations { get; set; } = new List<SpatialRelation>();
        public List<ReviewFinding> Findings { get; set; } = new List<ReviewFinding>();
        public List<ProxyLedgerEntry> ProxyLedger { get; set; } = new List<ProxyLedgerEntry>();
        public SnapshotMetrics Metrics { get; set; } = new SnapshotMetrics();
        public List<ProviderDiagnostic> ProviderDiagnostics { get; set; } = new List<ProviderDiagnostic>();
    }

    public sealed class DrawingIdentity
    {
        public string DrawingId { get; set; } = string.Empty;
        public string FileName { get; set; } = string.Empty;
        public string Sha256 { get; set; } = string.Empty;
        public long FileLength { get; set; }
        public string SourceLastWriteUtc { get; set; } = string.Empty;
        public string CoordinateSystem { get; set; } = "WCS";
        public string GeometryUnits { get; set; } = "mm";
    }

    public sealed class ProfileIdentity
    {
        public string ProjectId { get; set; } = string.Empty;
        public string ProfileVersion { get; set; } = string.Empty;
        public string Sha256 { get; set; } = string.Empty;
    }

    public sealed class ScanIntegrityEvidence
    {
        public string SourceHashBefore { get; set; } = string.Empty;
        public string SourceHashAfter { get; set; } = string.Empty;
        public bool SourceBytesUnchanged { get; set; }
        public ScanInputMode ScanInputMode { get; set; } = ScanInputMode.ActiveDocument;
        public bool InputDatabaseReadOnly { get; set; }
        public int DbmodBefore { get; set; }
        public int DbmodAfter { get; set; }
        public bool DbmodCleanAtStart { get; set; }
        public bool DbmodUnchanged { get; set; }
    }

    public sealed class SemanticObject
    {
        public string SemanticId { get; set; } = string.Empty;
        public SemanticObjectType Type { get; set; }
        public string Classification { get; set; } = string.Empty;
        public string RawLabel { get; set; } = string.Empty;
        public string UseCode { get; set; } = string.Empty;
        public DecisionStatus Status { get; set; }
        public double Confidence { get; set; }
        public SourceReference Source { get; set; } = new SourceReference();
        public SemanticGeometry Geometry { get; set; } = new SemanticGeometry();
        public List<SemanticEvidence> Evidence { get; set; } = new List<SemanticEvidence>();
        public List<string> ReasonCodes { get; set; } = new List<string>();
    }

    public sealed class SpatialRelation
    {
        public string RelationId { get; set; } = string.Empty;
        public SemanticRelationType Type { get; set; }
        public string FromSemanticId { get; set; } = string.Empty;
        public string ToSemanticId { get; set; } = string.Empty;
        public DecisionStatus Status { get; set; }
        public double Confidence { get; set; }
        public List<SemanticEvidence> Evidence { get; set; } = new List<SemanticEvidence>();
        public List<string> ReasonCodes { get; set; } = new List<string>();
    }

    public sealed class ReviewFinding
    {
        public string FindingId { get; set; } = string.Empty;
        public FindingSeverity Severity { get; set; }
        public string ReasonCode { get; set; } = string.Empty;
        public string Message { get; set; } = string.Empty;
        public string SemanticId { get; set; } = string.Empty;
        public string SourceHandle { get; set; } = string.Empty;
    }

    public sealed class SnapshotMetrics
    {
        public long AnalysisElapsedMilliseconds { get; set; }
        public int FactCount { get; set; }
        public int SemanticObjectCount { get; set; }
        public int AcceptedObjectCount { get; set; }
        public int ReviewObjectCount { get; set; }
        public int RejectedObjectCount { get; set; }
        public int RelationCount { get; set; }
        public int ProxyCount { get; set; }
        public int TopLevelProxyObjectCount { get; set; }
        public int UniqueProxyHandleCount { get; set; }
        public int ReachableProxyInstanceCount { get; set; }
        public int SupportedProxyCount { get; set; }
        public int IgnoredAnnotationProxyCount { get; set; }
        public int IgnoredOutOfScopeProxyCount { get; set; }
        public int ReviewUnknownProxyCount { get; set; }
    }

    public sealed class ProfileValidationResult
    {
        public bool IsValid { get; set; }
        public List<string> ReasonCodes { get; set; } = new List<string>();
        public List<string> Messages { get; set; } = new List<string>();
    }
}
