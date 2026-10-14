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
    /// <summary>
    /// 第一层只描述 CAD 中实际存在的对象种类，不给对象下建筑工程结论。
    /// </summary>
    public enum CadPrimitiveKind
    {
        Unknown,
        Line,
        Polyline,
        Arc,
        Circle,
        Text,
        BlockReference,
        Point,
        Hatch,
        Region,
        Proxy,
        NativeObject
    }

    /// <summary>
    /// 第二层只描述可计算形状，不把形状命名为墙、门、房间等工程对象。
    /// </summary>
    public enum GeometryFeatureKind
    {
        None,
        Point,
        OpenPath,
        ClosedRegion,
        MultiPath,
        BoundsOnly
    }

    public enum GeometryRelationType
    {
        Contains,
        Touches,
        Intersects,
        Near
    }

    public sealed class CadPrimitive
    {
        public string PrimitiveId { get; set; } = string.Empty;
        public string SourceFactId { get; set; } = string.Empty;
        public CadPrimitiveKind Kind { get; set; }

        /// <summary>
        /// 适配器根据 RXClass/图层等给出的非权威提示。它不是最终建筑语义，
        /// 只用于第三层选择候选映射，最终分类仍由语义策略完成。
        /// </summary>
        public string AdapterRoleHint { get; set; } = string.Empty;
        public bool IsSemanticCandidate { get; set; }
        public SourceReference Source { get; set; } = new SourceReference();
        public string RawText { get; set; } = string.Empty;
        public SemanticGeometry RawGeometry { get; set; } = new SemanticGeometry();
        public double ExtractionConfidence { get; set; }
        public Dictionary<string, string> RawProperties { get; set; } = new Dictionary<string, string>(StringComparer.Ordinal);
        public List<SemanticEvidence> Evidence { get; set; } = new List<SemanticEvidence>();
        public List<string> ReasonCodes { get; set; } = new List<string>();
    }

    public sealed class CadPrimitiveSnapshot
    {
        public string SchemaVersion { get; set; } = BuildingSemanticSchema.PrimitiveSnapshotV1;
        public string Producer { get; set; } = BuildingSemanticSchema.Producer;
        public string ProducerVersion { get; set; } = BuildingSemanticSchema.ProducerVersion;
        public string ProducerBinarySha256 { get; set; } = string.Empty;
        public string GeneratedAtUtc { get; set; } = string.Empty;
        public AnalysisRunStatus Status { get; set; }
        public List<string> ReasonCodes { get; set; } = new List<string>();
        public DrawingIdentity Drawing { get; set; } = new DrawingIdentity();
        public ProfileIdentity Profile { get; set; } = new ProfileIdentity();
        public ScanIntegrityEvidence Integrity { get; set; } = new ScanIntegrityEvidence();
        public string ExtractionConfigurationHash { get; set; } = string.Empty;
        public string FactProviderId { get; set; } = string.Empty;
        public string DeterministicHashAlgorithm { get; set; } = string.Empty;
        public string DeterministicContentHash { get; set; } = string.Empty;
        public List<CadPrimitive> Primitives { get; set; } = new List<CadPrimitive>();
        public List<ProxyLedgerEntry> ProxyLedger { get; set; } = new List<ProxyLedgerEntry>();
        public List<ProviderDiagnostic> ProviderDiagnostics { get; set; } = new List<ProviderDiagnostic>();
        public PrimitiveLayerMetrics Metrics { get; set; } = new PrimitiveLayerMetrics();
    }

    public sealed class PrimitiveLayerMetrics
    {
        public int PrimitiveCount { get; set; }
        public int SemanticCandidateCount { get; set; }
        public int TextCount { get; set; }
        public int BlockReferenceCount { get; set; }
        public int ProxyOrNativeObjectCount { get; set; }
        public int WithRawGeometryCount { get; set; }
        public int ProxyLedgerCount { get; set; }
    }

    public sealed class GeometryMeasurements
    {
        public double LengthMillimeters { get; set; }
        public double AreaSquareMillimeters { get; set; }
        public bool AreaIsAvailable { get; set; }
        public string AreaMethod { get; set; } = "not_available";
        public double WidthMillimeters { get; set; }
        public double HeightMillimeters { get; set; }
        public SemanticPoint RepresentativePointWcsMillimeters { get; set; } = new SemanticPoint();
    }

    public sealed class GeometryFact
    {
        public string GeometryId { get; set; } = string.Empty;
        public string CompatibilityFactId { get; set; } = string.Empty;
        public List<string> SourcePrimitiveIds { get; set; } = new List<string>();
        public GeometryFeatureKind FeatureKind { get; set; }
        public string AdapterRoleHint { get; set; } = string.Empty;
        public bool IsSemanticCandidate { get; set; }
        public SourceReference Source { get; set; } = new SourceReference();
        public SemanticGeometry Geometry { get; set; } = new SemanticGeometry();
        public GeometryMeasurements Measurements { get; set; } = new GeometryMeasurements();
        public string RawText { get; set; } = string.Empty;
        public double ExtractionConfidence { get; set; }
        public Dictionary<string, string> RawProperties { get; set; } = new Dictionary<string, string>(StringComparer.Ordinal);
        public List<SemanticEvidence> Evidence { get; set; } = new List<SemanticEvidence>();
        public List<string> ReasonCodes { get; set; } = new List<string>();
    }

    public sealed class GeometryRelation
    {
        public string RelationId { get; set; } = string.Empty;
        public GeometryRelationType Type { get; set; }
        public string FromGeometryId { get; set; } = string.Empty;
        public string ToGeometryId { get; set; } = string.Empty;
        public double DistanceMillimeters { get; set; }
        public double Confidence { get; set; }
        public List<string> ReasonCodes { get; set; } = new List<string>();
    }

    public sealed class BuildingGeometrySnapshot
    {
        public string SchemaVersion { get; set; } = BuildingSemanticSchema.GeometrySnapshotV1;
        public string Producer { get; set; } = BuildingSemanticSchema.Producer;
        public string ProducerVersion { get; set; } = BuildingSemanticSchema.ProducerVersion;
        public string ProducerBinarySha256 { get; set; } = string.Empty;
        public string GeneratedAtUtc { get; set; } = string.Empty;
        public AnalysisRunStatus Status { get; set; }
        public List<string> ReasonCodes { get; set; } = new List<string>();
        public DrawingIdentity Drawing { get; set; } = new DrawingIdentity();
        public ProfileIdentity Profile { get; set; } = new ProfileIdentity();
        public ScanIntegrityEvidence Integrity { get; set; } = new ScanIntegrityEvidence();
        public string SourcePrimitiveContentHash { get; set; } = string.Empty;
        public string GeometryConfigurationHash { get; set; } = string.Empty;
        public string FactProviderId { get; set; } = string.Empty;
        public string DeterministicHashAlgorithm { get; set; } = string.Empty;
        public string DeterministicContentHash { get; set; } = string.Empty;
        public List<GeometryFact> Facts { get; set; } = new List<GeometryFact>();
        public List<GeometryRelation> Relations { get; set; } = new List<GeometryRelation>();
        public List<ProviderDiagnostic> ProviderDiagnostics { get; set; } = new List<ProviderDiagnostic>();
        public GeometryLayerMetrics Metrics { get; set; } = new GeometryLayerMetrics();
    }

    public sealed class GeometryLayerMetrics
    {
        public int GeometryFactCount { get; set; }
        public int SemanticCandidateCount { get; set; }
        public int ExactGeometryCount { get; set; }
        public int ClosedRegionCount { get; set; }
        public int InvalidGeometryFactCount { get; set; }
        public int InvalidSemanticCandidateCount { get; set; }
        public int RelationCount { get; set; }
    }

    public sealed class BuildingRecognitionBundle
    {
        public CadPrimitiveSnapshot PrimitiveSnapshot { get; set; } = new CadPrimitiveSnapshot();
        public BuildingGeometrySnapshot GeometrySnapshot { get; set; } = new BuildingGeometrySnapshot();
        public BuildingSemanticSnapshot SemanticSnapshot { get; set; } = new BuildingSemanticSnapshot();
    }

    public static class RecognitionLayerClone
    {
        public static CadPrimitive ClonePrimitive(CadPrimitive source)
        {
            source = source ?? new CadPrimitive();
            return new CadPrimitive
            {
                PrimitiveId = source.PrimitiveId ?? string.Empty,
                SourceFactId = source.SourceFactId ?? string.Empty,
                Kind = source.Kind,
                AdapterRoleHint = source.AdapterRoleHint ?? string.Empty,
                IsSemanticCandidate = source.IsSemanticCandidate,
                Source = CloneSource(source.Source),
                RawText = source.RawText ?? string.Empty,
                RawGeometry = CloneGeometry(source.RawGeometry),
                ExtractionConfidence = source.ExtractionConfidence,
                RawProperties = new Dictionary<string, string>(source.RawProperties ?? new Dictionary<string, string>(), StringComparer.Ordinal),
                Evidence = (source.Evidence ?? new List<SemanticEvidence>()).Select(CloneEvidence).ToList(),
                ReasonCodes = new List<string>(source.ReasonCodes ?? new List<string>())
            };
        }

        public static CadFact CloneFact(CadFact source)
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

        public static SourceReference CloneSource(SourceReference? source)
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

        public static SemanticGeometry CloneGeometry(SemanticGeometry? source)
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

        public static SemanticEvidence CloneEvidence(SemanticEvidence? source)
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

        public static ProxyLedgerEntry CloneProxy(ProxyLedgerEntry? source)
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

        public static ProviderDiagnostic CloneDiagnostic(ProviderDiagnostic? source)
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

        public static DrawingIdentity CloneDrawing(DrawingIdentity? source)
        {
            source = source ?? new DrawingIdentity();
            return new DrawingIdentity
            {
                DrawingId = source.DrawingId ?? string.Empty,
                FileName = source.FileName ?? string.Empty,
                Sha256 = source.Sha256 ?? string.Empty,
                FileLength = source.FileLength,
                SourceLastWriteUtc = source.SourceLastWriteUtc ?? string.Empty,
                CoordinateSystem = source.CoordinateSystem ?? "WCS",
                GeometryUnits = source.GeometryUnits ?? "mm"
            };
        }

        public static ProfileIdentity CloneProfile(ProfileIdentity? source)
        {
            source = source ?? new ProfileIdentity();
            return new ProfileIdentity
            {
                ProjectId = source.ProjectId ?? string.Empty,
                ProfileVersion = source.ProfileVersion ?? string.Empty,
                Sha256 = source.Sha256 ?? string.Empty
            };
        }
    }

    public static class CadPrimitiveSnapshotBuilder
    {
        public static CadPrimitiveSnapshot Build(DrawingSnapshot source, AnalysisRequest? request)
        {
            if (source == null)
                throw new ArgumentNullException(nameof(source));

            var snapshot = CreateBase(request);
            snapshot.FactProviderId = source.ProviderId ?? string.Empty;
            snapshot.ExtractionConfigurationHash = ComputeExtractionConfigurationHash(request?.Profile);
            snapshot.ProviderDiagnostics = source.Diagnostics.Select(RecognitionLayerClone.CloneDiagnostic).ToList();
            snapshot.ProxyLedger = source.ProxyLedger.Select(RecognitionLayerClone.CloneProxy).ToList();

            var byPath = new Dictionary<string, CadPrimitive>(StringComparer.Ordinal);
            foreach (CadPrimitive primitive in source.Primitives)
                AddOrReplace(byPath, primitive);
            foreach (CadFact fact in source.Facts)
                AddOrReplace(byPath, FromFact(fact));
            foreach (ProxyLedgerEntry proxy in source.ProxyLedger)
            {
                string key = proxy.StablePath ?? string.Empty;
                if (byPath.ContainsKey(key))
                    continue;
                var primitive = new CadPrimitive
                {
                    PrimitiveId = BuildingSemanticStableId.Create("primitive", request?.DrawingHash ?? string.Empty, key, "proxy"),
                    Kind = CadPrimitiveKind.Proxy,
                    Source = new SourceReference
                    {
                        DrawingHash = request?.DrawingHash ?? string.Empty,
                        Handle = proxy.Handle ?? string.Empty,
                        StablePath = key,
                        EffectiveLayer = proxy.EffectiveLayer ?? string.Empty,
                        NormalizedLayer = proxy.EffectiveLayer ?? string.Empty,
                        NativeDxfName = proxy.OriginalDxfName ?? string.Empty,
                        NativeClassName = proxy.OriginalClassName ?? string.Empty
                    },
                    ExtractionConfidence = 1.0,
                    ReasonCodes = string.IsNullOrWhiteSpace(proxy.ReasonCode)
                        ? new List<string>()
                        : new List<string> { proxy.ReasonCode }
                };
                byPath[key] = primitive;
            }

            snapshot.Primitives = byPath.Values
                .OrderBy(item => item.Source?.StablePath ?? string.Empty, StringComparer.Ordinal)
                .ThenBy(item => item.Kind)
                .ThenBy(item => item.PrimitiveId, StringComparer.Ordinal)
                .Select(RecognitionLayerClone.ClonePrimitive)
                .ToList();
            snapshot.ReasonCodes = source.ReasonCodes
                .Where(code => !string.IsNullOrWhiteSpace(code) && !string.Equals(code, BuildingSemanticReasonCodes.Ok, StringComparison.Ordinal))
                .Distinct(StringComparer.Ordinal)
                .OrderBy(code => code, StringComparer.Ordinal)
                .ToList();

            if (snapshot.Primitives.Count == 0)
            {
                snapshot.Status = AnalysisRunStatus.Failed;
                AddReason(snapshot.ReasonCodes, BuildingSemanticReasonCodes.FactProviderFailed);
            }
            else if (!source.IsSuccess || snapshot.ProviderDiagnostics.Any(IsPrimitiveLayerIssue))
            {
                // 即使天正解释器失败，已取得的原始对象仍保留；第一层只降级为 Review。
                snapshot.Status = AnalysisRunStatus.Review;
            }
            else
            {
                snapshot.Status = AnalysisRunStatus.Accepted;
                snapshot.ReasonCodes.Add(BuildingSemanticReasonCodes.Ok);
            }

            snapshot.Metrics = BuildMetrics(snapshot.Primitives, snapshot.ProxyLedger);
            snapshot.DeterministicContentHash = RecognitionLayerDeterminism.Compute(snapshot);
            return snapshot;
        }

        public static CadPrimitiveSnapshot CreateFailed(AnalysisRequest? request, IEnumerable<string> reasons)
        {
            CadPrimitiveSnapshot snapshot = CreateBase(request);
            snapshot.Status = AnalysisRunStatus.Failed;
            snapshot.ExtractionConfigurationHash = ComputeExtractionConfigurationHash(request?.Profile);
            snapshot.ReasonCodes = (reasons ?? Enumerable.Empty<string>())
                .Where(value => !string.IsNullOrWhiteSpace(value))
                .Distinct(StringComparer.Ordinal)
                .OrderBy(value => value, StringComparer.Ordinal)
                .ToList();
            if (snapshot.ReasonCodes.Count == 0)
                snapshot.ReasonCodes.Add(BuildingSemanticReasonCodes.FactProviderFailed);
            snapshot.DeterministicContentHash = RecognitionLayerDeterminism.Compute(snapshot);
            return snapshot;
        }

        public static CadPrimitive FromFact(CadFact fact)
        {
            fact = fact ?? new CadFact();
            string drawingHash = fact.Source?.DrawingHash ?? string.Empty;
            string stablePath = fact.Source?.StablePath ?? string.Empty;
            return new CadPrimitive
            {
                PrimitiveId = BuildingSemanticStableId.Create("primitive", drawingHash, stablePath, fact.FactId ?? string.Empty),
                SourceFactId = fact.FactId ?? string.Empty,
                Kind = InferPrimitiveKind(fact),
                AdapterRoleHint = fact.Kind.ToString(),
                IsSemanticCandidate = true,
                Source = RecognitionLayerClone.CloneSource(fact.Source),
                RawText = fact.RawLabel ?? string.Empty,
                RawGeometry = RecognitionLayerClone.CloneGeometry(fact.Geometry),
                ExtractionConfidence = fact.Confidence,
                RawProperties = new Dictionary<string, string>(fact.Properties ?? new Dictionary<string, string>(), StringComparer.Ordinal),
                Evidence = (fact.Evidence ?? new List<SemanticEvidence>()).Select(RecognitionLayerClone.CloneEvidence).ToList(),
                ReasonCodes = new List<string>(fact.ReasonCodes ?? new List<string>())
            };
        }

        private static CadPrimitiveSnapshot CreateBase(AnalysisRequest? request)
        {
            string path = request?.DrawingPath ?? string.Empty;
            return new CadPrimitiveSnapshot
            {
                GeneratedAtUtc = DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture),
                DeterministicHashAlgorithm = RecognitionLayerDeterminism.CanonicalBinaryV2,
                Drawing = new DrawingIdentity
                {
                    DrawingId = request?.DrawingId ?? string.Empty,
                    FileName = string.IsNullOrWhiteSpace(path) ? string.Empty : Path.GetFileName(path),
                    Sha256 = request?.DrawingHash ?? string.Empty,
                    FileLength = request?.SourceFileLength ?? 0,
                    SourceLastWriteUtc = request == null || request.SourceLastWriteUtc == default(DateTime)
                        ? string.Empty
                        : request.SourceLastWriteUtc.ToUniversalTime().ToString("O", CultureInfo.InvariantCulture)
                },
                Profile = new ProfileIdentity
                {
                    ProjectId = string.IsNullOrWhiteSpace(request?.RuntimeProjectId)
                        ? request?.Profile?.ProjectId ?? string.Empty
                        : request?.RuntimeProjectId ?? string.Empty,
                    ProfileVersion = request?.Profile?.ProfileVersion ?? string.Empty,
                    Sha256 = request?.ProfileHash ?? string.Empty
                }
            };
        }

        private static string ComputeExtractionConfigurationHash(ProjectProfile? profile)
        {
            var builder = new StringBuilder("primitive-extraction-config-v3|hatch=boundary-loops+pattern-name");
            Append(builder, profile?.Units ?? string.Empty, Number(profile?.UnitScaleToMillimeters ?? 0));
            foreach (string adapter in profile?.AdapterPriority ?? new List<string>())
                Append(builder, "adapter", adapter);
            foreach (LayerNormalizationRule rule in profile?.LayerNormalization ?? new List<LayerNormalizationRule>())
                Append(builder, "layer", rule.Id, rule.Pattern, rule.Replacement, rule.IgnoreCase.ToString());
            return BuildingSemanticStableId.Sha256Text(builder.ToString());
        }

        private static PrimitiveLayerMetrics BuildMetrics(IReadOnlyCollection<CadPrimitive> primitives, IReadOnlyCollection<ProxyLedgerEntry> proxies)
        {
            return new PrimitiveLayerMetrics
            {
                PrimitiveCount = primitives.Count,
                SemanticCandidateCount = primitives.Count(item => item.IsSemanticCandidate),
                TextCount = primitives.Count(item => item.Kind == CadPrimitiveKind.Text),
                BlockReferenceCount = primitives.Count(item => item.Kind == CadPrimitiveKind.BlockReference),
                ProxyOrNativeObjectCount = primitives.Count(item => item.Kind == CadPrimitiveKind.Proxy || item.Kind == CadPrimitiveKind.NativeObject),
                WithRawGeometryCount = primitives.Count(item => SemanticGeometryAlgorithms.IsUsable(item.RawGeometry, false)),
                ProxyLedgerCount = proxies.Count
            };
        }

        private static CadPrimitiveKind InferPrimitiveKind(CadFact fact)
        {
            string identity = ((fact.Source?.NativeDxfName ?? string.Empty) + "|" + (fact.Source?.NativeClassName ?? string.Empty)).ToUpperInvariant();
            if (fact.Kind == CadFactKind.Text || identity.Contains("TEXT")) return CadPrimitiveKind.Text;
            if (identity.Contains("BLOCK") || identity.Contains("INSERT")) return CadPrimitiveKind.BlockReference;
            if (identity.Contains("POLYLINE") || identity.Contains("LWPOLYLINE")) return CadPrimitiveKind.Polyline;
            if (identity.Contains("LINE")) return CadPrimitiveKind.Line;
            if (identity.Contains("ARC")) return CadPrimitiveKind.Arc;
            if (identity.Contains("CIRCLE")) return CadPrimitiveKind.Circle;
            if (identity.Contains("HATCH")) return CadPrimitiveKind.Hatch;
            if (identity.Contains("REGION")) return CadPrimitiveKind.Region;
            if (identity.Contains("POINT")) return CadPrimitiveKind.Point;
            if (identity.Contains("PROXY")) return CadPrimitiveKind.Proxy;
            return CadPrimitiveKind.NativeObject;
        }

        private static bool IsPrimitiveLayerIssue(ProviderDiagnostic diagnostic)
        {
            if (diagnostic == null || diagnostic.Severity == FindingSeverity.Information)
                return false;
            return !string.Equals(diagnostic.ReasonCode, BuildingSemanticReasonCodes.InvalidGeometry, StringComparison.Ordinal)
                   && !string.Equals(diagnostic.ReasonCode, BuildingSemanticReasonCodes.T20NativeGeometryUnavailable, StringComparison.Ordinal);
        }

        private static void AddOrReplace(IDictionary<string, CadPrimitive> target, CadPrimitive primitive)
        {
            if (primitive == null)
                return;
            string key = primitive.Source?.StablePath ?? primitive.PrimitiveId ?? string.Empty;
            if (string.IsNullOrWhiteSpace(primitive.PrimitiveId))
                primitive.PrimitiveId = BuildingSemanticStableId.Create("primitive", primitive.Source?.DrawingHash ?? string.Empty, key);
            if (!target.TryGetValue(key, out CadPrimitive? existing) || primitive.IsSemanticCandidate || !existing.IsSemanticCandidate)
                target[key] = RecognitionLayerClone.ClonePrimitive(primitive);
        }

        private static void AddReason(ICollection<string> reasons, string reason)
        {
            if (!reasons.Contains(reason))
                reasons.Add(reason);
        }

        private static void Append(StringBuilder builder, params string[] values)
        {
            foreach (string value in values)
                builder.Append(value ?? string.Empty).Append('\u001f');
            builder.Append('\n');
        }

        private static string Number(double value)
        {
            return Math.Round(value, 6, MidpointRounding.AwayFromZero).ToString("0.######", CultureInfo.InvariantCulture);
        }
    }

    public sealed class BuildingGeometryService
    {
        public BuildingGeometrySnapshot Build(CadPrimitiveSnapshot source)
        {
            if (source == null)
                throw new ArgumentNullException(nameof(source));

            var snapshot = new BuildingGeometrySnapshot
            {
                GeneratedAtUtc = DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture),
                DeterministicHashAlgorithm = RecognitionLayerDeterminism.CanonicalBinaryV2,
                Drawing = RecognitionLayerClone.CloneDrawing(source.Drawing),
                Profile = RecognitionLayerClone.CloneProfile(source.Profile),
                SourcePrimitiveContentHash = source.DeterministicContentHash ?? string.Empty,
                GeometryConfigurationHash = ConfigurationHash,
                FactProviderId = source.FactProviderId ?? string.Empty,
                ProviderDiagnostics = (source.ProviderDiagnostics ?? new List<ProviderDiagnostic>())
                    .Select(RecognitionLayerClone.CloneDiagnostic).ToList()
            };

            foreach (CadPrimitive primitive in source.Primitives ?? new List<CadPrimitive>())
            {
                bool invalidGeometry;
                SemanticGeometry geometry = NormalizeGeometry(primitive.RawGeometry, out invalidGeometry);
                if (!SemanticGeometryAlgorithms.IsUsable(geometry, false)
                    && !primitive.IsSemanticCandidate
                    && string.IsNullOrWhiteSpace(primitive.RawText)
                    && !invalidGeometry
                    && !(geometry.Bounds != null && geometry.Bounds.IsValid))
                    continue;

                var fact = new GeometryFact
                {
                    GeometryId = BuildingSemanticStableId.Create("geometry", source.Drawing?.Sha256 ?? string.Empty, primitive.PrimitiveId ?? string.Empty, "v1"),
                    CompatibilityFactId = primitive.SourceFactId ?? string.Empty,
                    SourcePrimitiveIds = new List<string> { primitive.PrimitiveId ?? string.Empty },
                    FeatureKind = ClassifyFeature(geometry),
                    AdapterRoleHint = primitive.AdapterRoleHint ?? string.Empty,
                    IsSemanticCandidate = primitive.IsSemanticCandidate,
                    Source = RecognitionLayerClone.CloneSource(primitive.Source),
                    Geometry = geometry,
                    Measurements = Measure(geometry),
                    RawText = primitive.RawText ?? string.Empty,
                    ExtractionConfidence = primitive.ExtractionConfidence,
                    RawProperties = new Dictionary<string, string>(primitive.RawProperties ?? new Dictionary<string, string>(), StringComparer.Ordinal),
                    Evidence = (primitive.Evidence ?? new List<SemanticEvidence>()).Select(RecognitionLayerClone.CloneEvidence).ToList(),
                    ReasonCodes = new List<string>(primitive.ReasonCodes ?? new List<string>())
                };
                if (invalidGeometry || (fact.IsSemanticCandidate
                    && !SemanticGeometryAlgorithms.IsUsable(fact.Geometry, false)
                    && !string.Equals(fact.AdapterRoleHint, CadFactKind.Storey.ToString(), StringComparison.OrdinalIgnoreCase)))
                {
                    AddReason(fact.ReasonCodes, BuildingSemanticReasonCodes.InvalidGeometry);
                }
                if ((fact.Geometry.IsClosed || fact.Geometry.Kind == GeometryKind.Polygon) && fact.Geometry.Paths.Count > 1)
                    AddReason(fact.ReasonCodes, BuildingSemanticReasonCodes.GeometryAreaRequiresLoopTopology);
                snapshot.Facts.Add(fact);
            }

            snapshot.Facts.AddRange(WallLoopGeometryBuilder.Build(source));

            snapshot.Facts = snapshot.Facts
                .OrderBy(item => item.Source?.StablePath ?? string.Empty, StringComparer.Ordinal)
                .ThenBy(item => item.FeatureKind)
                .ThenBy(item => item.GeometryId, StringComparer.Ordinal)
                .ToList();
            snapshot.ReasonCodes = (source.ReasonCodes ?? new List<string>())
                .Where(value => !string.IsNullOrWhiteSpace(value) && !string.Equals(value, BuildingSemanticReasonCodes.Ok, StringComparison.Ordinal))
                .Distinct(StringComparer.Ordinal)
                .OrderBy(value => value, StringComparer.Ordinal)
                .ToList();

            int invalidCandidates = snapshot.Facts.Count(item => item.IsSemanticCandidate
                && item.ReasonCodes.Contains(BuildingSemanticReasonCodes.InvalidGeometry));
            int invalidFacts = snapshot.Facts.Count(item => item.ReasonCodes.Contains(BuildingSemanticReasonCodes.InvalidGeometry));
            bool unresolvedArea = snapshot.Facts.Any(item => item.ReasonCodes.Contains(BuildingSemanticReasonCodes.GeometryAreaRequiresLoopTopology));
            if (source.Status == AnalysisRunStatus.Failed || snapshot.Facts.Count == 0)
            {
                snapshot.Status = AnalysisRunStatus.Failed;
                if (snapshot.Facts.Count == 0)
                    AddReason(snapshot.ReasonCodes, BuildingSemanticReasonCodes.InvalidGeometry);
            }
            else if (source.Status == AnalysisRunStatus.Review || invalidFacts > 0 || unresolvedArea)
            {
                snapshot.Status = AnalysisRunStatus.Review;
                if (invalidFacts > 0)
                    AddReason(snapshot.ReasonCodes, BuildingSemanticReasonCodes.InvalidGeometry);
                if (unresolvedArea)
                    AddReason(snapshot.ReasonCodes, BuildingSemanticReasonCodes.GeometryAreaRequiresLoopTopology);
            }
            else
            {
                snapshot.Status = AnalysisRunStatus.Accepted;
                snapshot.ReasonCodes.Add(BuildingSemanticReasonCodes.Ok);
            }

            snapshot.Metrics = new GeometryLayerMetrics
            {
                GeometryFactCount = snapshot.Facts.Count,
                SemanticCandidateCount = snapshot.Facts.Count(item => item.IsSemanticCandidate),
                ExactGeometryCount = snapshot.Facts.Count(item => item.Geometry != null && item.Geometry.IsExact),
                ClosedRegionCount = snapshot.Facts.Count(item => item.FeatureKind == GeometryFeatureKind.ClosedRegion),
                InvalidGeometryFactCount = invalidFacts,
                InvalidSemanticCandidateCount = invalidCandidates,
                RelationCount = snapshot.Relations.Count
            };
            snapshot.DeterministicContentHash = RecognitionLayerDeterminism.Compute(snapshot);
            return snapshot;
        }

        public static BuildingGeometrySnapshot CreateFailed(CadPrimitiveSnapshot primitiveSnapshot, IEnumerable<string> reasons)
        {
            CadPrimitiveSnapshot source = primitiveSnapshot ?? new CadPrimitiveSnapshot();
            var snapshot = new BuildingGeometrySnapshot
            {
                GeneratedAtUtc = DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture),
                DeterministicHashAlgorithm = RecognitionLayerDeterminism.CanonicalBinaryV2,
                Status = AnalysisRunStatus.Failed,
                Drawing = RecognitionLayerClone.CloneDrawing(source.Drawing),
                Profile = RecognitionLayerClone.CloneProfile(source.Profile),
                SourcePrimitiveContentHash = source.DeterministicContentHash ?? string.Empty,
                GeometryConfigurationHash = ConfigurationHash,
                FactProviderId = source.FactProviderId ?? string.Empty,
                ReasonCodes = (reasons ?? Enumerable.Empty<string>()).Where(value => !string.IsNullOrWhiteSpace(value)).Distinct(StringComparer.Ordinal).OrderBy(value => value, StringComparer.Ordinal).ToList()
            };
            if (snapshot.ReasonCodes.Count == 0)
                snapshot.ReasonCodes.Add(BuildingSemanticReasonCodes.FactProviderFailed);
            snapshot.DeterministicContentHash = RecognitionLayerDeterminism.Compute(snapshot);
            return snapshot;
        }

        private static string ConfigurationHash => BuildingSemanticStableId.Sha256Text(
            "building-geometry-normalization-v3|wcs|mm|round=6|invalid=reject|area=single-planar-loop-only|wall-loop-snap=5mm|concrete-wall-boundary-supplement=true");

        private static SemanticGeometry NormalizeGeometry(SemanticGeometry input, out bool invalid)
        {
            SemanticGeometry source = RecognitionLayerClone.CloneGeometry(input);
            invalid = false;
            var paths = new List<List<SemanticPoint>>();
            foreach (List<SemanticPoint> sourcePath in source.Paths ?? new List<List<SemanticPoint>>())
            {
                var path = new List<SemanticPoint>();
                if (sourcePath == null || sourcePath.Count == 0)
                    invalid = true;
                foreach (SemanticPoint point in sourcePath ?? new List<SemanticPoint>())
                {
                    if (!SemanticGeometryAlgorithms.IsFinite(point))
                    {
                        invalid = true;
                        continue;
                    }
                    if (path.Count > 0 && SamePoint(path[path.Count - 1], point))
                        continue;
                    path.Add(new SemanticPoint(point.X, point.Y, point.Z));
                }
                if (path.Count > 0)
                    paths.Add(path);
            }
            source.Paths = paths;
            bool singleClosedPath = paths.Count == 1 && (source.IsClosed || source.Kind == GeometryKind.Polygon);
            if (singleClosedPath)
            {
                List<SemanticPoint> path = paths[0];
                if (path.Count > 1 && SamePoint(path[0], path[path.Count - 1]))
                    path.RemoveAt(path.Count - 1);
                double area = Math.Abs(SignedArea(path));
                invalid |= path.Count < 3 || area <= 1e-12 || double.IsNaN(area) || double.IsInfinity(area)
                           || path.Any(point => Math.Abs(point.Z - path[0].Z) > 1e-6);
            }
            else if (paths.Count == 1 && source.Kind != GeometryKind.Point && paths[0].Count < 2)
            {
                invalid = true;
            }
            // A missing/non-finite coordinate must not become a newly invented edge or (0,0,0).
            // Keep the original geometry in L1; quarantine the whole L2 shape.
            if (invalid)
                return new SemanticGeometry
                {
                    Kind = GeometryKind.None,
                    IsExact = false,
                    ExtractionMethod = source.ExtractionMethod + "|rejected_invalid_geometry",
                    Bounds = new SemanticBounds { IsValid = false }
                };
            if (paths.Count > 0)
                source.Bounds = SemanticGeometryAlgorithms.CalculateBounds(paths);
            return source;
        }

        private static GeometryFeatureKind ClassifyFeature(SemanticGeometry geometry)
        {
            if (geometry == null || geometry.Kind == GeometryKind.None)
                return geometry?.Bounds != null && geometry.Bounds.IsValid ? GeometryFeatureKind.BoundsOnly : GeometryFeatureKind.None;
            if (geometry.Kind == GeometryKind.Point)
                return GeometryFeatureKind.Point;
            if (geometry.Paths != null && geometry.Paths.Count > 1)
                return GeometryFeatureKind.MultiPath;
            if (geometry.IsClosed || geometry.Kind == GeometryKind.Polygon)
                return GeometryFeatureKind.ClosedRegion;
            if (geometry.Kind == GeometryKind.Bounds)
                return GeometryFeatureKind.BoundsOnly;
            return GeometryFeatureKind.OpenPath;
        }

        internal static GeometryMeasurements Measure(SemanticGeometry? geometry)
        {
            SemanticGeometry safeGeometry = geometry ?? new SemanticGeometry();
            SemanticBounds bounds = safeGeometry.Bounds ?? new SemanticBounds();
            double length = 0;
            double area = 0;
            bool areaAvailable = (safeGeometry.IsClosed || safeGeometry.Kind == GeometryKind.Polygon)
                                 && safeGeometry.Paths != null && safeGeometry.Paths.Count == 1
                                 && safeGeometry.Paths[0].Count >= 3;
            foreach (List<SemanticPoint> path in safeGeometry.Paths ?? new List<List<SemanticPoint>>())
            {
                for (int index = 1; index < path.Count; index++)
                    length += Distance(path[index - 1], path[index]);
                if (areaAvailable)
                {
                    length += Distance(path[path.Count - 1], path[0]);
                    area += Math.Abs(SignedArea(path));
                }
            }
            return new GeometryMeasurements
            {
                LengthMillimeters = length,
                AreaSquareMillimeters = area,
                AreaIsAvailable = areaAvailable,
                AreaMethod = areaAvailable ? "planar_single_loop_polygon" : "not_available",
                WidthMillimeters = bounds.IsValid ? Math.Max(0, bounds.MaxX - bounds.MinX) : 0,
                HeightMillimeters = bounds.IsValid ? Math.Max(0, bounds.MaxY - bounds.MinY) : 0,
                RepresentativePointWcsMillimeters = SemanticGeometryAlgorithms.RepresentativePoint(safeGeometry)
            };
        }

        private static double SignedArea(IReadOnlyList<SemanticPoint> path)
        {
            double sum = 0;
            for (int index = 0; index < path.Count; index++)
            {
                SemanticPoint current = path[index];
                SemanticPoint next = path[(index + 1) % path.Count];
                sum += current.X * next.Y - next.X * current.Y;
            }
            return sum * 0.5;
        }

        private static double Distance(SemanticPoint first, SemanticPoint second)
        {
            double dx = first.X - second.X;
            double dy = first.Y - second.Y;
            double dz = first.Z - second.Z;
            return Math.Sqrt(dx * dx + dy * dy + dz * dz);
        }

        private static bool SamePoint(SemanticPoint first, SemanticPoint second)
        {
            return first.X == second.X && first.Y == second.Y && first.Z == second.Z;
        }

        private static void AddReason(ICollection<string> reasons, string reason)
        {
            if (!reasons.Contains(reason))
                reasons.Add(reason);
        }
    }

    public static class GeometryFactCompatibility
    {
        public static List<CadFact> ToCadFacts(BuildingGeometrySnapshot snapshot)
        {
            return ToCadFacts(snapshot, null);
        }

        public static List<CadFact> ToCadFacts(BuildingGeometrySnapshot snapshot, ProjectProfile? profile)
        {
            if (snapshot == null)
                return new List<CadFact>();
            var result = new List<CadFact>();
            foreach (GeometryFact geometryFact in snapshot.Facts
                         .Where(item => item.IsSemanticCandidate)
                         .Where(item => !IsHiddenByXclip(item))
                         .OrderBy(item => item.Source?.StablePath ?? string.Empty, StringComparer.Ordinal)
                         .ThenBy(item => item.GeometryId, StringComparer.Ordinal))
            {
                if (!Enum.TryParse(geometryFact.AdapterRoleHint, true, out CadFactKind kind) || kind == CadFactKind.Unknown)
                    continue;
                result.Add(CreateFact(snapshot, geometryFact, kind, string.Empty, geometryFact.RawText, geometryFact.ExtractionConfidence));
            }

            AppendStandardRoofLinePromotions(snapshot, result);
            AppendProfilePromotions(snapshot, profile, result);
            return result;
        }

        private static void AppendStandardRoofLinePromotions(
            BuildingGeometrySnapshot snapshot,
            ICollection<CadFact> result)
        {
            foreach (GeometryFact geometryFact in (snapshot.Facts ?? new List<GeometryFact>())
                         .Where(item => !item.IsSemanticCandidate)
                         .Where(item => !IsHiddenByXclip(item))
                         .Where(item => string.Equals(item.Source?.NormalizedLayer, "A-Roof", StringComparison.OrdinalIgnoreCase))
                         .Where(item => string.Equals(item.Source?.NativeClassName, "AcDbPolyline", StringComparison.OrdinalIgnoreCase))
                         .Where(item => item.FeatureKind == GeometryFeatureKind.OpenPath
                                        || item.FeatureKind == GeometryFeatureKind.ClosedRegion)
                         .Where(item => SemanticGeometryAlgorithms.IsUsable(item.Geometry, true))
                         .OrderBy(item => item.Source?.StablePath ?? string.Empty, StringComparer.Ordinal)
                         .ThenBy(item => item.GeometryId, StringComparer.Ordinal))
            {
                CadFact roofLine = CreateFact(
                    snapshot,
                    geometryFact,
                    CadFactKind.RoofLine,
                    "standard-a-roof-polyline",
                    string.Empty,
                    Math.Min(geometryFact.ExtractionConfidence, 0.90));
                roofLine.Properties["classification"] = "Unclassified";
                roofLine.Evidence.Add(new SemanticEvidence
                {
                    Code = "STANDARD_A_ROOF_POLYLINE",
                    Kind = "layer_and_native_geometry",
                    Value = "A-Roof/AcDbPolyline/" + geometryFact.FeatureKind,
                    SourceHandle = geometryFact.Source?.Handle ?? string.Empty,
                    Weight = 0.90
                });
                result.Add(roofLine);
            }
        }

        private static void AppendProfilePromotions(
            BuildingGeometrySnapshot snapshot,
            ProjectProfile? profile,
            ICollection<CadFact> result)
        {
            List<GeometrySemanticRule> rules = (profile?.GeometrySemanticRules ?? new List<GeometrySemanticRule>())
                .OrderBy(item => item.Id ?? string.Empty, StringComparer.Ordinal)
                .ToList();
            if (rules.Count == 0)
                return;

            List<GeometryFact> textFacts = (snapshot.Facts ?? new List<GeometryFact>())
                .Where(item => string.Equals(item.AdapterRoleHint, CadFactKind.Text.ToString(), StringComparison.OrdinalIgnoreCase))
                .Where(item => !IsHiddenByXclip(item))
                .Where(item => !string.IsNullOrWhiteSpace(item.RawText))
                .Where(item => TryGetPoint(item, out _))
                .OrderBy(item => item.Source?.StablePath ?? string.Empty, StringComparer.Ordinal)
                .ThenBy(item => item.GeometryId, StringComparer.Ordinal)
                .ToList();

            foreach (GeometryFact geometryFact in (snapshot.Facts ?? new List<GeometryFact>())
                         .Where(item => !item.IsSemanticCandidate)
                         .Where(item => !IsHiddenByXclip(item))
                         .OrderBy(item => item.Source?.StablePath ?? string.Empty, StringComparer.Ordinal)
                         .ThenBy(item => item.GeometryId, StringComparer.Ordinal))
            {
                var matches = new List<CadFact>();
                foreach (GeometrySemanticRule rule in rules)
                {
                    if (TryCreatePromotedFact(snapshot, geometryFact, rule, textFacts, profile, out CadFact? promoted))
                        matches.Add(promoted!);
                }

                // 一份未命名几何只能由一条配置规则赋予工程含义；重叠规则按失败关闭处理。
                if (matches.Count == 1)
                    result.Add(matches[0]);
            }
        }

        private static bool TryCreatePromotedFact(
            BuildingGeometrySnapshot snapshot,
            GeometryFact geometryFact,
            GeometrySemanticRule rule,
            IReadOnlyList<GeometryFact> textFacts,
            ProjectProfile? profile,
            out CadFact? promoted)
        {
            promoted = null;
            if (!Enum.TryParse(rule.SemanticType, true, out CadFactKind kind) || kind == CadFactKind.Unknown)
                return false;
            if (!MatchesGeometryRule(geometryFact, rule, false))
                return false;

            string rawLabel = geometryFact.RawText ?? string.Empty;
            GeometryFact? labelFact = null;
            RoomUseMatch? labelMatch = null;
            GeometryFact? areaFact = null;
            double areaTextSquareMeters = 0;
            if (rule.LabelMode == GeometrySemanticLabelMode.UniqueContainedRoomUse)
            {
                List<GeometryFact> labels = textFacts
                    .Where(item => Contains(rule.LabelLayers, item.Source?.NormalizedLayer ?? string.Empty))
                    .Where(item => TryGetPoint(item, out SemanticPoint? point)
                                   && SemanticGeometryAlgorithms.ContainsPoint(geometryFact.Geometry, point))
                    .GroupBy(item => item.Source?.StablePath ?? item.GeometryId ?? string.Empty, StringComparer.Ordinal)
                    .Select(group => group.First())
                    .ToList();
                labelMatch = labels.Count == 1 ? RoomUseClassifier.Match(labels[0].RawText, profile) : null;
                if (labels.Count != 1
                    || labelMatch == null
                    || !labelMatch.IsMatch
                    || !TryGetPoint(labels[0], out SemanticPoint? labelPoint)
                    || !IsPreferredBoundary(snapshot, geometryFact, rule, labelPoint!, labelMatch.SemanticType == SemanticObjectType.Shaft))
                    return false;

                labelFact = labels[0];
                rawLabel = labelFact.RawText ?? string.Empty;
            }
            else if (rule.LabelMode == GeometrySemanticLabelMode.UniqueContainedRoomUseAndArea)
            {
                List<GeometryFact> labels = textFacts
                    .Where(item => Contains(rule.LabelLayers, item.Source?.NormalizedLayer ?? string.Empty))
                    .Where(item => RoomUseClassifier.Match(item.RawText, profile).IsMatch)
                    .Where(item => TryGetPoint(item, out SemanticPoint? point)
                                   && SemanticGeometryAlgorithms.ContainsPoint(geometryFact.Geometry, point))
                    .GroupBy(item => item.Source?.StablePath ?? item.GeometryId ?? string.Empty, StringComparer.Ordinal)
                    .Select(group => group.First())
                    .ToList();
                if (labels.Count != 1)
                    return false;

                double geometryAreaSquareMeters = geometryFact.Measurements.AreaSquareMillimeters / 1000000.0;
                List<(GeometryFact Fact, double AreaSquareMeters)> areaLabels = textFacts
                    .Where(item => Contains(rule.AreaLabelLayers, item.Source?.NormalizedLayer ?? string.Empty))
                    .Where(item => TryGetPoint(item, out SemanticPoint? point)
                                   && SemanticGeometryAlgorithms.ContainsPoint(geometryFact.Geometry, point))
                    .Select(item =>
                    {
                        bool parsed = TryReadAreaSquareMeters(item.RawText, out double value);
                        return new { Fact = item, Parsed = parsed, Value = value };
                    })
                    .Where(item => item.Parsed
                                   && RelativeDifference(item.Value, geometryAreaSquareMeters)
                                   <= rule.MaximumAreaLabelRelativeDifference)
                    .GroupBy(item => item.Fact.Source?.StablePath ?? item.Fact.GeometryId ?? string.Empty, StringComparer.Ordinal)
                    .Select(group => (group.First().Fact, group.First().Value))
                    .ToList();
                if (areaLabels.Count != 1)
                    return false;

                labelFact = labels[0];
                areaFact = areaLabels[0].Fact;
                areaTextSquareMeters = areaLabels[0].AreaSquareMeters;
                rawLabel = labelFact.RawText ?? string.Empty;
            }

            bool smallShaftAreaException = labelMatch?.SemanticType == SemanticObjectType.Shaft
                                           && geometryFact.Measurements.AreaSquareMillimeters > 0
                                           && geometryFact.Measurements.AreaSquareMillimeters < rule.MinimumAreaSquareMillimeters
                                           && geometryFact.Measurements.AreaSquareMillimeters <= rule.MaximumAreaSquareMillimeters;
            if (!MatchesGeometryRule(geometryFact, rule) && !smallShaftAreaException)
                return false;

            promoted = CreateFact(
                snapshot,
                geometryFact,
                kind,
                rule.Id ?? string.Empty,
                rawLabel,
                Math.Min(geometryFact.ExtractionConfidence, rule.Confidence));
            promoted.Properties["semantic_geometry_rule_id"] = rule.Id ?? string.Empty;
            if (kind == CadFactKind.Wall && !string.IsNullOrWhiteSpace(rule.Classification))
                promoted.Properties["wall_class"] = rule.Classification;
            promoted.Evidence.Add(new SemanticEvidence
            {
                Code = "PROJECT_GEOMETRY_SEMANTIC_RULE",
                Kind = "profile_rule",
                Value = (rule.Id ?? string.Empty) + "=>" + kind,
                SourceHandle = geometryFact.Source?.Handle ?? string.Empty,
                Weight = rule.Confidence
            });

            if (labelFact != null)
            {
                promoted.Properties["contained_room_label"] = rawLabel;
                promoted.Evidence.Add(new SemanticEvidence
                {
                    Code = "ROOM_LABEL_CONTAINED_TEXT",
                    Kind = "spatial_text",
                    Value = rawLabel,
                    SourceHandle = labelFact.Source?.Handle ?? string.Empty,
                    Weight = 0.95
                });
            }
            if (smallShaftAreaException)
            {
                promoted.Evidence.Add(new SemanticEvidence
                {
                    Code = "SHAFT_LABEL_SMALL_WALL_LOOP",
                    Kind = "geometry_policy",
                    Value = geometryFact.Measurements.AreaSquareMillimeters.ToString("R", CultureInfo.InvariantCulture),
                    SourceHandle = labelFact?.Source?.Handle ?? string.Empty,
                    Weight = 0.90
                });
            }
            if (areaFact != null)
            {
                promoted.Properties["area_text_square_meters"] = areaTextSquareMeters.ToString("R", CultureInfo.InvariantCulture);
                promoted.Evidence.Add(new SemanticEvidence
                {
                    Code = "ROOM_AREA_TEXT_MATCH",
                    Kind = "spatial_text_measurement",
                    Value = areaFact.RawText ?? string.Empty,
                    SourceHandle = areaFact.Source?.Handle ?? string.Empty,
                    Weight = 0.95
                });
            }
            return true;
        }

        private static CadFact CreateFact(
            BuildingGeometrySnapshot snapshot,
            GeometryFact geometryFact,
            CadFactKind kind,
            string ruleId,
            string? rawLabel,
            double confidence)
        {
            var fact = new CadFact
            {
                FactId = string.IsNullOrWhiteSpace(ruleId) && !string.IsNullOrWhiteSpace(geometryFact.CompatibilityFactId)
                    ? geometryFact.CompatibilityFactId
                    : BuildingSemanticStableId.Create(
                        "fact",
                        snapshot.Drawing?.Sha256 ?? string.Empty,
                        geometryFact.GeometryId ?? string.Empty,
                        kind.ToString(),
                        ruleId ?? string.Empty),
                Kind = kind,
                Source = RecognitionLayerClone.CloneSource(geometryFact.Source),
                Geometry = RecognitionLayerClone.CloneGeometry(geometryFact.Geometry),
                RawLabel = rawLabel ?? string.Empty,
                Confidence = confidence,
                Properties = new Dictionary<string, string>(geometryFact.RawProperties ?? new Dictionary<string, string>(), StringComparer.Ordinal),
                Evidence = (geometryFact.Evidence ?? new List<SemanticEvidence>()).Select(RecognitionLayerClone.CloneEvidence).ToList(),
                ReasonCodes = new List<string>(geometryFact.ReasonCodes ?? new List<string>())
            };
            fact.Evidence.Add(new SemanticEvidence
            {
                Code = "GEOMETRY_FACT_SOURCE",
                Kind = "geometry_fact",
                Value = geometryFact.GeometryId ?? string.Empty,
                SourceHandle = geometryFact.Source?.Handle ?? string.Empty,
                Weight = geometryFact.ExtractionConfidence
            });
            return fact;
        }

        private static bool MatchesGeometryRule(GeometryFact fact, GeometrySemanticRule rule, bool requireAreaBounds = true)
        {
            return Contains(rule.NormalizedLayers, fact.Source?.NormalizedLayer ?? string.Empty)
                   && (rule.NativeClassNames == null
                       || rule.NativeClassNames.Count == 0
                       || Contains(rule.NativeClassNames, fact.Source?.NativeClassName ?? string.Empty))
                   && rule.FeatureKinds != null
                   && rule.FeatureKinds.Contains(fact.FeatureKind)
                   && HasRequiredProperties(fact.RawProperties, rule.RequiredProperties)
                   && (!rule.RequireClosed || (fact.Geometry?.IsClosed ?? false))
                   && (!rule.RequireExact || (fact.Geometry?.IsExact ?? false))
                   && fact.Measurements != null
                   && fact.Measurements.AreaIsAvailable
                   && (!requireAreaBounds
                       || fact.Measurements.AreaSquareMillimeters >= rule.MinimumAreaSquareMillimeters
                       && fact.Measurements.AreaSquareMillimeters <= rule.MaximumAreaSquareMillimeters);
        }

        private static bool IsPreferredBoundary(
            BuildingGeometrySnapshot snapshot,
            GeometryFact candidate,
            GeometrySemanticRule rule,
            SemanticPoint labelPoint,
            bool allowBelowMinimumArea = false)
        {
            double area = candidate.Measurements.AreaSquareMillimeters;
            return !(snapshot.Facts ?? new List<GeometryFact>())
                .Where(item => !item.IsSemanticCandidate)
                .Where(item => !string.Equals(item.GeometryId, candidate.GeometryId, StringComparison.Ordinal))
                .Where(item => MatchesGeometryRule(item, rule, !allowBelowMinimumArea))
                .Where(item => item.Measurements.AreaSquareMillimeters > 0
                               && item.Measurements.AreaSquareMillimeters <= rule.MaximumAreaSquareMillimeters)
                .Where(item => SemanticGeometryAlgorithms.ContainsPoint(item.Geometry, labelPoint))
                .Any(item => item.Measurements.AreaSquareMillimeters < area - 1e-6
                             || Math.Abs(item.Measurements.AreaSquareMillimeters - area) <= 1e-6
                             && string.CompareOrdinal(item.GeometryId, candidate.GeometryId) < 0);
        }

        private static bool HasRequiredProperties(
            IReadOnlyDictionary<string, string>? actual,
            IReadOnlyDictionary<string, string>? required)
        {
            foreach (KeyValuePair<string, string> item in required ?? new Dictionary<string, string>())
            {
                if (actual == null
                    || !actual.TryGetValue(item.Key, out string? value)
                    || !string.Equals(value?.Trim(), item.Value?.Trim(), StringComparison.OrdinalIgnoreCase))
                {
                    return false;
                }
            }
            return true;
        }

        private static bool TryGetPoint(GeometryFact fact, out SemanticPoint? point)
        {
            point = fact?.Geometry?.Bounds?.IsValid == true
                ? fact.Measurements?.RepresentativePointWcsMillimeters
                : fact?.Geometry?.Paths?.FirstOrDefault()?.FirstOrDefault();
            return point != null
                   && !double.IsNaN(point.X)
                   && !double.IsInfinity(point.X)
                   && !double.IsNaN(point.Y)
                   && !double.IsInfinity(point.Y);
        }

        private static bool Contains(IEnumerable<string>? values, string candidate)
        {
            return (values ?? Enumerable.Empty<string>())
                .Any(value => string.Equals(value, candidate, StringComparison.OrdinalIgnoreCase));
        }

        private static bool IsHiddenByXclip(GeometryFact fact)
        {
            return fact?.RawProperties != null
                   && fact.RawProperties.TryGetValue("xclip_visibility", out string? value)
                   && string.Equals(value, "hidden", StringComparison.OrdinalIgnoreCase);
        }

        private static bool TryReadAreaSquareMeters(string rawText, out double value)
        {
            value = 0;
            Match match = Regex.Match(
                (rawText ?? string.Empty).Replace(',', '.'),
                @"(?<![\d.])(\d+(?:\.\d+)?)\s*(?:m|㎡|%%140)",
                RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);
            return match.Success
                   && double.TryParse(match.Groups[1].Value, NumberStyles.Float, CultureInfo.InvariantCulture, out value)
                   && value > 0;
        }

        private static double RelativeDifference(double first, double second)
        {
            return Math.Abs(first - second) / Math.Max(Math.Max(Math.Abs(first), Math.Abs(second)), 1e-9);
        }
    }

    /// <summary>
    /// 第三层策略：在几何事实进入语义映射前才写入墙、分区、门窗及
    /// 防火/人防分类。第一层和第二层不会包含这些最终工程结论。
    /// </summary>
    public static class SemanticClassificationPolicy
    {
        public static void Apply(CadFact fact)
        {
            if (fact == null)
                return;
            fact.Properties = fact.Properties ?? new Dictionary<string, string>(StringComparer.Ordinal);
            string material = string.Join("|", new[]
            {
                fact.Source?.RawLayer,
                fact.Source?.EffectiveLayer,
                fact.Source?.NormalizedLayer,
                fact.RawLabel,
                fact.Source?.NativeDxfName,
                fact.Source?.NativeClassName,
                string.Join("|", fact.Properties.Values)
            }).ToUpperInvariant();

            bool civilDefense = ContainsAny(material, "人防", "防护", "CIVILDEFENSE", "CIVIL_DEFENSE")
                                || SemanticSensitivityPolicy.HasCivilDefenseEvidence(fact.Properties);
            bool fire = ContainsAny(material, "防火", "FIRE")
                        || SemanticSensitivityPolicy.HasFireEvidence(fact.Properties);
            bool masonry = ContainsAny(material, "加气块", "砌块", "砖墙", "MASONRY", "BRICK");

            if (fact.Kind == CadFactKind.Wall && !HasValue(fact.Properties, "wall_class"))
            {
                fact.Properties["wall_class"] = civilDefense
                    ? WallClassification.CivilDefense.ToString()
                    : fire ? WallClassification.Fire.ToString()
                    : masonry ? WallClassification.Masonry.ToString()
                    : WallClassification.Unknown.ToString();
            }
            if (fact.Kind == CadFactKind.Zone && !HasValue(fact.Properties, "zone_class"))
            {
                fact.Properties["zone_class"] = civilDefense
                    ? ZoneClassification.CivilDefense.ToString()
                    : fire ? ZoneClassification.Fire.ToString() : ZoneClassification.Unknown.ToString();
            }
            if (fact.Kind == CadFactKind.Opening || fact.Kind == CadFactKind.Door || fact.Kind == CadFactKind.Window)
            {
                if (!HasValue(fact.Properties, "opening_kind"))
                {
                    if (fact.Kind == CadFactKind.Door || ContainsAny(material, "DOOR", "门"))
                        fact.Properties["opening_kind"] = "door";
                    else if (fact.Kind == CadFactKind.Window || ContainsAny(material, "WINDOW", "WIND", "窗"))
                        fact.Properties["opening_kind"] = "window";
                    else
                        fact.Properties["opening_kind"] = "unknown";
                }
                if (fire)
                    fact.Properties["fire_protection"] = "true";
                if (civilDefense)
                    fact.Properties["civil_defense"] = "true";
            }
        }

        private static bool HasValue(IDictionary<string, string> values, string key)
        {
            return values.TryGetValue(key, out string? value) && !string.IsNullOrWhiteSpace(value);
        }

        private static bool ContainsAny(string value, params string[] terms)
        {
            string normalized = (value ?? string.Empty).ToUpperInvariant();
            return terms.Any(term => normalized.Contains(term.ToUpperInvariant()));
        }
    }

    public static class RecognitionLayerProvenance
    {
        public static void Apply(BuildingRecognitionBundle bundle, string producerBinarySha256)
        {
            if (bundle == null)
                throw new ArgumentNullException(nameof(bundle));
            if (bundle.PrimitiveSnapshot != null)
            {
                bundle.PrimitiveSnapshot.ProducerBinarySha256 = producerBinarySha256 ?? string.Empty;
                bundle.PrimitiveSnapshot.DeterministicContentHash = RecognitionLayerDeterminism.Compute(bundle.PrimitiveSnapshot);
            }
            if (bundle.GeometrySnapshot != null)
            {
                bundle.GeometrySnapshot.ProducerBinarySha256 = producerBinarySha256 ?? string.Empty;
                bundle.GeometrySnapshot.SourcePrimitiveContentHash = bundle.PrimitiveSnapshot?.DeterministicContentHash ?? string.Empty;
                bundle.GeometrySnapshot.DeterministicContentHash = RecognitionLayerDeterminism.Compute(bundle.GeometrySnapshot);
            }
        }
    }

    public static class RecognitionLayerIntegrityPolicy
    {
        public static void Apply(
            BuildingRecognitionBundle bundle,
            string hashBefore,
            string hashAfter,
            int dbmodBefore,
            int dbmodAfter,
            ScanInputMode inputMode,
            bool inputDatabaseReadOnly)
        {
            if (bundle == null)
                throw new ArgumentNullException(nameof(bundle));
            var integrity = new ScanIntegrityEvidence
            {
                SourceHashBefore = hashBefore ?? string.Empty,
                SourceHashAfter = hashAfter ?? string.Empty,
                SourceBytesUnchanged = string.Equals(hashBefore, hashAfter, StringComparison.OrdinalIgnoreCase),
                ScanInputMode = inputMode,
                InputDatabaseReadOnly = inputDatabaseReadOnly,
                DbmodBefore = dbmodBefore,
                DbmodAfter = dbmodAfter,
                DbmodCleanAtStart = dbmodBefore == 0,
                DbmodUnchanged = dbmodBefore >= 0 && dbmodAfter >= 0 && dbmodBefore == dbmodAfter
            };
            bundle.PrimitiveSnapshot.Integrity = CloneIntegrity(integrity);
            bundle.GeometrySnapshot.Integrity = CloneIntegrity(integrity);

            var failures = new List<string>();
            if (dbmodBefore < 0 || dbmodAfter < 0)
                failures.Add(BuildingSemanticReasonCodes.DbmodEvidenceUnavailable);
            if (inputMode == ScanInputMode.ActiveDocument && dbmodBefore != 0)
                failures.Add(BuildingSemanticReasonCodes.SourceDrawingDirty);
            if (inputMode == ScanInputMode.DiskSideDatabase && !inputDatabaseReadOnly)
                failures.Add(BuildingSemanticReasonCodes.ScanInputNotReadOnly);
            if (!integrity.SourceBytesUnchanged || dbmodBefore >= 0 && dbmodAfter >= 0 && !integrity.DbmodUnchanged)
                failures.Add(BuildingSemanticReasonCodes.SourceModifiedDuringScan);

            if (failures.Count > 0)
            {
                bundle.PrimitiveSnapshot.Status = AnalysisRunStatus.Failed;
                bundle.GeometrySnapshot.Status = AnalysisRunStatus.Failed;
                bundle.PrimitiveSnapshot.ReasonCodes.RemoveAll(code => code == BuildingSemanticReasonCodes.Ok);
                bundle.GeometrySnapshot.ReasonCodes.RemoveAll(code => code == BuildingSemanticReasonCodes.Ok);
                foreach (string failure in failures.Distinct(StringComparer.Ordinal))
                {
                    AddReason(bundle.PrimitiveSnapshot.ReasonCodes, failure);
                    AddReason(bundle.GeometrySnapshot.ReasonCodes, failure);
                }
            }
            bundle.PrimitiveSnapshot.ReasonCodes = bundle.PrimitiveSnapshot.ReasonCodes.Distinct(StringComparer.Ordinal).OrderBy(value => value, StringComparer.Ordinal).ToList();
            bundle.GeometrySnapshot.ReasonCodes = bundle.GeometrySnapshot.ReasonCodes.Distinct(StringComparer.Ordinal).OrderBy(value => value, StringComparer.Ordinal).ToList();
            bundle.PrimitiveSnapshot.DeterministicContentHash = RecognitionLayerDeterminism.Compute(bundle.PrimitiveSnapshot);
            bundle.GeometrySnapshot.SourcePrimitiveContentHash = bundle.PrimitiveSnapshot.DeterministicContentHash;
            bundle.GeometrySnapshot.DeterministicContentHash = RecognitionLayerDeterminism.Compute(bundle.GeometrySnapshot);
        }

        private static ScanIntegrityEvidence CloneIntegrity(ScanIntegrityEvidence source)
        {
            return new ScanIntegrityEvidence
            {
                SourceHashBefore = source.SourceHashBefore,
                SourceHashAfter = source.SourceHashAfter,
                SourceBytesUnchanged = source.SourceBytesUnchanged,
                ScanInputMode = source.ScanInputMode,
                InputDatabaseReadOnly = source.InputDatabaseReadOnly,
                DbmodBefore = source.DbmodBefore,
                DbmodAfter = source.DbmodAfter,
                DbmodCleanAtStart = source.DbmodCleanAtStart,
                DbmodUnchanged = source.DbmodUnchanged
            };
        }

        private static void AddReason(ICollection<string> values, string value)
        {
            if (!values.Contains(value))
                values.Add(value);
        }
    }

    public static class RecognitionLayerDeterminism
    {
        public const string CanonicalBinaryV2 = "canonical-binary-v2";
        public const string LegacyTextV1 = "legacy-text-v1";

        public static string Compute(CadPrimitiveSnapshot snapshot)
        {
            return ComputeCanonicalBinaryV2(snapshot);
        }

        public static string Compute(BuildingGeometrySnapshot snapshot)
        {
            return ComputeCanonicalBinaryV2(snapshot);
        }

        internal static string ComputeLegacyTextV1(CadPrimitiveSnapshot snapshot)
        {
            if (snapshot == null)
                throw new ArgumentNullException(nameof(snapshot));
            using (var builder = new DeterministicHashTextWriter())
            {
                Append(builder, snapshot.SchemaVersion, snapshot.Producer, snapshot.ProducerVersion, snapshot.ProducerBinarySha256,
                    snapshot.Status.ToString(), snapshot.ExtractionConfigurationHash, snapshot.FactProviderId);
                AppendDrawing(builder, snapshot.Drawing);
                AppendIntegrity(builder, snapshot.Integrity);
                foreach (string reason in snapshot.ReasonCodes.OrderBy(value => value, StringComparer.Ordinal))
                    Append(builder, "reason", reason);
                foreach (CadPrimitive primitive in snapshot.Primitives.OrderBy(value => value.PrimitiveId, StringComparer.Ordinal))
                {
                    Append(builder, "primitive", primitive.PrimitiveId, primitive.SourceFactId, primitive.Kind.ToString(),
                        primitive.AdapterRoleHint, primitive.IsSemanticCandidate.ToString(), Number(primitive.ExtractionConfidence), primitive.RawText);
                    AppendSource(builder, primitive.Source);
                    AppendGeometry(builder, primitive.RawGeometry);
                    foreach (KeyValuePair<string, string> property in primitive.RawProperties.OrderBy(value => value.Key, StringComparer.Ordinal))
                        Append(builder, "property", property.Key, property.Value);
                    AppendEvidenceAndReasons(builder, primitive.Evidence, primitive.ReasonCodes, "primitive");
                }
                AppendProxyAndDiagnostics(builder, snapshot.ProxyLedger, snapshot.ProviderDiagnostics);
                PrimitiveLayerMetrics metrics = snapshot.Metrics ?? new PrimitiveLayerMetrics();
                Append(builder, "metrics", Number(metrics.PrimitiveCount), Number(metrics.SemanticCandidateCount),
                    Number(metrics.TextCount), Number(metrics.BlockReferenceCount), Number(metrics.ProxyOrNativeObjectCount),
                    Number(metrics.WithRawGeometryCount), Number(metrics.ProxyLedgerCount));
                return builder.Finish();
            }
        }

        internal static string ComputeLegacyTextV1(BuildingGeometrySnapshot snapshot)
        {
            if (snapshot == null)
                throw new ArgumentNullException(nameof(snapshot));
            using (var builder = new DeterministicHashTextWriter())
            {
                Append(builder, snapshot.SchemaVersion, snapshot.Producer, snapshot.ProducerVersion, snapshot.ProducerBinarySha256,
                    snapshot.Status.ToString(), snapshot.SourcePrimitiveContentHash, snapshot.GeometryConfigurationHash, snapshot.FactProviderId);
                AppendDrawing(builder, snapshot.Drawing);
                AppendIntegrity(builder, snapshot.Integrity);
                foreach (string reason in snapshot.ReasonCodes.OrderBy(value => value, StringComparer.Ordinal))
                    Append(builder, "reason", reason);
                foreach (GeometryFact fact in snapshot.Facts.OrderBy(value => value.GeometryId, StringComparer.Ordinal))
                {
                    Append(builder, "geometry_fact", fact.GeometryId, fact.CompatibilityFactId, fact.FeatureKind.ToString(),
                        fact.AdapterRoleHint, fact.IsSemanticCandidate.ToString(), Number(fact.ExtractionConfidence), fact.RawText);
                    foreach (string primitiveId in fact.SourcePrimitiveIds.OrderBy(value => value, StringComparer.Ordinal))
                        Append(builder, "source_primitive", primitiveId);
                    AppendSource(builder, fact.Source);
                    AppendGeometry(builder, fact.Geometry);
                    GeometryMeasurements measure = fact.Measurements ?? new GeometryMeasurements();
                    Append(builder, "measure", Number(measure.LengthMillimeters), Number(measure.AreaSquareMillimeters),
                        measure.AreaIsAvailable.ToString(), measure.AreaMethod,
                        Number(measure.WidthMillimeters), Number(measure.HeightMillimeters), Number(measure.RepresentativePointWcsMillimeters?.X ?? 0),
                        Number(measure.RepresentativePointWcsMillimeters?.Y ?? 0), Number(measure.RepresentativePointWcsMillimeters?.Z ?? 0));
                    foreach (KeyValuePair<string, string> property in fact.RawProperties.OrderBy(value => value.Key, StringComparer.Ordinal))
                        Append(builder, "property", property.Key, property.Value);
                    AppendEvidenceAndReasons(builder, fact.Evidence, fact.ReasonCodes, "geometry");
                }
                foreach (GeometryRelation relation in snapshot.Relations.OrderBy(value => value.RelationId, StringComparer.Ordinal))
                {
                    Append(builder, "relation", relation.RelationId, relation.Type.ToString(), relation.FromGeometryId,
                        relation.ToGeometryId, Number(relation.DistanceMillimeters), Number(relation.Confidence));
                    foreach (string reason in relation.ReasonCodes.OrderBy(value => value, StringComparer.Ordinal))
                        Append(builder, "relation_reason", reason);
                }
                foreach (ProviderDiagnostic diagnostic in snapshot.ProviderDiagnostics.OrderBy(value => value.StablePath, StringComparer.Ordinal)
                             .ThenBy(value => value.ReasonCode, StringComparer.Ordinal).ThenBy(value => value.Message, StringComparer.Ordinal))
                    Append(builder, "diagnostic", diagnostic.StablePath, diagnostic.Severity.ToString(), diagnostic.ReasonCode, diagnostic.Message);
                GeometryLayerMetrics metrics = snapshot.Metrics ?? new GeometryLayerMetrics();
                Append(builder, "metrics", Number(metrics.GeometryFactCount), Number(metrics.SemanticCandidateCount),
                    Number(metrics.ExactGeometryCount), Number(metrics.ClosedRegionCount), Number(metrics.InvalidGeometryFactCount),
                    Number(metrics.InvalidSemanticCandidateCount), Number(metrics.RelationCount));
                return builder.Finish();
            }
        }

        private static string ComputeCanonicalBinaryV2(CadPrimitiveSnapshot snapshot)
        {
            if (snapshot == null)
                throw new ArgumentNullException(nameof(snapshot));
            using (var writer = new CanonicalBinaryHashWriter())
            {
                writer.WriteString("cad-primitives-canonical-binary-v2");
                writer.WriteString(snapshot.DeterministicHashAlgorithm);
                writer.WriteString(snapshot.SchemaVersion);
                writer.WriteString(snapshot.Producer);
                writer.WriteString(snapshot.ProducerVersion);
                writer.WriteString(snapshot.ProducerBinarySha256);
                writer.WriteString(snapshot.Status.ToString());
                writer.WriteString(snapshot.ExtractionConfigurationHash);
                writer.WriteString(snapshot.FactProviderId);
                WriteDrawing(writer, snapshot.Drawing);
                WriteIntegrity(writer, snapshot.Integrity);
                WriteStrings(writer, snapshot.ReasonCodes, true);

                List<CadPrimitive> primitives = (snapshot.Primitives ?? new List<CadPrimitive>())
                    .OrderBy(value => value.PrimitiveId, StringComparer.Ordinal)
                    .ToList();
                writer.WriteInt32(primitives.Count);
                foreach (CadPrimitive primitive in primitives)
                {
                    writer.WriteString(primitive.PrimitiveId);
                    writer.WriteString(primitive.SourceFactId);
                    writer.WriteString(primitive.Kind.ToString());
                    writer.WriteString(primitive.AdapterRoleHint);
                    writer.WriteBoolean(primitive.IsSemanticCandidate);
                    writer.WriteDouble(primitive.ExtractionConfidence);
                    writer.WriteString(primitive.RawText);
                    WriteSource(writer, primitive.Source);
                    WriteGeometry(writer, primitive.RawGeometry);
                    WriteProperties(writer, primitive.RawProperties);
                    WriteEvidence(writer, primitive.Evidence);
                    WriteStrings(writer, primitive.ReasonCodes, true);
                }

                WriteProxies(writer, snapshot.ProxyLedger);
                WriteDiagnostics(writer, snapshot.ProviderDiagnostics);
                PrimitiveLayerMetrics metrics = snapshot.Metrics ?? new PrimitiveLayerMetrics();
                writer.WriteInt32(metrics.PrimitiveCount);
                writer.WriteInt32(metrics.SemanticCandidateCount);
                writer.WriteInt32(metrics.TextCount);
                writer.WriteInt32(metrics.BlockReferenceCount);
                writer.WriteInt32(metrics.ProxyOrNativeObjectCount);
                writer.WriteInt32(metrics.WithRawGeometryCount);
                writer.WriteInt32(metrics.ProxyLedgerCount);
                return writer.Finish();
            }
        }

        private static string ComputeCanonicalBinaryV2(BuildingGeometrySnapshot snapshot)
        {
            if (snapshot == null)
                throw new ArgumentNullException(nameof(snapshot));
            using (var writer = new CanonicalBinaryHashWriter())
            {
                writer.WriteString("building-geometry-canonical-binary-v2");
                writer.WriteString(snapshot.DeterministicHashAlgorithm);
                writer.WriteString(snapshot.SchemaVersion);
                writer.WriteString(snapshot.Producer);
                writer.WriteString(snapshot.ProducerVersion);
                writer.WriteString(snapshot.ProducerBinarySha256);
                writer.WriteString(snapshot.Status.ToString());
                writer.WriteString(snapshot.SourcePrimitiveContentHash);
                writer.WriteString(snapshot.GeometryConfigurationHash);
                writer.WriteString(snapshot.FactProviderId);
                WriteDrawing(writer, snapshot.Drawing);
                WriteIntegrity(writer, snapshot.Integrity);
                WriteStrings(writer, snapshot.ReasonCodes, true);

                List<GeometryFact> facts = (snapshot.Facts ?? new List<GeometryFact>())
                    .OrderBy(value => value.GeometryId, StringComparer.Ordinal)
                    .ToList();
                writer.WriteInt32(facts.Count);
                foreach (GeometryFact fact in facts)
                {
                    writer.WriteString(fact.GeometryId);
                    writer.WriteString(fact.CompatibilityFactId);
                    writer.WriteString(fact.FeatureKind.ToString());
                    writer.WriteString(fact.AdapterRoleHint);
                    writer.WriteBoolean(fact.IsSemanticCandidate);
                    writer.WriteDouble(fact.ExtractionConfidence);
                    writer.WriteString(fact.RawText);
                    WriteStrings(writer, fact.SourcePrimitiveIds, true);
                    WriteSource(writer, fact.Source);
                    WriteGeometry(writer, fact.Geometry);
                    WriteMeasurements(writer, fact.Measurements);
                    WriteProperties(writer, fact.RawProperties);
                    WriteEvidence(writer, fact.Evidence);
                    WriteStrings(writer, fact.ReasonCodes, true);
                }

                List<GeometryRelation> relations = (snapshot.Relations ?? new List<GeometryRelation>())
                    .OrderBy(value => value.RelationId, StringComparer.Ordinal)
                    .ToList();
                writer.WriteInt32(relations.Count);
                foreach (GeometryRelation relation in relations)
                {
                    writer.WriteString(relation.RelationId);
                    writer.WriteString(relation.Type.ToString());
                    writer.WriteString(relation.FromGeometryId);
                    writer.WriteString(relation.ToGeometryId);
                    writer.WriteDouble(relation.DistanceMillimeters);
                    writer.WriteDouble(relation.Confidence);
                    WriteStrings(writer, relation.ReasonCodes, true);
                }

                WriteDiagnostics(writer, snapshot.ProviderDiagnostics);
                GeometryLayerMetrics metrics = snapshot.Metrics ?? new GeometryLayerMetrics();
                writer.WriteInt32(metrics.GeometryFactCount);
                writer.WriteInt32(metrics.SemanticCandidateCount);
                writer.WriteInt32(metrics.ExactGeometryCount);
                writer.WriteInt32(metrics.ClosedRegionCount);
                writer.WriteInt32(metrics.InvalidGeometryFactCount);
                writer.WriteInt32(metrics.InvalidSemanticCandidateCount);
                writer.WriteInt32(metrics.RelationCount);
                return writer.Finish();
            }
        }

        private static void WriteDrawing(CanonicalBinaryHashWriter writer, DrawingIdentity drawing)
        {
            drawing = drawing ?? new DrawingIdentity();
            writer.WriteString(drawing.DrawingId);
            writer.WriteString(drawing.FileName);
            writer.WriteString(drawing.Sha256);
            writer.WriteInt64(drawing.FileLength);
            writer.WriteString(drawing.SourceLastWriteUtc);
            writer.WriteString(drawing.CoordinateSystem);
            writer.WriteString(drawing.GeometryUnits);
        }

        private static void WriteIntegrity(CanonicalBinaryHashWriter writer, ScanIntegrityEvidence integrity)
        {
            integrity = integrity ?? new ScanIntegrityEvidence();
            writer.WriteString(integrity.SourceHashBefore);
            writer.WriteString(integrity.SourceHashAfter);
            writer.WriteBoolean(integrity.SourceBytesUnchanged);
            writer.WriteString(integrity.ScanInputMode.ToString());
            writer.WriteBoolean(integrity.InputDatabaseReadOnly);
            writer.WriteInt32(integrity.DbmodBefore);
            writer.WriteInt32(integrity.DbmodAfter);
            writer.WriteBoolean(integrity.DbmodCleanAtStart);
            writer.WriteBoolean(integrity.DbmodUnchanged);
        }

        private static void WriteSource(CanonicalBinaryHashWriter writer, SourceReference source)
        {
            source = source ?? new SourceReference();
            writer.WriteString(source.DrawingHash);
            writer.WriteString(source.StablePath);
            writer.WriteString(source.Handle);
            writer.WriteString(source.RawLayer);
            writer.WriteString(source.EffectiveLayer);
            writer.WriteString(source.NormalizedLayer);
            writer.WriteString(source.NativeDxfName);
            writer.WriteString(source.NativeClassName);
            WriteStrings(writer, source.BlockPath, false);
            WriteStrings(writer, source.XrefPath, false);
            WriteStrings(writer, source.XrefHashes, false);
            List<double> transform = source.WcsTransform ?? new List<double>();
            writer.WriteInt32(transform.Count);
            foreach (double value in transform)
                writer.WriteDouble(value);
        }

        private static void WriteGeometry(CanonicalBinaryHashWriter writer, SemanticGeometry geometry)
        {
            geometry = geometry ?? new SemanticGeometry();
            writer.WriteString(geometry.Kind.ToString());
            writer.WriteBoolean(geometry.IsClosed);
            writer.WriteBoolean(geometry.IsExact);
            writer.WriteString(geometry.ExtractionMethod);
            SemanticBounds bounds = geometry.Bounds ?? new SemanticBounds();
            writer.WriteBoolean(bounds.IsValid);
            writer.WriteDouble(bounds.MinX);
            writer.WriteDouble(bounds.MinY);
            writer.WriteDouble(bounds.MinZ);
            writer.WriteDouble(bounds.MaxX);
            writer.WriteDouble(bounds.MaxY);
            writer.WriteDouble(bounds.MaxZ);

            List<List<SemanticPoint>> paths = geometry.Paths ?? new List<List<SemanticPoint>>();
            writer.WriteInt32(paths.Count);
            foreach (List<SemanticPoint> path in paths)
            {
                if (path == null)
                {
                    writer.WriteInt32(-1);
                    continue;
                }
                writer.WriteInt32(path.Count);
                foreach (SemanticPoint point in path)
                {
                    writer.WriteBoolean(point != null);
                    if (point == null)
                        continue;
                    writer.WriteDouble(point.X);
                    writer.WriteDouble(point.Y);
                    writer.WriteDouble(point.Z);
                }
            }
        }

        private static void WriteMeasurements(CanonicalBinaryHashWriter writer, GeometryMeasurements measurements)
        {
            measurements = measurements ?? new GeometryMeasurements();
            writer.WriteDouble(measurements.LengthMillimeters);
            writer.WriteDouble(measurements.AreaSquareMillimeters);
            writer.WriteBoolean(measurements.AreaIsAvailable);
            writer.WriteString(measurements.AreaMethod);
            writer.WriteDouble(measurements.WidthMillimeters);
            writer.WriteDouble(measurements.HeightMillimeters);
            SemanticPoint point = measurements.RepresentativePointWcsMillimeters ?? new SemanticPoint();
            writer.WriteDouble(point.X);
            writer.WriteDouble(point.Y);
            writer.WriteDouble(point.Z);
        }

        private static void WriteProperties(CanonicalBinaryHashWriter writer, IDictionary<string, string> properties)
        {
            List<KeyValuePair<string, string>> ordered = (properties ?? new Dictionary<string, string>())
                .OrderBy(value => value.Key, StringComparer.Ordinal)
                .ToList();
            writer.WriteInt32(ordered.Count);
            foreach (KeyValuePair<string, string> property in ordered)
            {
                writer.WriteString(property.Key);
                writer.WriteString(property.Value);
            }
        }

        private static void WriteEvidence(CanonicalBinaryHashWriter writer, IEnumerable<SemanticEvidence> evidence)
        {
            List<SemanticEvidence> ordered = (evidence ?? Enumerable.Empty<SemanticEvidence>())
                .OrderBy(value => value.Code, StringComparer.Ordinal)
                .ThenBy(value => value.Value, StringComparer.Ordinal)
                .ThenBy(value => value.SourceHandle, StringComparer.Ordinal)
                .ThenBy(value => value.Weight)
                .ToList();
            writer.WriteInt32(ordered.Count);
            foreach (SemanticEvidence item in ordered)
            {
                writer.WriteString(item.Code);
                writer.WriteString(item.Kind);
                writer.WriteString(item.Value);
                writer.WriteString(item.SourceHandle);
                writer.WriteDouble(item.Weight);
            }
        }

        private static void WriteStrings(CanonicalBinaryHashWriter writer, IEnumerable<string> values, bool sort)
        {
            IEnumerable<string> source = values ?? Enumerable.Empty<string>();
            List<string> materialized = (sort ? source.OrderBy(value => value, StringComparer.Ordinal) : source).ToList();
            writer.WriteInt32(materialized.Count);
            foreach (string value in materialized)
                writer.WriteString(value);
        }

        private static void WriteProxies(CanonicalBinaryHashWriter writer, IEnumerable<ProxyLedgerEntry> proxies)
        {
            List<ProxyLedgerEntry> ordered = (proxies ?? Enumerable.Empty<ProxyLedgerEntry>())
                .OrderBy(value => value.StablePath, StringComparer.Ordinal)
                .ToList();
            writer.WriteInt32(ordered.Count);
            foreach (ProxyLedgerEntry proxy in ordered)
            {
                writer.WriteString(proxy.StablePath);
                writer.WriteString(proxy.Handle);
                writer.WriteString(proxy.OriginalDxfName);
                writer.WriteString(proxy.OriginalClassName);
                writer.WriteString(proxy.ApplicationDescription);
                writer.WriteString(proxy.EffectiveLayer);
                writer.WriteString(proxy.Disposition.ToString());
                writer.WriteString(proxy.ReasonCode);
            }
        }

        private static void WriteDiagnostics(CanonicalBinaryHashWriter writer, IEnumerable<ProviderDiagnostic> diagnostics)
        {
            List<ProviderDiagnostic> ordered = (diagnostics ?? Enumerable.Empty<ProviderDiagnostic>())
                .OrderBy(value => value.StablePath, StringComparer.Ordinal)
                .ThenBy(value => value.ReasonCode, StringComparer.Ordinal)
                .ThenBy(value => value.Message, StringComparer.Ordinal)
                .ToList();
            writer.WriteInt32(ordered.Count);
            foreach (ProviderDiagnostic diagnostic in ordered)
            {
                writer.WriteString(diagnostic.StablePath);
                writer.WriteString(diagnostic.Severity.ToString());
                writer.WriteString(diagnostic.ReasonCode);
                writer.WriteString(diagnostic.Message);
            }
        }

        private sealed class CanonicalBinaryHashWriter : IDisposable
        {
            private readonly SHA256 _sha = SHA256.Create();
            private readonly CryptoStream _crypto;
            private readonly BufferedStream _buffer;
            private readonly BinaryWriter _writer;
            private bool _finished;

            public CanonicalBinaryHashWriter()
            {
                _crypto = new CryptoStream(Stream.Null, _sha, CryptoStreamMode.Write);
                _buffer = new BufferedStream(_crypto, 65536);
                _writer = new BinaryWriter(_buffer, new UTF8Encoding(false), true);
            }

            public void WriteString(string value)
            {
                EnsureWritable();
                _writer.Write(value ?? string.Empty);
            }

            public void WriteBoolean(bool value)
            {
                EnsureWritable();
                _writer.Write(value);
            }

            public void WriteInt32(int value)
            {
                EnsureWritable();
                _writer.Write(value);
            }

            public void WriteInt64(long value)
            {
                EnsureWritable();
                _writer.Write(value);
            }

            public void WriteDouble(double value)
            {
                EnsureWritable();
                if (double.IsNaN(value))
                {
                    _writer.Write((byte)1);
                    return;
                }
                if (double.IsPositiveInfinity(value))
                {
                    _writer.Write((byte)2);
                    return;
                }
                if (double.IsNegativeInfinity(value))
                {
                    _writer.Write((byte)3);
                    return;
                }
                _writer.Write((byte)0);
                double rounded = Math.Round(value, 6, MidpointRounding.AwayFromZero);
                if (rounded == 0)
                    rounded = 0;
                _writer.Write(BitConverter.DoubleToInt64Bits(rounded));
            }

            public string Finish()
            {
                if (!_finished)
                {
                    _writer.Flush();
                    _buffer.Flush();
                    _crypto.FlushFinalBlock();
                    _finished = true;
                }
                return BuildingSemanticStableId.ToHex(_sha.Hash ?? Array.Empty<byte>());
            }

            public void Dispose()
            {
                if (!_finished)
                    Finish();
                _writer.Dispose();
                _buffer.Dispose();
                _crypto.Dispose();
                _sha.Dispose();
            }

            private void EnsureWritable()
            {
                if (_finished)
                    throw new InvalidOperationException("规范二进制哈希写入器已经结束。");
            }
        }

        private static void AppendDrawing(DeterministicHashTextWriter builder, DrawingIdentity drawing)
        {
            drawing = drawing ?? new DrawingIdentity();
            Append(builder, "drawing", drawing.DrawingId, drawing.FileName, drawing.Sha256,
                drawing.FileLength.ToString(CultureInfo.InvariantCulture), drawing.SourceLastWriteUtc,
                drawing.CoordinateSystem, drawing.GeometryUnits);
            // Profile SHA deliberately does not participate: semantic dictionaries, thresholds and
            // observation regions must not invalidate raw/geometry layer content hashes.
        }

        private static void AppendIntegrity(DeterministicHashTextWriter builder, ScanIntegrityEvidence integrity)
        {
            integrity = integrity ?? new ScanIntegrityEvidence();
            Append(builder, "integrity", integrity.SourceHashBefore, integrity.SourceHashAfter,
                integrity.SourceBytesUnchanged.ToString(), integrity.ScanInputMode.ToString(), integrity.InputDatabaseReadOnly.ToString(),
                integrity.DbmodBefore.ToString(CultureInfo.InvariantCulture), integrity.DbmodAfter.ToString(CultureInfo.InvariantCulture),
                integrity.DbmodCleanAtStart.ToString(), integrity.DbmodUnchanged.ToString());
        }

        private static void AppendSource(DeterministicHashTextWriter builder, SourceReference source)
        {
            source = source ?? new SourceReference();
            Append(builder, "source", source.DrawingHash, source.StablePath, source.Handle, source.RawLayer,
                source.EffectiveLayer, source.NormalizedLayer, source.NativeDxfName, source.NativeClassName);
            foreach (string value in source.BlockPath ?? new List<string>()) Append(builder, "block", value);
            foreach (string value in source.XrefPath ?? new List<string>()) Append(builder, "xref", value);
            foreach (string value in source.XrefHashes ?? new List<string>()) Append(builder, "xref_hash", value);
            foreach (double value in source.WcsTransform ?? new List<double>()) Append(builder, "transform", Number(value));
        }

        private static void AppendGeometry(DeterministicHashTextWriter builder, SemanticGeometry geometry)
        {
            geometry = geometry ?? new SemanticGeometry();
            Append(builder, "geometry", geometry.Kind.ToString(), geometry.IsClosed.ToString(), geometry.IsExact.ToString(), geometry.ExtractionMethod);
            SemanticBounds bounds = geometry.Bounds ?? new SemanticBounds();
            Append(builder, "bounds", bounds.IsValid.ToString(), Number(bounds.MinX), Number(bounds.MinY), Number(bounds.MinZ),
                Number(bounds.MaxX), Number(bounds.MaxY), Number(bounds.MaxZ));
            foreach (List<SemanticPoint> path in geometry.Paths ?? new List<List<SemanticPoint>>())
            {
                Append(builder, "path", path.Count.ToString(CultureInfo.InvariantCulture));
                foreach (SemanticPoint point in path)
                {
                    if (point == null) Append(builder, "missing_point");
                    else Append(builder, Number(point.X), Number(point.Y), Number(point.Z));
                }
            }
        }

        private static void AppendEvidenceAndReasons(DeterministicHashTextWriter builder, IEnumerable<SemanticEvidence> evidence, IEnumerable<string> reasons, string prefix)
        {
            foreach (SemanticEvidence item in (evidence ?? Enumerable.Empty<SemanticEvidence>()).OrderBy(value => value.Code, StringComparer.Ordinal)
                         .ThenBy(value => value.Value, StringComparer.Ordinal).ThenBy(value => value.SourceHandle, StringComparer.Ordinal).ThenBy(value => value.Weight))
                Append(builder, prefix + "_evidence", item.Code, item.Kind, item.Value, item.SourceHandle, Number(item.Weight));
            foreach (string reason in (reasons ?? Enumerable.Empty<string>()).OrderBy(value => value, StringComparer.Ordinal))
                Append(builder, prefix + "_reason", reason);
        }

        private static void AppendProxyAndDiagnostics(DeterministicHashTextWriter builder, IEnumerable<ProxyLedgerEntry> proxies, IEnumerable<ProviderDiagnostic> diagnostics)
        {
            foreach (ProxyLedgerEntry proxy in (proxies ?? Enumerable.Empty<ProxyLedgerEntry>()).OrderBy(value => value.StablePath, StringComparer.Ordinal))
                Append(builder, "proxy", proxy.StablePath, proxy.Handle, proxy.OriginalDxfName, proxy.OriginalClassName,
                    proxy.ApplicationDescription, proxy.EffectiveLayer, proxy.Disposition.ToString(), proxy.ReasonCode);
            foreach (ProviderDiagnostic diagnostic in (diagnostics ?? Enumerable.Empty<ProviderDiagnostic>()).OrderBy(value => value.StablePath, StringComparer.Ordinal)
                         .ThenBy(value => value.ReasonCode, StringComparer.Ordinal).ThenBy(value => value.Message, StringComparer.Ordinal))
                Append(builder, "diagnostic", diagnostic.StablePath, diagnostic.Severity.ToString(), diagnostic.ReasonCode, diagnostic.Message);
        }

        private static void Append(DeterministicHashTextWriter builder, params string[] values)
        {
            foreach (string value in values)
            {
                builder.Write(value ?? string.Empty);
                builder.Write('\u001f');
            }
            builder.Write('\n');
        }

        private sealed class DeterministicHashTextWriter : IDisposable
        {
            private readonly SHA256 _sha = SHA256.Create();
            private readonly CryptoStream _crypto;
            private readonly StreamWriter _writer;
            private bool _finished;

            public DeterministicHashTextWriter()
            {
                _crypto = new CryptoStream(Stream.Null, _sha, CryptoStreamMode.Write);
                _writer = new StreamWriter(_crypto, new UTF8Encoding(false), 65536, true);
            }

            public void Write(string value)
            {
                if (_finished)
                    throw new InvalidOperationException("确定性哈希写入器已经结束。");
                _writer.Write(value ?? string.Empty);
            }

            public void Write(char value)
            {
                if (_finished)
                    throw new InvalidOperationException("确定性哈希写入器已经结束。");
                _writer.Write(value);
            }

            public string Finish()
            {
                if (!_finished)
                {
                    _writer.Flush();
                    _crypto.FlushFinalBlock();
                    _finished = true;
                }
                return BuildingSemanticStableId.ToHex(_sha.Hash ?? Array.Empty<byte>());
            }

            public void Dispose()
            {
                if (!_finished)
                    Finish();
                _writer.Dispose();
                _crypto.Dispose();
                _sha.Dispose();
            }
        }

        private static string Number(double value)
        {
            return Math.Round(value, 6, MidpointRounding.AwayFromZero).ToString("0.######", CultureInfo.InvariantCulture);
        }
    }
}
