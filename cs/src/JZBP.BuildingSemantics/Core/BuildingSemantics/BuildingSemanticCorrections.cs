// SPDX-License-Identifier: MPL-2.0
// Copyright (c) 2026 张田; 著作权人、原作者及维护者：张田；其他贡献者和第三方保留各自权利。
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;

namespace JZBP.BuildingSemantics.Core
{
    public sealed class BuildingSemanticOverrideDocument
    {
        public string SchemaVersion { get; set; } = BuildingSemanticSchema.OverrideV1;
        public string OverrideId { get; set; } = string.Empty;
        public string Status { get; set; } = string.Empty;
        public string DrawingSha256 { get; set; } = string.Empty;
        public string SourceSemanticsHash { get; set; } = string.Empty;
        public string SourceProducerVersion { get; set; } = string.Empty;
        public string SourceProducerBinarySha256 { get; set; } = string.Empty;
        public string ProjectId { get; set; } = string.Empty;
        public string CreatedAtUtc { get; set; } = string.Empty;
        public string CreatedBy { get; set; } = string.Empty;
        public string ReviewedAtUtc { get; set; } = string.Empty;
        public string ReviewedBy { get; set; } = string.Empty;
        public string Reason { get; set; } = string.Empty;
        public List<BuildingSemanticOverrideChange> Changes { get; set; } = new List<BuildingSemanticOverrideChange>();
    }

    public sealed class BuildingSemanticOverrideChange
    {
        public string ChangeId { get; set; } = string.Empty;
        public string SemanticId { get; set; } = string.Empty;
        public string SourceHandle { get; set; } = string.Empty;
        public string? ExpectedClassification { get; set; }
        public string? ExpectedUseCode { get; set; }
        public string? ReplacementClassification { get; set; }
        public string? ReplacementUseCode { get; set; }
        public string Reason { get; set; } = string.Empty;
    }

    public sealed class SemanticOverrideApplicationResult
    {
        public BuildingSemanticSnapshot Snapshot { get; set; } = new BuildingSemanticSnapshot();
        public bool Applied { get; set; }
        public string OverrideId { get; set; } = string.Empty;
        public int AppliedChangeCount { get; set; }
    }

    public static class BuildingSemanticOverrideResolver
    {
        public static SemanticOverrideApplicationResult Apply(
            BuildingSemanticSnapshot rawSnapshot,
            BuildingSemanticOverrideDocument document)
        {
            ValidateHeader(rawSnapshot, document);
            BuildingSemanticSnapshot resolved = Clone(rawSnapshot);
            var seenTargets = new HashSet<string>(StringComparer.Ordinal);
            var seenChanges = new HashSet<string>(StringComparer.Ordinal);
            foreach (BuildingSemanticOverrideChange change in document.Changes)
            {
                ValidateChange(change);
                if (!seenChanges.Add(change.ChangeId))
                    throw new InvalidDataException("覆盖文件中的 change_id 必须唯一。");
                if (!seenTargets.Add(change.SemanticId))
                    throw new InvalidDataException("同一 semantic_id 不能在一个覆盖文件中重复修改。");

                SemanticObject target = resolved.Objects.SingleOrDefault(item =>
                    string.Equals(item.SemanticId, change.SemanticId, StringComparison.Ordinal))
                    ?? throw new InvalidDataException("覆盖目标 semantic_id 不存在: " + change.SemanticId);
                if (!string.Equals(target.Source.Handle, change.SourceHandle, StringComparison.OrdinalIgnoreCase)
                    || !string.Equals(target.Classification, change.ExpectedClassification, StringComparison.Ordinal)
                    || !string.Equals(target.UseCode, change.ExpectedUseCode, StringComparison.Ordinal))
                    throw new InvalidDataException("覆盖目标的 Handle 或修改前值与原始 L3 不一致: " + change.SemanticId);
                if (target.Status == DecisionStatus.Rejected)
                    throw new InvalidDataException("Rejected 对象不能通过试点覆盖恢复: " + change.SemanticId);
                if (string.Equals(target.Classification, change.ReplacementClassification, StringComparison.Ordinal)
                    && string.Equals(target.UseCode, change.ReplacementUseCode, StringComparison.Ordinal))
                    throw new InvalidDataException("覆盖变更没有产生实际差异: " + change.SemanticId);

                target.Classification = change.ReplacementClassification ?? string.Empty;
                target.UseCode = change.ReplacementUseCode ?? string.Empty;
                target.Status = DecisionStatus.Review;
                target.ReasonCodes.Add(BuildingSemanticReasonCodes.SemanticOverrideApplied);
                target.Evidence.Add(new SemanticEvidence
                {
                    Code = BuildingSemanticReasonCodes.SemanticOverrideApplied,
                    Kind = "human_review",
                    Value = document.OverrideId + "/" + change.ChangeId,
                    SourceHandle = target.Source.Handle,
                    Weight = 1
                });
                resolved.Findings.Add(CreateFinding(resolved, document, change));
            }

            resolved.Status = AnalysisRunStatus.Review;
            resolved.ReasonCodes.Add(BuildingSemanticReasonCodes.SemanticOverrideApplied);
            FinalizeResolvedSnapshot(resolved);
            return new SemanticOverrideApplicationResult
            {
                Snapshot = resolved,
                Applied = true,
                OverrideId = document.OverrideId,
                AppliedChangeCount = document.Changes.Count
            };
        }

        public static BuildingSemanticSnapshot FailClosed(BuildingSemanticSnapshot rawSnapshot, string message)
        {
            BuildingSemanticSnapshot failed = Clone(rawSnapshot);
            failed.Status = AnalysisRunStatus.Failed;
            failed.ReasonCodes.Add(BuildingSemanticReasonCodes.SemanticOverrideInvalid);
            foreach (SemanticObject item in failed.Objects.Where(item => item.Status == DecisionStatus.Accepted))
                item.Status = DecisionStatus.Review;
            foreach (SpatialRelation relation in failed.Relations.Where(item => item.Status == DecisionStatus.Accepted))
                relation.Status = DecisionStatus.Review;
            failed.Findings.Add(new ReviewFinding
            {
                FindingId = BuildingSemanticStableId.Create("finding", failed.Drawing.Sha256,
                    BuildingSemanticReasonCodes.SemanticOverrideInvalid, message ?? string.Empty),
                Severity = FindingSeverity.Error,
                ReasonCode = BuildingSemanticReasonCodes.SemanticOverrideInvalid,
                Message = message ?? string.Empty
            });
            FinalizeResolvedSnapshot(failed);
            return failed;
        }

        private static void ValidateHeader(BuildingSemanticSnapshot raw, BuildingSemanticOverrideDocument document)
        {
            if (raw == null || document == null)
                throw new ArgumentNullException(raw == null ? nameof(raw) : nameof(document));
            if (raw.Status == AnalysisRunStatus.Failed)
                throw new InvalidDataException("Failed 原始 L3 不能应用覆盖。");
            if (!string.Equals(document.SchemaVersion, BuildingSemanticSchema.OverrideV1, StringComparison.Ordinal)
                || !string.Equals(document.Status, "approved", StringComparison.Ordinal)
                || string.IsNullOrWhiteSpace(document.OverrideId) || string.IsNullOrWhiteSpace(document.CreatedBy)
                || string.IsNullOrWhiteSpace(document.ReviewedBy)
                || string.IsNullOrWhiteSpace(document.Reason) || document.Changes == null || document.Changes.Count == 0)
                throw new InvalidDataException("覆盖文件不是完整的 approved building-semantics.override.v1。");
            if (!IsUtcTimestamp(document.CreatedAtUtc) || !IsUtcTimestamp(document.ReviewedAtUtc))
                throw new InvalidDataException("覆盖文件必须提供 ISO-8601 UTC 创建和审核时间。");
            if (!string.Equals(document.DrawingSha256, raw.Drawing.Sha256, StringComparison.OrdinalIgnoreCase)
                || !string.Equals(document.SourceSemanticsHash, raw.DeterministicContentHash, StringComparison.OrdinalIgnoreCase)
                || !string.Equals(document.SourceProducerVersion, raw.ProducerVersion, StringComparison.Ordinal)
                || !string.Equals(document.SourceProducerBinarySha256, raw.ProducerBinarySha256, StringComparison.OrdinalIgnoreCase)
                || !string.Equals(document.ProjectId, raw.Profile.ProjectId, StringComparison.Ordinal))
                throw new InvalidDataException("覆盖文件与当前 DWG、原始 L3、生产 DLL 或项目空间不一致。");
        }

        private static void ValidateChange(BuildingSemanticOverrideChange change)
        {
            if (change == null || string.IsNullOrWhiteSpace(change.ChangeId)
                || string.IsNullOrWhiteSpace(change.SemanticId) || string.IsNullOrWhiteSpace(change.SourceHandle)
                || change.ExpectedClassification == null || change.ExpectedUseCode == null
                || change.ReplacementClassification == null || change.ReplacementUseCode == null
                || string.IsNullOrWhiteSpace(change.Reason))
                throw new InvalidDataException("覆盖变更缺少必填字段。");
        }

        private static bool IsUtcTimestamp(string value)
        {
            return DateTimeOffset.TryParse(value, CultureInfo.InvariantCulture, DateTimeStyles.RoundtripKind,
                       out DateTimeOffset parsed)
                   && parsed.Offset == TimeSpan.Zero;
        }

        private static ReviewFinding CreateFinding(
            BuildingSemanticSnapshot snapshot,
            BuildingSemanticOverrideDocument document,
            BuildingSemanticOverrideChange change)
        {
            return new ReviewFinding
            {
                FindingId = BuildingSemanticStableId.Create("finding", snapshot.Drawing.Sha256, document.OverrideId, change.ChangeId),
                Severity = FindingSeverity.Review,
                ReasonCode = BuildingSemanticReasonCodes.SemanticOverrideApplied,
                Message = change.Reason,
                SemanticId = change.SemanticId,
                SourceHandle = change.SourceHandle
            };
        }

        private static BuildingSemanticSnapshot Clone(BuildingSemanticSnapshot snapshot)
        {
            return BuildingSemanticJson.DeserializeSnapshot(BuildingSemanticJson.SerializeSnapshot(snapshot));
        }

        private static void FinalizeResolvedSnapshot(BuildingSemanticSnapshot snapshot)
        {
            snapshot.ReasonCodes = snapshot.ReasonCodes.Distinct(StringComparer.Ordinal)
                .OrderBy(value => value, StringComparer.Ordinal).ToList();
            foreach (SemanticObject item in snapshot.Objects)
                item.ReasonCodes = item.ReasonCodes.Distinct(StringComparer.Ordinal)
                    .OrderBy(value => value, StringComparer.Ordinal).ToList();
            snapshot.Findings = snapshot.Findings.GroupBy(item => item.FindingId, StringComparer.Ordinal)
                .Select(group => group.First()).OrderBy(item => item.FindingId, StringComparer.Ordinal).ToList();
            snapshot.Metrics.SemanticObjectCount = snapshot.Objects.Count;
            snapshot.Metrics.AcceptedObjectCount = snapshot.Objects.Count(item => item.Status == DecisionStatus.Accepted);
            snapshot.Metrics.ReviewObjectCount = snapshot.Objects.Count(item => item.Status == DecisionStatus.Review);
            snapshot.Metrics.RejectedObjectCount = snapshot.Objects.Count(item => item.Status == DecisionStatus.Rejected);
            snapshot.Metrics.RelationCount = snapshot.Relations.Count;
            snapshot.DeterministicContentHash = BuildingSemanticDeterminism.Compute(snapshot);
        }
    }
}
