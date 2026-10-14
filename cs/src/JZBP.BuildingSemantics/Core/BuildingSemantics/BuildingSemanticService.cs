// SPDX-License-Identifier: MPL-2.0
// Copyright (c) 2026 张田; 著作权人、原作者及维护者：张田；其他贡献者和第三方保留各自权利。
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;

namespace JZBP.BuildingSemantics.Core
{
    public sealed class BuildingSemanticService : IBuildingRecognitionService
    {
        private readonly ICadFactProvider _factProvider;

        public BuildingSemanticService(ICadFactProvider factProvider)
        {
            _factProvider = factProvider ?? throw new ArgumentNullException(nameof(factProvider));
        }

        public BuildingRecognitionBundle AnalyzeLayers(AnalysisRequest? request)
        {
            var layerClock = Stopwatch.StartNew();
            ProfileValidationResult validation = ProjectProfileValidator.Validate(request?.Profile);
            bool canCollect = validation.IsValid
                              && request != null
                              && !string.IsNullOrWhiteSpace(request.DrawingHash)
                              && ProjectProfileValidator.FindDrawing(request.Profile, request.DrawingHash) != null;
            if (!canCollect)
            {
                var reasons = new List<string>(validation.ReasonCodes ?? new List<string>());
                if (request == null || string.IsNullOrWhiteSpace(request.DrawingHash))
                    AddDistinct(reasons, BuildingSemanticReasonCodes.DrawingHashRequired);
                else if (validation.IsValid)
                    AddDistinct(reasons, BuildingSemanticReasonCodes.DrawingHashMismatch);
                CadPrimitiveSnapshot primitiveFailure = CadPrimitiveSnapshotBuilder.CreateFailed(request, reasons);
                return new BuildingRecognitionBundle
                {
                    PrimitiveSnapshot = primitiveFailure,
                    GeometrySnapshot = BuildingGeometryService.CreateFailed(primitiveFailure, reasons),
                    SemanticSnapshot = Analyze(request)
                };
            }

            AnalysisRequest safeRequest = request!;
            DrawingSnapshot drawingSnapshot;
            try
            {
                drawingSnapshot = _factProvider.Collect(new CadFactRequest { Analysis = safeRequest });
            }
            catch (Exception ex)
            {
                drawingSnapshot = DrawingSnapshot.Freeze(new CadFactSnapshot
                {
                    ProviderId = _factProvider.ProviderId,
                    IsSuccess = false,
                    ReasonCodes = new List<string> { BuildingSemanticReasonCodes.FactProviderFailed },
                    Diagnostics = new List<ProviderDiagnostic>
                    {
                        new ProviderDiagnostic
                        {
                            Severity = FindingSeverity.Error,
                            ReasonCode = BuildingSemanticReasonCodes.FactProviderFailed,
                            Message = "CAD 事实适配器异常: " + ex.Message
                        }
                    }
                });
            }

            CadPrimitiveSnapshot primitives = CadPrimitiveSnapshotBuilder.Build(drawingSnapshot, safeRequest);
            BuildingGeometrySnapshot geometry = new BuildingGeometryService().Build(primitives);
            BuildingSemanticSnapshot semantics = AnalyzeCore(safeRequest, drawingSnapshot, geometry);
            semantics.Metrics.AnalysisElapsedMilliseconds = layerClock.ElapsedMilliseconds;
            return new BuildingRecognitionBundle
            {
                PrimitiveSnapshot = primitives,
                GeometrySnapshot = geometry,
                SemanticSnapshot = semantics
            };
        }

        public BuildingSemanticSnapshot Analyze(AnalysisRequest? request)
        {
            return AnalyzeCore(request, null, null);
        }

        private BuildingSemanticSnapshot AnalyzeCore(
            AnalysisRequest? request,
            DrawingSnapshot? collectedSnapshot,
            BuildingGeometrySnapshot? preparedGeometry)
        {
            var stopwatch = Stopwatch.StartNew();
            BuildingSemanticSnapshot snapshot = CreateSnapshot(request);
            try
            {
                ProfileValidationResult profileValidation = ProjectProfileValidator.Validate(request?.Profile);
                if (!profileValidation.IsValid)
                {
                    foreach (string message in profileValidation.Messages)
                        AddFinding(snapshot, FindingSeverity.Error, BuildingSemanticReasonCodes.ProfileInvalid, message);
                    snapshot.ReasonCodes.AddRange(profileValidation.ReasonCodes);
                    snapshot.Status = AnalysisRunStatus.Failed;
                    return FinalizeSnapshot(snapshot, stopwatch, 0);
                }

                if (request == null || string.IsNullOrWhiteSpace(request.DrawingHash))
                {
                    AddFinding(snapshot, FindingSeverity.Error, BuildingSemanticReasonCodes.DrawingHashRequired, "扫描前必须计算源 DWG 的 SHA-256。");
                    snapshot.Status = AnalysisRunStatus.Failed;
                    return FinalizeSnapshot(snapshot, stopwatch, 0);
                }

                DrawingProfileRule? drawingRule = ProjectProfileValidator.FindDrawing(request.Profile, request.DrawingHash);
                if (drawingRule == null)
                {
                    AddFinding(snapshot, FindingSeverity.Error, BuildingSemanticReasonCodes.DrawingHashMismatch, "当前 DWG 哈希不在 ProjectProfile 白名单中，拒绝套用本项目语义规则。");
                    snapshot.Status = AnalysisRunStatus.Failed;
                    return FinalizeSnapshot(snapshot, stopwatch, 0);
                }

                DrawingSnapshot? facts;
                try
                {
                    facts = collectedSnapshot ?? _factProvider.Collect(new CadFactRequest { Analysis = request });
                }
                catch (Exception ex)
                {
                    AddFinding(snapshot, FindingSeverity.Error, BuildingSemanticReasonCodes.FactProviderFailed, "CAD 事实适配器异常: " + ex.Message);
                    snapshot.Status = AnalysisRunStatus.Failed;
                    return FinalizeSnapshot(snapshot, stopwatch, 0);
                }

                snapshot.FactProviderId = facts?.ProviderId ?? _factProvider.ProviderId;
                snapshot.ProxyLedger = facts?.ProxyLedger.ToList() ?? new List<ProxyLedgerEntry>();
                snapshot.ProviderDiagnostics = facts?.Diagnostics.ToList() ?? new List<ProviderDiagnostic>();
                foreach (ProviderDiagnostic diagnostic in snapshot.ProviderDiagnostics)
                {
                    AddFinding(snapshot, diagnostic.Severity, diagnostic.ReasonCode, diagnostic.Message, string.Empty, ExtractHandle(diagnostic.StablePath));
                }

                if (facts == null || !facts.IsSuccess)
                {
                    IEnumerable<string> reasons = facts == null
                        ? new[] { BuildingSemanticReasonCodes.FactProviderFailed }
                        : facts.ReasonCodes;
                    snapshot.ReasonCodes.AddRange(reasons);
                    if (!snapshot.ReasonCodes.Any())
                        snapshot.ReasonCodes.Add(BuildingSemanticReasonCodes.FactProviderFailed);
                    snapshot.Status = AnalysisRunStatus.Failed;
                    return FinalizeSnapshot(snapshot, stopwatch, facts?.Facts?.Count ?? 0);
                }

                BuildingGeometrySnapshot geometryLayer = preparedGeometry
                    ?? new BuildingGeometryService().Build(CadPrimitiveSnapshotBuilder.Build(facts, request));
                List<CadFact> factList = GeometryFactCompatibility.ToCadFacts(geometryLayer, request.Profile)
                    .OrderBy(fact => fact.Source?.StablePath ?? string.Empty, StringComparer.Ordinal)
                    .ThenBy(fact => fact.Kind)
                    .ThenBy(fact => fact.FactId, StringComparer.Ordinal)
                    .ToList();
                foreach (CadFact fact in factList)
                    SemanticClassificationPolicy.Apply(fact);
                EnrichSpaceLabels(factList, request.Profile);

                foreach (CadFact fact in factList)
                    MapFact(snapshot, fact, request);
                AddUnresolvedKnownSpaceLabelFindings(snapshot, factList, request.Profile);

                if (!ApplyObservationRegionGate(snapshot, request.Profile, drawingRule, request.DrawingHash))
                    return FinalizeSnapshot(snapshot, stopwatch, factList.Count);

                BuildRelations(snapshot, request.Profile);
                AddObjectFindings(snapshot);
                AddProxyFindings(snapshot);

                if (snapshot.Objects.Count == 0)
                {
                    AddFinding(snapshot, FindingSeverity.Review, BuildingSemanticReasonCodes.NoSemanticObjects, "事实提取成功，但未形成可复核的建筑语义对象。");
                    AddReason(snapshot, BuildingSemanticReasonCodes.NoSemanticObjects);
                }

                bool needsReview = snapshot.Objects.Any(item => item.Status != DecisionStatus.Accepted)
                                   || snapshot.Relations.Any(item => item.Status != DecisionStatus.Accepted)
                                   || snapshot.ProxyLedger.Any(item => item.Disposition == ProxyDisposition.ReviewUnknown)
                                   || snapshot.Findings.Any(item => item.Severity != FindingSeverity.Information);
                snapshot.Status = needsReview ? AnalysisRunStatus.Review : AnalysisRunStatus.Accepted;
                if (!needsReview)
                    AddReason(snapshot, BuildingSemanticReasonCodes.Ok);

                return FinalizeSnapshot(snapshot, stopwatch, factList.Count);
            }
            catch (Exception ex)
            {
                AddFinding(snapshot, FindingSeverity.Error, BuildingSemanticReasonCodes.FactProviderFailed, "语义分析未处理异常: " + ex.Message);
                snapshot.Status = AnalysisRunStatus.Failed;
                return FinalizeSnapshot(snapshot, stopwatch, 0);
            }
        }

        private static BuildingSemanticSnapshot CreateSnapshot(AnalysisRequest? request)
        {
            string drawingPath = request?.DrawingPath ?? string.Empty;
            return new BuildingSemanticSnapshot
            {
                GeneratedAtUtc = DateTime.UtcNow.ToString("O", CultureInfo.InvariantCulture),
                Status = AnalysisRunStatus.Failed,
                Drawing = new DrawingIdentity
                {
                    DrawingId = request?.DrawingId ?? string.Empty,
                    FileName = string.IsNullOrWhiteSpace(drawingPath) ? string.Empty : Path.GetFileName(drawingPath),
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

        private static void EnrichSpaceLabels(IReadOnlyList<CadFact> facts, ProjectProfile profile)
        {
            List<CadFact> texts = facts.Where(fact => fact.Kind == CadFactKind.Text && !string.IsNullOrWhiteSpace(fact.RawLabel)).ToList();
            foreach (CadFact space in facts.Where(fact => fact.Kind == CadFactKind.Space && string.IsNullOrWhiteSpace(fact.RawLabel)))
            {
                var candidates = texts
                    .Where(text => text.Geometry?.Paths?.FirstOrDefault()?.FirstOrDefault() != null)
                    .Where(text => SemanticGeometryAlgorithms.ContainsPoint(space.Geometry, text.Geometry.Paths[0][0]))
                    .Select(text => new { Fact = text, Match = RoomUseClassifier.Match(text.RawLabel, profile) })
                    .Where(item => item.Match.IsMatch)
                    .OrderByDescending(item => item.Fact.Confidence)
                    .ThenBy(item => item.Fact.RawLabel.Length)
                    .ThenBy(item => item.Fact.Source?.StablePath ?? string.Empty, StringComparer.Ordinal)
                    .ToList();

                if (candidates.Count == 0)
                    continue;

                CadFact selected = candidates[0].Fact;
                space.RawLabel = selected.RawLabel;
                space.Evidence.Add(new SemanticEvidence
                {
                    Code = "ROOM_LABEL_CONTAINED_TEXT",
                    Kind = "spatial_text",
                    Value = selected.RawLabel,
                    SourceHandle = selected.Source?.Handle ?? string.Empty,
                    Weight = 0.85
                });
                space.Confidence = Math.Min(space.Confidence, 0.96);
                if (candidates.Count > 1)
                    AddFactReason(space, BuildingSemanticReasonCodes.AmbiguousRelation);
            }
        }

        private static void MapFact(BuildingSemanticSnapshot snapshot, CadFact fact, AnalysisRequest request)
        {
            if (fact == null || !IsSemanticKind(fact.Kind))
                return;

            if (fact.Source == null
                || string.IsNullOrWhiteSpace(fact.Source.Handle)
                || string.IsNullOrWhiteSpace(fact.Source.DrawingHash)
                || !string.Equals(fact.Source.DrawingHash, request.DrawingHash, StringComparison.OrdinalIgnoreCase))
            {
                AddFinding(snapshot, FindingSeverity.Error, BuildingSemanticReasonCodes.MissingEvidence, "事实缺少图纸哈希或源 Handle，未生成语义对象。", string.Empty, fact.Source?.Handle ?? string.Empty);
                AddReason(snapshot, BuildingSemanticReasonCodes.MissingEvidence);
                return;
            }

            if (fact.Evidence == null || fact.Evidence.Count == 0)
            {
                fact.Evidence = fact.Evidence ?? new List<SemanticEvidence>();
                fact.Evidence.Add(new SemanticEvidence
                {
                    Code = "CAD_NATIVE_IDENTITY",
                    Kind = "source",
                    Value = fact.Source.NativeDxfName + "/" + fact.Source.NativeClassName,
                    SourceHandle = fact.Source.Handle,
                    Weight = 0.5
                });
                AddFactReason(fact, BuildingSemanticReasonCodes.MissingEvidence);
            }

            switch (fact.Kind)
            {
                case CadFactKind.Opening:
                    AddOpeningObjects(snapshot, fact, request);
                    break;
                case CadFactKind.Door:
                    fact.Properties["opening_kind"] = "door";
                    AddOpeningObjects(snapshot, fact, request);
                    break;
                case CadFactKind.Window:
                    fact.Properties["opening_kind"] = "window";
                    AddOpeningObjects(snapshot, fact, request);
                    break;
                default:
                    AddObject(snapshot, fact, ToSemanticType(fact.Kind), ResolveClassification(fact), request, string.Empty);
                    break;
            }
        }

        private static void AddOpeningObjects(BuildingSemanticSnapshot snapshot, CadFact fact, AnalysisRequest request)
        {
            SemanticObject opening = AddObject(snapshot, fact, SemanticObjectType.Opening, ResolveClassification(fact), request, "base");
            string openingKind = GetProperty(fact, "opening_kind");
            SemanticObjectType subtype;
            if (string.Equals(openingKind, "door", StringComparison.OrdinalIgnoreCase))
                subtype = SemanticObjectType.Door;
            else if (string.Equals(openingKind, "window", StringComparison.OrdinalIgnoreCase))
                subtype = SemanticObjectType.Window;
            else
                return;

            SemanticObject fill = AddObject(snapshot, fact, subtype, ResolveClassification(fact), request, "fill");
            bool sensitive = IsSensitive(opening) || IsSensitive(fill);
            DecisionStatus relationStatus = !sensitive
                                            && opening.Status == DecisionStatus.Accepted
                                            && fill.Status == DecisionStatus.Accepted
                ? DecisionStatus.Accepted
                : DecisionStatus.Review;
            snapshot.Relations.Add(new SpatialRelation
            {
                RelationId = BuildingSemanticStableId.Create("rel", request.DrawingHash, request.ProfileHash, SemanticRelationType.FillsOpening.ToString(), fill.SemanticId, opening.SemanticId),
                Type = SemanticRelationType.FillsOpening,
                FromSemanticId = fill.SemanticId,
                ToSemanticId = opening.SemanticId,
                Status = relationStatus,
                Confidence = Math.Min(opening.Confidence, fill.Confidence),
                Evidence = new List<SemanticEvidence>
                {
                    new SemanticEvidence
                    {
                        Code = "SAME_NATIVE_OPENING_SOURCE",
                        Kind = "source_identity",
                        Value = fact.Source.StablePath,
                        SourceHandle = fact.Source.Handle,
                        Weight = 0.99
                    }
                },
                ReasonCodes = relationStatus == DecisionStatus.Review
                    ? new List<string> { BuildingSemanticReasonCodes.LowConfidence }
                    : new List<string>()
            });
        }

        private static SemanticObject AddObject(
            BuildingSemanticSnapshot snapshot,
            CadFact fact,
            SemanticObjectType type,
            string classification,
            AnalysisRequest request,
            string discriminator)
        {
            RoomUseMatch useMatch = type == SemanticObjectType.Space
                                    || type == SemanticObjectType.Shaft
                                    || type == SemanticObjectType.Stair
                                    || type == SemanticObjectType.Ramp
                ? RoomUseClassifier.Match(fact.RawLabel, request.Profile)
                : new RoomUseMatch();
            if (fact.Kind == CadFactKind.Space && useMatch.IsMatch)
                type = useMatch.SemanticType;
            bool spaceLike = IsSpaceLike(type);

            bool geometryUsable = type == SemanticObjectType.Storey
                                  || SemanticGeometryAlgorithms.IsUsable(fact.Geometry, false);
            bool exactGeometry = type == SemanticObjectType.Storey
                                 || SemanticGeometryAlgorithms.IsUsable(fact.Geometry, true);
            bool sensitive = IsSensitiveClassification(classification) || IsSensitiveFact(fact);

            DecisionStatus status;
            var reasons = new List<string>(fact.ReasonCodes ?? new List<string>());
            if (!geometryUsable)
            {
                status = DecisionStatus.Rejected;
                AddDistinct(reasons, BuildingSemanticReasonCodes.InvalidGeometry);
            }
            else if (type == SemanticObjectType.RoofLine)
            {
                status = DecisionStatus.Review;
                AddDistinct(reasons, BuildingSemanticReasonCodes.LowConfidence);
            }
            else if (sensitive)
            {
                status = DecisionStatus.Review;
                AddDistinct(reasons, BuildingSemanticReasonCodes.LowConfidence);
            }
            else if (reasons.Any())
            {
                status = DecisionStatus.Review;
            }
            else if (fact.Confidence >= request.Profile.Thresholds.AcceptedConfidence && exactGeometry)
            {
                status = DecisionStatus.Accepted;
            }
            else
            {
                status = DecisionStatus.Review;
                AddDistinct(reasons, BuildingSemanticReasonCodes.LowConfidence);
                if (!exactGeometry)
                    AddDistinct(reasons, BuildingSemanticReasonCodes.InvalidGeometry);
            }

            if (spaceLike
                && (string.IsNullOrWhiteSpace(fact.RawLabel)
                    || type == SemanticObjectType.Space && !useMatch.IsMatch))
            {
                status = status == DecisionStatus.Rejected ? status : DecisionStatus.Review;
                AddDistinct(reasons, BuildingSemanticReasonCodes.LowConfidence);
            }

            string useCode = type == SemanticObjectType.RoofLine
                ? "ROOF_LINE"
                : useMatch.IsMatch
                ? useMatch.UseCode
                : !spaceLike
                    ? string.Empty
                    : type == SemanticObjectType.Space ? "UNKNOWN" : type.ToString().ToUpperInvariant();
            var semanticObject = new SemanticObject
            {
                SemanticId = BuildingSemanticStableId.Create(
                    "sem",
                    request.DrawingHash,
                    request.ProfileHash,
                    type.ToString(),
                    fact.Source.StablePath,
                    discriminator ?? string.Empty),
                Type = type,
                Classification = classification,
                RawLabel = fact.RawLabel ?? string.Empty,
                UseCode = useCode,
                Status = status,
                Confidence = Clamp(fact.Confidence),
                Source = fact.Source,
                Geometry = fact.Geometry,
                Evidence = (fact.Evidence ?? new List<SemanticEvidence>())
                    .OrderBy(item => item.Code, StringComparer.Ordinal)
                    .ThenBy(item => item.Value, StringComparer.Ordinal)
                    .ToList(),
                ReasonCodes = reasons.OrderBy(item => item, StringComparer.Ordinal).ToList()
            };
            if (useMatch.IsMatch)
            {
                semanticObject.Evidence.Add(new SemanticEvidence
                {
                    Code = "PROJECT_USE_DICTIONARY",
                    Kind = "profile_rule",
                    Value = useMatch.Keyword + "=>" + useMatch.UseCode,
                    SourceHandle = fact.Source.Handle,
                    Weight = 0.90
                });
                semanticObject.Evidence.Add(new SemanticEvidence
                {
                    Code = "SEMANTIC_RULE_PACK",
                    Kind = "profile_rule_pack",
                    Value = useMatch.RulePack,
                    SourceHandle = fact.Source.Handle,
                    Weight = 1.0
                });
            }
            else if (spaceLike && type != SemanticObjectType.Space)
            {
                semanticObject.Evidence.Add(new SemanticEvidence
                {
                    Code = "EXPLICIT_SEMANTIC_TYPE_USE",
                    Kind = "native_type",
                    Value = type + "=>" + useCode,
                    SourceHandle = fact.Source.Handle,
                    Weight = 0.80
                });
            }
            snapshot.Objects.Add(semanticObject);
            return semanticObject;
        }

        private static bool ApplyObservationRegionGate(
            BuildingSemanticSnapshot snapshot,
            ProjectProfile profile,
            DrawingProfileRule drawingRule,
            string drawingHash)
        {
            if (ProjectProfileValidator.IsGenericReviewDrawing(drawingRule))
            {
                foreach (SemanticObject semanticObject in snapshot.Objects)
                {
                    if (semanticObject.Status == DecisionStatus.Accepted)
                        semanticObject.Status = DecisionStatus.Review;
                    AddDistinct(semanticObject.ReasonCodes, BuildingSemanticReasonCodes.RulesNotFrozen);
                    semanticObject.Evidence.Add(new SemanticEvidence
                    {
                        Code = "GENERIC_UNLISTED_DRAWING_REVIEW",
                        Kind = "profile_policy",
                        Value = drawingHash,
                        SourceHandle = semanticObject.Source?.Handle ?? string.Empty,
                        Weight = 1.0
                    });
                    semanticObject.Evidence = semanticObject.Evidence
                        .OrderBy(item => item.Code, StringComparer.Ordinal)
                        .ThenBy(item => item.Value, StringComparer.Ordinal)
                        .ToList();
                }
                AddFinding(snapshot, FindingSeverity.Review, BuildingSemanticReasonCodes.RulesNotFrozen,
                    "当前 DWG 未登记为金标准样本；已离线套用通用图层、对象和文字规则，图纸哈希仅用于追溯，全部结果保持 Review。");
                AddReason(snapshot, BuildingSemanticReasonCodes.RulesNotFrozen);
                return true;
            }

            List<ObservationRegion> drawingRegions = (profile.ObservationRegions ?? new List<ObservationRegion>())
                .Where(region => string.Equals(region.DrawingHash, drawingHash, StringComparison.OrdinalIgnoreCase))
                .OrderBy(region => region.Code, StringComparer.Ordinal)
                .ToList();
            if (drawingRegions.Count == 0)
            {
                if (profile.RuleState != SemanticRuleState.Frozen)
                {
                    foreach (SemanticObject semanticObject in snapshot.Objects)
                    {
                        if (semanticObject.Status == DecisionStatus.Accepted)
                            semanticObject.Status = DecisionStatus.Review;
                        AddDistinct(semanticObject.ReasonCodes, BuildingSemanticReasonCodes.RulesNotFrozen);
                        semanticObject.Evidence.Add(new SemanticEvidence
                        {
                            Code = "REGISTERED_DRAWING_REVIEW",
                            Kind = "profile_policy",
                            Value = drawingHash,
                            SourceHandle = semanticObject.Source?.Handle ?? string.Empty,
                            Weight = 1.0
                        });
                        semanticObject.Evidence = semanticObject.Evidence
                            .OrderBy(item => item.Code, StringComparer.Ordinal)
                            .ThenBy(item => item.Value, StringComparer.Ordinal)
                            .ToList();
                    }
                    AddFinding(snapshot, FindingSeverity.Review, BuildingSemanticReasonCodes.RulesNotFrozen,
                        "当前已登记 DWG 使用生产复核规则，但规则尚未冻结；全部结果保持 Review，历史留出样本不阻断日常扫描。");
                    AddReason(snapshot, BuildingSemanticReasonCodes.RulesNotFrozen);
                }
                return true;
            }

            List<string> pending = drawingRegions
                .Where(region => region.State != ObservationRegionState.Frozen)
                .Select(region => region.Code)
                .ToList();
            if (pending.Count > 0)
            {
                string message = "观察区坐标尚未由用户冻结: " + string.Join(",", pending)
                                 + "。正向语义对象已封锁，禁止实施者自行选区或提前查看留出结果。";
                AddFinding(snapshot, FindingSeverity.Error, BuildingSemanticReasonCodes.ObservationRegionNotFrozen, message);
                AddReason(snapshot, BuildingSemanticReasonCodes.ObservationRegionNotFrozen);
                snapshot.Objects.Clear();
                snapshot.Relations.Clear();
                snapshot.Status = AnalysisRunStatus.Failed;
                return false;
            }

            if (profile.RuleState == SemanticRuleState.Frozen)
                return true;

            bool drawingIsHoldout = (drawingRule?.Role ?? string.Empty)
                .IndexOf("holdout", StringComparison.OrdinalIgnoreCase) >= 0;
            List<ObservationRegion> calibrationRegions = drawingRegions
                .Where(region => region.Role == ObservationRegionRole.Calibration)
                .ToList();
            if (drawingIsHoldout || calibrationRegions.Count == 0)
            {
                AddFinding(snapshot, FindingSeverity.Error, BuildingSemanticReasonCodes.HoldoutEvaluationLocked,
                    "当前图纸只承担留出验证；rules_frozen 审计完成前不输出语义对象。");
                AddReason(snapshot, BuildingSemanticReasonCodes.HoldoutEvaluationLocked);
                snapshot.Objects.Clear();
                snapshot.Relations.Clear();
                snapshot.Status = AnalysisRunStatus.Failed;
                return false;
            }

            var regionGeometries = calibrationRegions.ToDictionary(
                region => region.Code,
                CreateRegionGeometry,
                StringComparer.Ordinal);
            var kept = new List<SemanticObject>();
            foreach (SemanticObject semanticObject in snapshot.Objects)
            {
                List<string> matches = regionGeometries
                    .Where(item => SemanticGeometryAlgorithms.Intersects2D(semanticObject.Geometry, item.Value))
                    .Select(item => item.Key)
                    .OrderBy(code => code, StringComparer.Ordinal)
                    .ToList();
                if (matches.Count == 0)
                    continue;

                if (semanticObject.Status == DecisionStatus.Accepted)
                    semanticObject.Status = DecisionStatus.Review;
                AddDistinct(semanticObject.ReasonCodes, BuildingSemanticReasonCodes.RulesNotFrozen);
                semanticObject.Evidence.Add(new SemanticEvidence
                {
                    Code = "CALIBRATION_REGION_GATE",
                    Kind = "project_governance",
                    Value = string.Join(",", matches),
                    SourceHandle = semanticObject.Source.Handle,
                    Weight = 1.0
                });
                semanticObject.Evidence = semanticObject.Evidence
                    .OrderBy(item => item.Code, StringComparer.Ordinal)
                    .ThenBy(item => item.Value, StringComparer.Ordinal)
                    .ToList();
                kept.Add(semanticObject);
            }
            snapshot.Objects = kept;
            AddFinding(snapshot, FindingSeverity.Review, BuildingSemanticReasonCodes.RulesNotFrozen,
                "当前为校准模式，仅输出冻结的校准区对象；B4/G1 留出对象已从结果中排除，且全部对象最多为 Review。");
            AddReason(snapshot, BuildingSemanticReasonCodes.RulesNotFrozen);
            return true;
        }

        private static SemanticGeometry CreateRegionGeometry(ObservationRegion region)
        {
            List<SemanticPoint> points = (region?.PolygonWcsMillimeters ?? new List<SemanticPoint>())
                .Select(point => new SemanticPoint(point.X, point.Y, point.Z))
                .ToList();
            var geometry = new SemanticGeometry
            {
                Kind = GeometryKind.Polygon,
                IsClosed = true,
                IsExact = true,
                ExtractionMethod = "human_frozen_observation_region",
                Paths = new List<List<SemanticPoint>> { points }
            };
            geometry.Bounds = SemanticGeometryAlgorithms.CalculateBounds(geometry.Paths);
            return geometry;
        }

        private static void BuildRelations(BuildingSemanticSnapshot snapshot, ProjectProfile profile)
        {
            double tolerance = profile.Thresholds.RelationToleranceMillimeters;
            List<SemanticObject> walls = snapshot.Objects.Where(item => item.Type == SemanticObjectType.Wall && item.Status != DecisionStatus.Rejected).ToList();
            List<SemanticObject> openings = snapshot.Objects.Where(item => item.Type == SemanticObjectType.Opening && item.Status != DecisionStatus.Rejected).ToList();
            List<SemanticObject> spaces = snapshot.Objects.Where(item => IsSpaceLike(item.Type) && item.Status != DecisionStatus.Rejected).ToList();
            List<SemanticObject> zones = snapshot.Objects.Where(item => item.Type == SemanticObjectType.Zone && item.Status != DecisionStatus.Rejected).ToList();

            foreach (SemanticObject opening in openings)
            {
                List<SemanticObject> candidates = walls
                    .Where(wall => SemanticGeometryAlgorithms.BoundsIntersect(opening.Geometry, wall.Geometry, tolerance))
                    .OrderBy(wall => SemanticGeometryAlgorithms.BoundsCenterDistance(opening.Geometry, wall.Geometry))
                    .ThenBy(wall => wall.SemanticId, StringComparer.Ordinal)
                    .ToList();
                if (candidates.Count == 1)
                {
                    SemanticObject wall = candidates[0];
                    bool accepted = opening.Status == DecisionStatus.Accepted
                                    && wall.Status == DecisionStatus.Accepted
                                    && opening.Geometry.IsExact
                                    && wall.Geometry.IsExact
                                    && !IsSensitive(opening)
                                    && !IsSensitive(wall);
                    AddRelation(snapshot, SemanticRelationType.HostedBy, opening, wall,
                        accepted ? DecisionStatus.Accepted : DecisionStatus.Review,
                        Math.Min(opening.Confidence, wall.Confidence) * 0.98,
                        "UNIQUE_GEOMETRY_HOST", accepted ? string.Empty : BuildingSemanticReasonCodes.LowConfidence);
                }
                else if (candidates.Count > 1)
                {
                    SemanticObject wall = candidates[0];
                    AddRelation(snapshot, SemanticRelationType.HostedBy, opening, wall,
                        DecisionStatus.Review,
                        Math.Min(opening.Confidence, wall.Confidence) * 0.70,
                        "AMBIGUOUS_GEOMETRY_HOST", BuildingSemanticReasonCodes.AmbiguousRelation);
                }

                SemanticPoint openingPoint = SemanticGeometryAlgorithms.RepresentativePoint(opening.Geometry);
                List<SemanticObject> connectedSpaces = spaces
                    .Where(space => SemanticGeometryAlgorithms.ContainsPoint(space.Geometry, openingPoint)
                                    || SemanticGeometryAlgorithms.BoundsIntersect(space.Geometry, opening.Geometry, tolerance))
                    .OrderBy(space => SemanticGeometryAlgorithms.BoundsCenterDistance(opening.Geometry, space.Geometry))
                    .ThenBy(space => space.SemanticId, StringComparer.Ordinal)
                    .Take(2)
                    .ToList();
                foreach (SemanticObject space in connectedSpaces)
                {
                    AddRelation(snapshot, SemanticRelationType.Connects, opening, space,
                        DecisionStatus.Review,
                        Math.Min(opening.Confidence, space.Confidence) * 0.75,
                        "OPENING_NEAR_SPACE_BOUNDARY", BuildingSemanticReasonCodes.LowConfidence);
                }
            }

            foreach (SemanticObject space in spaces)
            {
                foreach (SemanticObject wall in walls
                             .Where(wall => SemanticGeometryAlgorithms.BoundsIntersect(space.Geometry, wall.Geometry, tolerance))
                             .OrderBy(wall => wall.SemanticId, StringComparer.Ordinal))
                {
                    AddRelation(snapshot, SemanticRelationType.BoundedBy, space, wall,
                        DecisionStatus.Review,
                        Math.Min(space.Confidence, wall.Confidence) * 0.70,
                        "BOUNDARY_PROXIMITY", BuildingSemanticReasonCodes.LowConfidence);
                }
            }

            foreach (SemanticObject zone in zones)
            {
                foreach (SemanticObject space in spaces
                             .Where(space => SemanticGeometryAlgorithms.ContainsPoint(zone.Geometry, SemanticGeometryAlgorithms.RepresentativePoint(space.Geometry)))
                             .OrderBy(space => space.SemanticId, StringComparer.Ordinal))
                {
                    AddRelation(snapshot, SemanticRelationType.Contains, zone, space,
                        DecisionStatus.Review,
                        Math.Min(zone.Confidence, space.Confidence) * 0.90,
                        "REPRESENTATIVE_POINT_IN_ZONE", BuildingSemanticReasonCodes.LowConfidence);
                }
            }
        }

        private static void AddRelation(
            BuildingSemanticSnapshot snapshot,
            SemanticRelationType type,
            SemanticObject from,
            SemanticObject to,
            DecisionStatus status,
            double confidence,
            string evidenceCode,
            string reasonCode)
        {
            if (snapshot.Relations.Any(item => item.Type == type
                                               && item.FromSemanticId == from.SemanticId
                                               && item.ToSemanticId == to.SemanticId))
                return;
            var relation = new SpatialRelation
            {
                RelationId = BuildingSemanticStableId.Create("rel", snapshot.Drawing.Sha256, snapshot.Profile.Sha256, type.ToString(), from.SemanticId, to.SemanticId),
                Type = type,
                FromSemanticId = from.SemanticId,
                ToSemanticId = to.SemanticId,
                Status = status,
                Confidence = Clamp(confidence),
                Evidence = new List<SemanticEvidence>
                {
                    new SemanticEvidence
                    {
                        Code = evidenceCode,
                        Kind = "geometry_relation",
                        Value = from.Source.StablePath + "=>" + to.Source.StablePath,
                        SourceHandle = from.Source.Handle,
                        Weight = Clamp(confidence)
                    }
                }
            };
            if (!string.IsNullOrWhiteSpace(reasonCode))
                relation.ReasonCodes.Add(reasonCode);
            snapshot.Relations.Add(relation);
        }

        private static void AddObjectFindings(BuildingSemanticSnapshot snapshot)
        {
            foreach (SemanticObject semanticObject in snapshot.Objects.Where(item => item.Status != DecisionStatus.Accepted))
            {
                string reason = semanticObject.ReasonCodes.FirstOrDefault() ?? BuildingSemanticReasonCodes.LowConfidence;
                string message = semanticObject.Status == DecisionStatus.Rejected
                    ? "对象因几何或证据无效被拒绝，禁止下游自动使用。"
                    : "对象需要人工复核，禁止下游按 Accepted 使用。";
                AddFinding(snapshot,
                    semanticObject.Status == DecisionStatus.Rejected ? FindingSeverity.Error : FindingSeverity.Review,
                    reason,
                    message,
                    semanticObject.SemanticId,
                    semanticObject.Source.Handle);
                AddReason(snapshot, reason);
            }
        }

        private static void AddProxyFindings(BuildingSemanticSnapshot snapshot)
        {
            foreach (ProxyLedgerEntry entry in snapshot.ProxyLedger.Where(item => item.Disposition == ProxyDisposition.ReviewUnknown))
            {
                string reason = string.IsNullOrWhiteSpace(entry.ReasonCode)
                    ? BuildingSemanticReasonCodes.UnsupportedProxyObject
                    : entry.ReasonCode;
                AddFinding(snapshot, FindingSeverity.Review, reason, "代理对象未被静默忽略，需要复核分类。", string.Empty, entry.Handle);
                AddReason(snapshot, reason);
            }
        }

        private static void AddUnresolvedKnownSpaceLabelFindings(
            BuildingSemanticSnapshot snapshot,
            IReadOnlyList<CadFact> facts,
            ProjectProfile profile)
        {
            List<CadFact> labels = facts
                .Where(fact => fact.Kind == CadFactKind.Text)
                .Where(fact => string.Equals(
                    fact.Source?.NormalizedLayer,
                    "A-Spac-Iden-Auto",
                    StringComparison.OrdinalIgnoreCase))
                .Where(fact => !string.IsNullOrWhiteSpace(fact.RawLabel))
                .GroupBy(fact => fact.Source?.StablePath ?? fact.FactId ?? string.Empty, StringComparer.Ordinal)
                .Select(group => group.First())
                .ToList();
            foreach (CadFact label in labels)
            {
                RoomUseMatch match = RoomUseClassifier.Match(label.RawLabel, profile);
                if (!match.IsMatch
                    || (match.SemanticType != SemanticObjectType.Space
                        && match.SemanticType != SemanticObjectType.Shaft
                        && match.SemanticType != SemanticObjectType.Zone))
                    continue;
                SemanticPoint? point = label.Geometry?.Bounds?.IsValid == true
                    ? SemanticGeometryAlgorithms.RepresentativePoint(label.Geometry)
                    : null;
                string normalizedLabel = RoomUseClassifier.Normalize(label.RawLabel);
                bool resolved = point != null && snapshot.Objects.Any(item =>
                    item.Type == match.SemanticType
                    && string.Equals(item.UseCode, match.UseCode, StringComparison.Ordinal)
                    && string.Equals(RoomUseClassifier.Normalize(item.RawLabel), normalizedLabel, StringComparison.Ordinal)
                    && SemanticGeometryAlgorithms.ContainsPoint(item.Geometry, point));
                if (resolved)
                    continue;

                string location = point == null
                    ? "坐标不可用"
                    : "WCS=(" + point.X.ToString("0.###", CultureInfo.InvariantCulture)
                      + "," + point.Y.ToString("0.###", CultureInfo.InvariantCulture) + ")mm";
                AddFinding(
                    snapshot,
                    FindingSeverity.Review,
                    BuildingSemanticReasonCodes.KnownSpaceLabelUnresolved,
                    "已知空间名称“" + label.RawLabel.Replace("\r", " ").Replace("\n", " ")
                    + "”未形成唯一墙围合语义；请检查墙线/钢筋混凝土墙边界是否闭合、名称定位点是否落在墙上，或同一围合内是否存在多条名称。"
                    + location,
                    string.Empty,
                    label.Source?.Handle ?? string.Empty);
                AddReason(snapshot, BuildingSemanticReasonCodes.KnownSpaceLabelUnresolved);
            }
        }

        private static BuildingSemanticSnapshot FinalizeSnapshot(BuildingSemanticSnapshot snapshot, Stopwatch stopwatch, int factCount)
        {
            stopwatch.Stop();
            snapshot.ReasonCodes = snapshot.ReasonCodes
                .Where(code => !string.IsNullOrWhiteSpace(code))
                .Distinct(StringComparer.Ordinal)
                .OrderBy(code => code, StringComparer.Ordinal)
                .ToList();
            snapshot.Objects = snapshot.Objects
                .OrderBy(item => item.SemanticId, StringComparer.Ordinal)
                .ToList();
            snapshot.Relations = snapshot.Relations
                .OrderBy(item => item.RelationId, StringComparer.Ordinal)
                .ToList();
            snapshot.Findings = snapshot.Findings
                .GroupBy(item => item.FindingId, StringComparer.Ordinal)
                .Select(group => group.First())
                .OrderBy(item => item.FindingId, StringComparer.Ordinal)
                .ToList();
            snapshot.ProxyLedger = snapshot.ProxyLedger
                .OrderBy(item => item.StablePath, StringComparer.Ordinal)
                .ThenBy(item => item.Handle, StringComparer.Ordinal)
                .ToList();
            snapshot.ProviderDiagnostics = snapshot.ProviderDiagnostics
                .OrderBy(item => item.StablePath, StringComparer.Ordinal)
                .ThenBy(item => item.ReasonCode, StringComparer.Ordinal)
                .ToList();
            snapshot.Metrics = new SnapshotMetrics
            {
                AnalysisElapsedMilliseconds = stopwatch.ElapsedMilliseconds,
                FactCount = factCount,
                SemanticObjectCount = snapshot.Objects.Count,
                AcceptedObjectCount = snapshot.Objects.Count(item => item.Status == DecisionStatus.Accepted),
                ReviewObjectCount = snapshot.Objects.Count(item => item.Status == DecisionStatus.Review),
                RejectedObjectCount = snapshot.Objects.Count(item => item.Status == DecisionStatus.Rejected),
                RelationCount = snapshot.Relations.Count,
                ProxyCount = snapshot.ProxyLedger.Count,
                TopLevelProxyObjectCount = snapshot.ProxyLedger.Count(item => (item.StablePath ?? string.Empty).IndexOf('/') < 0),
                UniqueProxyHandleCount = snapshot.ProxyLedger
                    .Select(item => (item.Handle ?? string.Empty) + "|" + (item.OriginalDxfName ?? string.Empty) + "|" + (item.OriginalClassName ?? string.Empty))
                    .Distinct(StringComparer.OrdinalIgnoreCase)
                    .Count(),
                ReachableProxyInstanceCount = snapshot.ProxyLedger.Count,
                SupportedProxyCount = snapshot.ProxyLedger.Count(item => item.Disposition == ProxyDisposition.SupportedFact),
                IgnoredAnnotationProxyCount = snapshot.ProxyLedger.Count(item => item.Disposition == ProxyDisposition.IgnoredAnnotation),
                IgnoredOutOfScopeProxyCount = snapshot.ProxyLedger.Count(item => item.Disposition == ProxyDisposition.IgnoredOutOfScope),
                ReviewUnknownProxyCount = snapshot.ProxyLedger.Count(item => item.Disposition == ProxyDisposition.ReviewUnknown)
            };
            snapshot.DeterministicContentHash = BuildingSemanticDeterminism.Compute(snapshot);
            return snapshot;
        }

        private static void AddFinding(
            BuildingSemanticSnapshot snapshot,
            FindingSeverity severity,
            string reasonCode,
            string message,
            string semanticId = "",
            string sourceHandle = "")
        {
            string identity = !string.IsNullOrWhiteSpace(semanticId) ? semanticId : sourceHandle;
            snapshot.Findings.Add(new ReviewFinding
            {
                FindingId = BuildingSemanticStableId.Create("finding", snapshot.Drawing.Sha256, reasonCode ?? string.Empty, identity ?? string.Empty, message ?? string.Empty),
                Severity = severity,
                ReasonCode = reasonCode ?? string.Empty,
                Message = message ?? string.Empty,
                SemanticId = semanticId ?? string.Empty,
                SourceHandle = sourceHandle ?? string.Empty
            });
        }

        private static void AddReason(BuildingSemanticSnapshot snapshot, string reason)
        {
            if (!string.IsNullOrWhiteSpace(reason) && !snapshot.ReasonCodes.Contains(reason, StringComparer.Ordinal))
                snapshot.ReasonCodes.Add(reason);
        }

        private static void AddFactReason(CadFact fact, string reason)
        {
            fact.ReasonCodes = fact.ReasonCodes ?? new List<string>();
            AddDistinct(fact.ReasonCodes, reason);
        }

        private static void AddDistinct(ICollection<string> values, string value)
        {
            if (!values.Contains(value))
                values.Add(value);
        }

        private static bool IsSemanticKind(CadFactKind kind)
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
                   || kind == CadFactKind.Zone
                   || kind == CadFactKind.RoofLine;
        }

        private static SemanticObjectType ToSemanticType(CadFactKind kind)
        {
            switch (kind)
            {
                case CadFactKind.Storey: return SemanticObjectType.Storey;
                case CadFactKind.Space: return SemanticObjectType.Space;
                case CadFactKind.Wall: return SemanticObjectType.Wall;
                case CadFactKind.Column: return SemanticObjectType.Column;
                case CadFactKind.Door: return SemanticObjectType.Door;
                case CadFactKind.Window: return SemanticObjectType.Window;
                case CadFactKind.Shaft: return SemanticObjectType.Shaft;
                case CadFactKind.Stair: return SemanticObjectType.Stair;
                case CadFactKind.Ramp: return SemanticObjectType.Ramp;
                case CadFactKind.Zone: return SemanticObjectType.Zone;
                case CadFactKind.RoofLine: return SemanticObjectType.RoofLine;
                default: return SemanticObjectType.Space;
            }
        }

        private static string ResolveClassification(CadFact fact)
        {
            if (fact.Kind == CadFactKind.Wall)
                return GetProperty(fact, "wall_class", WallClassification.Unknown.ToString());
            if (fact.Kind == CadFactKind.Zone)
                return GetProperty(fact, "zone_class", ZoneClassification.Unknown.ToString());
            return GetProperty(fact, "classification");
        }

        private static string GetProperty(CadFact fact, string key, string fallback = "")
        {
            if (fact?.Properties != null && fact.Properties.TryGetValue(key, out string? value))
                return value ?? fallback;
            return fallback;
        }

        private static bool IsSensitiveFact(CadFact fact)
        {
            string value = string.Join("|", new[]
            {
                fact.RawLabel,
                fact.Source?.RawLayer,
                fact.Source?.EffectiveLayer,
                fact.Source?.NormalizedLayer,
                GetProperty(fact, "fire_protection"),
                GetProperty(fact, "civil_defense")
            });
            return ContainsAny(value, "防火", "消防", "FIRE", "人防", "防护", "CIVILDEFENSE", "CIVIL_DEFENSE")
                   || SemanticSensitivityPolicy.HasFireEvidence(fact.Properties)
                   || SemanticSensitivityPolicy.HasCivilDefenseEvidence(fact.Properties);
        }

        private static bool IsSensitive(SemanticObject? semanticObject)
        {
            return semanticObject != null
                   && (IsSensitiveClassification(semanticObject.Classification)
                       || ContainsAny(semanticObject.RawLabel, "防火", "消防", "FIRE", "人防", "防护"));
        }

        private static bool IsSensitiveClassification(string? classification)
        {
            return string.Equals(classification, WallClassification.Fire.ToString(), StringComparison.OrdinalIgnoreCase)
                   || string.Equals(classification, WallClassification.Shear.ToString(), StringComparison.OrdinalIgnoreCase)
                   || string.Equals(classification, WallClassification.CivilDefense.ToString(), StringComparison.OrdinalIgnoreCase)
                   || string.Equals(classification, ZoneClassification.Fire.ToString(), StringComparison.OrdinalIgnoreCase)
                   || string.Equals(classification, ZoneClassification.CivilDefense.ToString(), StringComparison.OrdinalIgnoreCase);
        }

        private static bool ContainsAny(string? value, params string[] terms)
        {
            string normalized = (value ?? string.Empty).ToUpperInvariant();
            return terms.Any(term => normalized.Contains(term.ToUpperInvariant()));
        }

        private static bool IsSpaceLike(SemanticObjectType type)
        {
            return type == SemanticObjectType.Space
                   || type == SemanticObjectType.Shaft
                   || type == SemanticObjectType.Stair
                   || type == SemanticObjectType.Ramp;
        }

        private static double Clamp(double value)
        {
            if (double.IsNaN(value) || double.IsInfinity(value))
                return 0;
            return Math.Max(0, Math.Min(1, value));
        }

        private static string ExtractHandle(string stablePath)
        {
            if (string.IsNullOrWhiteSpace(stablePath))
                return string.Empty;
            string[] parts = stablePath.Split('/');
            return parts.Length == 0 ? string.Empty : parts[parts.Length - 1];
        }
    }

    /// <summary>
    /// 将磁盘字节、活动文档状态与实际扫描输入模式绑定为可审计证据。
    /// 侧载数据库模式允许 T20 打开图纸后产生的非零 DBMOD，但侧载输入必须只读，
    /// 且活动文档的 DBMOD 在扫描期间仍必须可读并保持不变。
    /// </summary>
    public static class ScanIntegrityPolicy
    {
        public static void Apply(
            BuildingSemanticSnapshot snapshot,
            string hashBefore,
            string hashAfter,
            int dbmodBefore,
            int dbmodAfter,
            ScanInputMode inputMode,
            bool inputDatabaseReadOnly)
        {
            if (snapshot == null)
                throw new ArgumentNullException(nameof(snapshot));

            bool bytesUnchanged = string.Equals(hashBefore, hashAfter, StringComparison.OrdinalIgnoreCase);
            bool dbmodAvailable = dbmodBefore >= 0 && dbmodAfter >= 0;
            bool dbmodUnchanged = dbmodAvailable && dbmodBefore == dbmodAfter;
            bool dbmodCleanAtStart = dbmodBefore == 0;
            snapshot.Integrity = new ScanIntegrityEvidence
            {
                SourceHashBefore = hashBefore,
                SourceHashAfter = hashAfter,
                SourceBytesUnchanged = bytesUnchanged,
                ScanInputMode = inputMode,
                InputDatabaseReadOnly = inputDatabaseReadOnly,
                DbmodBefore = dbmodBefore,
                DbmodAfter = dbmodAfter,
                DbmodCleanAtStart = dbmodCleanAtStart,
                DbmodUnchanged = dbmodUnchanged
            };

            if (!dbmodAvailable)
            {
                AddFailure(
                    snapshot,
                    hashBefore,
                    BuildingSemanticReasonCodes.DbmodEvidenceUnavailable,
                    "无法读取活动图扫描前后的 DBMOD，不能证明命令未改变活动图。所有结果已失败闭合。");
            }

            if (inputMode == ScanInputMode.ActiveDocument && !dbmodCleanAtStart)
            {
                AddFailure(
                    snapshot,
                    hashBefore,
                    BuildingSemanticReasonCodes.SourceDrawingDirty,
                    "扫描输入是活动文档，但开始时 DBMOD 不为 0；内存图与磁盘 SHA-256 不能建立同一性。所有结果已失败闭合。");
            }

            if (inputMode == ScanInputMode.DiskSideDatabase && !inputDatabaseReadOnly)
            {
                AddFailure(
                    snapshot,
                    hashBefore,
                    BuildingSemanticReasonCodes.ScanInputNotReadOnly,
                    "磁盘侧载数据库未声明为只读输入，不能作为源 DWG 的可信快照。所有结果已失败闭合。");
            }

            if (!bytesUnchanged || (dbmodAvailable && !dbmodUnchanged))
            {
                AddFailure(
                    snapshot,
                    hashBefore,
                    BuildingSemanticReasonCodes.SourceModifiedDuringScan,
                    "扫描期间源 DWG 字节或活动图 DBMOD 发生变化，全部结果禁止自动使用。");
            }

            snapshot.ReasonCodes = snapshot.ReasonCodes
                .Distinct(StringComparer.Ordinal)
                .OrderBy(value => value, StringComparer.Ordinal)
                .ToList();
            snapshot.Findings = snapshot.Findings
                .GroupBy(value => value.FindingId, StringComparer.Ordinal)
                .Select(group => group.First())
                .OrderBy(value => value.FindingId, StringComparer.Ordinal)
                .ToList();
            snapshot.DeterministicContentHash = BuildingSemanticDeterminism.Compute(snapshot);
        }

        private static void AddFailure(
            BuildingSemanticSnapshot snapshot,
            string drawingHash,
            string reasonCode,
            string message)
        {
            snapshot.Status = AnalysisRunStatus.Failed;
            QuarantineSemanticOutput(snapshot);
            if (!snapshot.ReasonCodes.Contains(reasonCode, StringComparer.Ordinal))
                snapshot.ReasonCodes.Add(reasonCode);
            snapshot.Findings.Add(new ReviewFinding
            {
                FindingId = BuildingSemanticStableId.Create("finding", drawingHash, reasonCode),
                Severity = FindingSeverity.Error,
                ReasonCode = reasonCode,
                Message = message
            });
        }

        private static void QuarantineSemanticOutput(BuildingSemanticSnapshot snapshot)
        {
            // 完整性门禁在语义分析之后执行；一旦失败，禁止把先前已生成的
            // Accepted/Review 对象或关系留在 Failed 快照中供下游误用。
            snapshot.Objects = new List<SemanticObject>();
            snapshot.Relations = new List<SpatialRelation>();
            SnapshotMetrics metrics = snapshot.Metrics ?? new SnapshotMetrics();
            metrics.SemanticObjectCount = 0;
            metrics.AcceptedObjectCount = 0;
            metrics.ReviewObjectCount = 0;
            metrics.RejectedObjectCount = 0;
            metrics.RelationCount = 0;
            snapshot.Metrics = metrics;
        }
    }

    public static class BuildingSemanticDeterminism
    {
        public static string Compute(BuildingSemanticSnapshot snapshot)
        {
            var builder = new StringBuilder();
            Append(builder, snapshot.SchemaVersion, snapshot.Producer, snapshot.ProducerVersion,
                snapshot.ProducerBinarySha256, snapshot.Status.ToString());
            Append(builder, snapshot.Drawing.DrawingId, snapshot.Drawing.FileName, snapshot.Drawing.Sha256,
                snapshot.Drawing.FileLength.ToString(CultureInfo.InvariantCulture), snapshot.Drawing.SourceLastWriteUtc,
                snapshot.Drawing.CoordinateSystem, snapshot.Drawing.GeometryUnits);
            Append(builder, snapshot.Profile.ProjectId, snapshot.Profile.ProfileVersion, snapshot.Profile.Sha256, snapshot.FactProviderId);
            Append(builder, "integrity", snapshot.Integrity.SourceHashBefore, snapshot.Integrity.SourceHashAfter,
                snapshot.Integrity.SourceBytesUnchanged.ToString(), snapshot.Integrity.DbmodBefore.ToString(CultureInfo.InvariantCulture),
                snapshot.Integrity.DbmodAfter.ToString(CultureInfo.InvariantCulture), snapshot.Integrity.DbmodCleanAtStart.ToString(),
                snapshot.Integrity.DbmodUnchanged.ToString());
            // v1 旧快照没有以下可选字段。仅非默认模式写入哈希材料，保持旧 v1 快照可验证。
            if (snapshot.Integrity.ScanInputMode != ScanInputMode.ActiveDocument
                || snapshot.Integrity.InputDatabaseReadOnly)
            {
                Append(builder, "scan_input", snapshot.Integrity.ScanInputMode.ToString(),
                    snapshot.Integrity.InputDatabaseReadOnly.ToString());
            }
            AppendSemanticPayloadCore(builder, snapshot);
            return BuildingSemanticStableId.Sha256Text(builder.ToString());
        }

        /// <summary>
        /// 只覆盖识图语义载荷，不包含生产 DLL、生成时间和扫描完整性证据。
        /// JZBPVIEW 用它证明活动图与磁盘侧载快照在显示前仍具有相同语义。
        /// </summary>
        public static string ComputeSemanticPayload(BuildingSemanticSnapshot snapshot)
        {
            if (snapshot == null)
                throw new ArgumentNullException(nameof(snapshot));

            var builder = new StringBuilder();
            Append(builder, "semantic_payload_v1", snapshot.Status.ToString(), snapshot.Drawing.DrawingId,
                snapshot.Drawing.Sha256, snapshot.Profile.ProjectId, snapshot.Profile.ProfileVersion,
                snapshot.Profile.Sha256, snapshot.FactProviderId);
            AppendSemanticPayloadCore(builder, snapshot);
            return BuildingSemanticStableId.Sha256Text(builder.ToString());
        }

        /// <summary>
        /// 只覆盖 JZBPVIEW 实际用于生成瞬态图形的字段。活动文档与磁盘侧载
        /// 对代理核账、复核清单或诊断统计的差异不应阻断高亮；对象类型、墙分类、
        /// 房间用途、显示状态或坐标几何任一变化仍会失败闭合。
        /// </summary>
        public static string ComputeViewPayload(BuildingSemanticSnapshot snapshot)
        {
            if (snapshot == null)
                throw new ArgumentNullException(nameof(snapshot));

            var builder = new StringBuilder();
            Append(builder, "view_payload_v1", snapshot.Drawing.DrawingId, snapshot.Drawing.Sha256,
                snapshot.Profile.ProjectId, snapshot.Profile.ProfileVersion, snapshot.Profile.Sha256);

            var objectPayloads = new List<string>();
            foreach (SemanticObject item in snapshot.Objects ?? new List<SemanticObject>())
            {
                var objectBuilder = new StringBuilder();
                Append(objectBuilder, "object", item.Type.ToString(), item.Classification,
                    item.UseCode, item.Status.ToString());
                AppendViewGeometry(objectBuilder, item.Geometry);
                objectPayloads.Add(objectBuilder.ToString());
            }
            foreach (string payload in objectPayloads.OrderBy(value => value, StringComparer.Ordinal))
                Append(builder, "display_object", payload);

            return BuildingSemanticStableId.Sha256Text(builder.ToString());
        }

        private static void AppendSemanticPayloadCore(StringBuilder builder, BuildingSemanticSnapshot snapshot)
        {
            foreach (string reason in snapshot.ReasonCodes.OrderBy(value => value, StringComparer.Ordinal))
                Append(builder, "reason", reason);
            foreach (SemanticObject item in snapshot.Objects.OrderBy(value => value.SemanticId, StringComparer.Ordinal))
            {
                Append(builder, "object", item.SemanticId, item.Type.ToString(), item.Classification, item.RawLabel, item.UseCode,
                    item.Status.ToString(), Number(item.Confidence), item.Source.DrawingHash, item.Source.StablePath,
                    item.Source.Handle, item.Source.RawLayer, item.Source.EffectiveLayer, item.Source.NormalizedLayer,
                    item.Source.NativeDxfName, item.Source.NativeClassName);
                foreach (string value in item.Source.BlockPath ?? new List<string>())
                    Append(builder, "block_path", value);
                foreach (string value in item.Source.XrefPath ?? new List<string>())
                    Append(builder, "xref_path", value);
                foreach (string value in item.Source.XrefHashes ?? new List<string>())
                    Append(builder, "xref_hash", value);
                foreach (double value in item.Source.WcsTransform ?? new List<double>())
                    Append(builder, "wcs_transform", Number(value));
                AppendGeometry(builder, item.Geometry);
                foreach (SemanticEvidence evidence in item.Evidence.OrderBy(value => value.Code, StringComparer.Ordinal)
                             .ThenBy(value => value.Value, StringComparer.Ordinal)
                             .ThenBy(value => value.SourceHandle, StringComparer.Ordinal)
                             .ThenBy(value => value.Weight))
                    Append(builder, "evidence", evidence.Code, evidence.Kind, evidence.Value, evidence.SourceHandle, Number(evidence.Weight));
                foreach (string reason in item.ReasonCodes.OrderBy(value => value, StringComparer.Ordinal))
                    Append(builder, "object_reason", reason);
            }
            foreach (SpatialRelation relation in snapshot.Relations.OrderBy(value => value.RelationId, StringComparer.Ordinal))
            {
                Append(builder, "relation", relation.RelationId, relation.Type.ToString(), relation.FromSemanticId,
                    relation.ToSemanticId, relation.Status.ToString(), Number(relation.Confidence));
                foreach (SemanticEvidence evidence in relation.Evidence.OrderBy(value => value.Code, StringComparer.Ordinal)
                             .ThenBy(value => value.Value, StringComparer.Ordinal)
                             .ThenBy(value => value.SourceHandle, StringComparer.Ordinal)
                             .ThenBy(value => value.Weight))
                    Append(builder, "relation_evidence", evidence.Code, evidence.Kind, evidence.Value, evidence.SourceHandle, Number(evidence.Weight));
                foreach (string reason in relation.ReasonCodes.OrderBy(value => value, StringComparer.Ordinal))
                    Append(builder, "relation_reason", reason);
            }
            foreach (ProxyLedgerEntry entry in snapshot.ProxyLedger.OrderBy(value => value.StablePath, StringComparer.Ordinal))
                Append(builder, "proxy", entry.StablePath, entry.Handle, entry.OriginalDxfName, entry.OriginalClassName,
                    entry.ApplicationDescription, entry.EffectiveLayer, entry.Disposition.ToString(), entry.ReasonCode);
            foreach (ReviewFinding finding in snapshot.Findings.OrderBy(value => value.FindingId, StringComparer.Ordinal))
                Append(builder, "finding", finding.FindingId, finding.Severity.ToString(), finding.ReasonCode,
                    finding.Message, finding.SemanticId, finding.SourceHandle);
            foreach (ProviderDiagnostic diagnostic in snapshot.ProviderDiagnostics
                         .OrderBy(value => value.StablePath, StringComparer.Ordinal)
                         .ThenBy(value => value.ReasonCode, StringComparer.Ordinal)
                         .ThenBy(value => value.Message, StringComparer.Ordinal))
                Append(builder, "provider_diagnostic", diagnostic.StablePath, diagnostic.Severity.ToString(),
                    diagnostic.ReasonCode, diagnostic.Message);
            SnapshotMetrics metrics = snapshot.Metrics ?? new SnapshotMetrics();
            Append(builder, "metrics_without_elapsed",
                metrics.FactCount.ToString(CultureInfo.InvariantCulture),
                metrics.SemanticObjectCount.ToString(CultureInfo.InvariantCulture),
                metrics.AcceptedObjectCount.ToString(CultureInfo.InvariantCulture),
                metrics.ReviewObjectCount.ToString(CultureInfo.InvariantCulture),
                metrics.RejectedObjectCount.ToString(CultureInfo.InvariantCulture),
                metrics.RelationCount.ToString(CultureInfo.InvariantCulture),
                metrics.ProxyCount.ToString(CultureInfo.InvariantCulture),
                metrics.TopLevelProxyObjectCount.ToString(CultureInfo.InvariantCulture),
                metrics.UniqueProxyHandleCount.ToString(CultureInfo.InvariantCulture),
                metrics.ReachableProxyInstanceCount.ToString(CultureInfo.InvariantCulture),
                metrics.SupportedProxyCount.ToString(CultureInfo.InvariantCulture),
                metrics.IgnoredAnnotationProxyCount.ToString(CultureInfo.InvariantCulture),
                metrics.IgnoredOutOfScopeProxyCount.ToString(CultureInfo.InvariantCulture),
                metrics.ReviewUnknownProxyCount.ToString(CultureInfo.InvariantCulture));
        }

        private static void AppendGeometry(StringBuilder builder, SemanticGeometry geometry)
        {
            if (geometry == null)
            {
                Append(builder, "geometry", "null");
                return;
            }
            Append(builder, "geometry", geometry.Kind.ToString(), geometry.IsClosed.ToString(), geometry.IsExact.ToString(), geometry.ExtractionMethod);
            SemanticBounds bounds = geometry.Bounds ?? new SemanticBounds();
            Append(builder, "bounds", bounds.IsValid.ToString(), Number(bounds.MinX), Number(bounds.MinY), Number(bounds.MinZ),
                Number(bounds.MaxX), Number(bounds.MaxY), Number(bounds.MaxZ));
            foreach (List<SemanticPoint> path in geometry.Paths ?? new List<List<SemanticPoint>>())
            {
                Append(builder, "path", path.Count.ToString(CultureInfo.InvariantCulture));
                foreach (SemanticPoint point in path)
                    Append(builder, Number(point.X), Number(point.Y), Number(point.Z));
            }
        }

        private static void AppendViewGeometry(StringBuilder builder, SemanticGeometry geometry)
        {
            SemanticGeometry safeGeometry = geometry ?? new SemanticGeometry();
            Append(builder, "view_geometry", safeGeometry.Kind.ToString());
            foreach (List<SemanticPoint> path in safeGeometry.Paths ?? new List<List<SemanticPoint>>())
            {
                Append(builder, "view_path", path.Count.ToString(CultureInfo.InvariantCulture));
                foreach (SemanticPoint point in path)
                    Append(builder, Number(point.X), Number(point.Y), Number(point.Z));
            }
        }

        private static string Number(double value)
        {
            return Math.Round(value, 6, MidpointRounding.AwayFromZero).ToString("0.######", CultureInfo.InvariantCulture);
        }

        private static void Append(StringBuilder builder, params string[] values)
        {
            foreach (string value in values)
            {
                string safe = value ?? string.Empty;
                builder.Append(safe.Length.ToString(CultureInfo.InvariantCulture));
                builder.Append(':');
                builder.Append(safe);
                builder.Append('|');
            }
            builder.Append('\n');
        }
    }
}
