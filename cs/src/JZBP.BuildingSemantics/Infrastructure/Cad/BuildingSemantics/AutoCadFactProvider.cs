// SPDX-License-Identifier: MPL-2.0
// Copyright (c) 2026 张田; 著作权人、原作者及维护者：张田；其他贡献者和第三方保留各自权利。
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.DatabaseServices.Filters;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using JZBP.BuildingSemantics.Core;

namespace JZBP.BuildingSemantics.Infrastructure.Cad
{
    /// <summary>
    /// 只读事实适配器。优先解释已加载的 T20 原生对象；只有图中不存在 T20
    /// 建筑语义对象时才允许普通 CAD 兜底。所有事务均为 ForRead，Explode 仅作用于内存临时对象。
    /// </summary>
    internal sealed class AutoCadBuildingFactProvider : ICadFactProvider
    {
        private readonly Database _database;

        public AutoCadBuildingFactProvider(Database database)
        {
            _database = database ?? throw new ArgumentNullException(nameof(database));
        }

        public string ProviderId => "autocad2016:t20-first:readonly:v1";

        public DrawingSnapshot Collect(CadFactRequest request)
        {
            if (request?.Analysis?.Profile == null)
                throw new ArgumentException("CadFactRequest 缺少 Analysis/Profile。", nameof(request));

            var stopwatch = Stopwatch.StartNew();
            var snapshot = new CadFactSnapshot { ProviderId = ProviderId };
            var state = new ScanState(request.Analysis, snapshot);

            UnitsValue drawingUnits = _database.Insunits;
            if (drawingUnits != UnitsValue.Undefined && drawingUnits != UnitsValue.Millimeters)
            {
                snapshot.IsSuccess = false;
                snapshot.ReasonCodes.Add(BuildingSemanticReasonCodes.UnitMismatch);
                snapshot.Diagnostics.Add(new ProviderDiagnostic
                {
                    Severity = FindingSeverity.Error,
                    ReasonCode = BuildingSemanticReasonCodes.UnitMismatch,
                    Message = "DWG INSUNITS=" + drawingUnits + "，与 ProjectProfile 的 mm 冲突。"
                });
                stopwatch.Stop();
                snapshot.ElapsedMilliseconds = stopwatch.ElapsedMilliseconds;
                return DrawingSnapshot.Freeze(snapshot);
            }

            if (drawingUnits == UnitsValue.Undefined)
            {
                snapshot.Diagnostics.Add(new ProviderDiagnostic
                {
                    Severity = FindingSeverity.Information,
                    ReasonCode = "INSUNITS_UNDEFINED_PROFILE_MM",
                    Message = "DWG INSUNITS=0；按已冻结 ProjectProfile 以毫米解释，不从几何猜测单位。"
                });
            }

            using (Transaction transaction = _database.TransactionManager.StartOpenCloseTransaction())
            {
                BlockTable? table = transaction.GetObject(_database.BlockTableId, OpenMode.ForRead) as BlockTable;
                if (table == null)
                    throw new InvalidOperationException("无法读取 BlockTable。");
                var stack = new HashSet<ObjectId>();
                TraverseRecord(
                    table[BlockTableRecord.ModelSpace],
                    transaction,
                    Matrix3d.Identity,
                    new List<string>(),
                    new List<string>(),
                    new List<string>(),
                    new List<ClipBoundary>(),
                    string.Empty,
                    stack,
                    state);
            }

            if (state.XclipFilterCount > 0)
            {
                snapshot.Diagnostics.Add(new ProviderDiagnostic
                {
                    Severity = FindingSeverity.Information,
                    ReasonCode = "XCLIP_VISIBILITY_APPLIED",
                    Message = "已读取 " + state.XclipFilterCount.ToString(CultureInfo.InvariantCulture)
                              + " 个启用的块/外参裁剪窗口；L1/L2 保留对象账本，L3 排除其中 "
                              + state.XclipHiddenPrimitiveCount.ToString(CultureInfo.InvariantCulture) + " 个不可见实例。"
                });
            }

            snapshot.Facts = state.NativeT20ObjectCount > 0
                ? state.T20Facts.Concat(state.StandardFacts.Where(fact => fact.Kind == CadFactKind.Text)).ToList()
                : new List<CadFact>(state.StandardFacts);
            snapshot.DetectedT20 = state.DetectedT20;
            snapshot.T20InterpreterAvailable = state.DetectedT20 && state.UnresolvedSemanticT20Count == 0 && state.NativeT20ObjectCount > 0;

            if (state.XclipReadFailureCount > 0)
            {
                snapshot.IsSuccess = false;
                AddReason(snapshot.ReasonCodes, BuildingSemanticReasonCodes.XclipFilterUnreadable);
                snapshot.Facts.Clear();
            }
            else if (state.UnresolvedSemanticT20Count > 0)
            {
                snapshot.IsSuccess = false;
                AddReason(snapshot.ReasonCodes, BuildingSemanticReasonCodes.T20InterpreterRequired);
                snapshot.Diagnostics.Add(new ProviderDiagnostic
                {
                    Severity = FindingSeverity.Error,
                    ReasonCode = BuildingSemanticReasonCodes.T20InterpreterRequired,
                    Message = "发现 " + state.UnresolvedSemanticT20Count.ToString(CultureInfo.InvariantCulture)
                              + " 个未解释的 T20 建筑语义代理对象；禁止返回普通 CAD 部分成功。"
                });
                snapshot.Facts.Clear();
            }
            else if (state.NativeSemanticT20Count > 0 && state.NativeT20GeometryFailureCount > 0)
            {
                snapshot.IsSuccess = false;
                AddReason(snapshot.ReasonCodes, BuildingSemanticReasonCodes.T20NativeGeometryUnavailable);
                AppendNativeGeometryFailureDiagnostics(state);
                snapshot.Diagnostics.Add(new ProviderDiagnostic
                {
                    Severity = FindingSeverity.Error,
                    ReasonCode = BuildingSemanticReasonCodes.T20NativeGeometryUnavailable,
                    Message = state.NativeT20GeometryFailureCount.ToString(CultureInfo.InvariantCulture)
                              + " 个必需 T20 原生对象未形成精确源几何；整次分析失败，禁止用代理包围盒或其余对象冒充部分成功。"
                });
                snapshot.Facts.Clear();
            }
            else
            {
                snapshot.IsSuccess = true;
                snapshot.ProviderId = state.DetectedT20
                    ? "autocad2016:t20-native-readonly:v1"
                    : "autocad2016:standard-cad-readonly:v1";
                if (snapshot.ReasonCodes.Count == 0)
                    snapshot.ReasonCodes.Add(BuildingSemanticReasonCodes.Ok);
            }

            snapshot.Facts = snapshot.Facts
                .OrderBy(fact => fact.Source.StablePath, StringComparer.Ordinal)
                .ThenBy(fact => fact.Kind)
                .ThenBy(fact => fact.FactId, StringComparer.Ordinal)
                .ToList();
            var primitivesByPath = state.RawPrimitives
                .GroupBy(item => item.Source?.StablePath ?? string.Empty, StringComparer.Ordinal)
                .ToDictionary(group => group.Key, group => group.First(), StringComparer.Ordinal);
            foreach (CadFact fact in snapshot.Facts)
                primitivesByPath[fact.Source?.StablePath ?? string.Empty] = CadPrimitiveSnapshotBuilder.FromFact(fact);
            snapshot.Primitives = primitivesByPath.Values
                .OrderBy(item => item.Source?.StablePath ?? string.Empty, StringComparer.Ordinal)
                .ThenBy(item => item.Kind)
                .ThenBy(item => item.PrimitiveId, StringComparer.Ordinal)
                .ToList();
            snapshot.ProxyLedger = snapshot.ProxyLedger
                .OrderBy(entry => entry.StablePath, StringComparer.Ordinal)
                .ThenBy(entry => entry.Handle, StringComparer.Ordinal)
                .ToList();
            stopwatch.Stop();
            snapshot.ElapsedMilliseconds = stopwatch.ElapsedMilliseconds;
            return DrawingSnapshot.Freeze(snapshot);
        }

        private static void TraverseRecord(
            ObjectId recordId,
            Transaction transaction,
            Matrix3d parentTransform,
            List<string> blockPath,
            List<string> xrefPath,
            List<string> xrefHashes,
            List<ClipBoundary> activeClips,
            string inheritedLayer,
            HashSet<ObjectId> stack,
            ScanState state)
        {
            if (recordId.IsNull || stack.Contains(recordId))
                return;

            BlockTableRecord? record;
            try
            {
                record = transaction.GetObject(recordId, OpenMode.ForRead) as BlockTableRecord;
            }
            catch (System.Exception ex)
            {
                AddDiagnostic(state, FindingSeverity.Review, BuildingSemanticReasonCodes.NestedTransformFailed,
                    "块定义读取失败: " + ex.Message, string.Join("/", blockPath));
                return;
            }
            if (record == null || record.IsLayout && !string.Equals(record.Name, BlockTableRecord.ModelSpace, StringComparison.OrdinalIgnoreCase))
                return;

            stack.Add(recordId);
            try
            {
                foreach (ObjectId objectId in record)
                {
                    Entity? entity;
                    try
                    {
                        entity = transaction.GetObject(objectId, OpenMode.ForRead) as Entity;
                    }
                    catch (System.Exception ex)
                    {
                        AddDiagnostic(state, FindingSeverity.Review, BuildingSemanticReasonCodes.FactProviderFailed,
                            "实体只读打开失败: " + ex.Message, string.Join("/", blockPath));
                        continue;
                    }
                    if (entity == null)
                        continue;

                    string handle = SafeHandle(entity);
                    string rawLayer = SafeLayer(entity);
                    string effectiveLayer = string.Equals(rawLayer, "0", StringComparison.OrdinalIgnoreCase)
                        ? inheritedLayer
                        : rawLayer;
                    if (string.IsNullOrWhiteSpace(effectiveLayer))
                        effectiveLayer = rawLayer;
                    string stablePath = BuildStablePath(blockPath, handle);

                    if (!IsFinite(parentTransform))
                    {
                        AddDiagnostic(state, FindingSeverity.Error, BuildingSemanticReasonCodes.NestedTransformFailed,
                            "嵌套块变换包含 NaN/Infinity。", stablePath);
                        continue;
                    }

                    NativeIdentity identity = NativeIdentity.Read(entity);
                    bool isT20 = T20Classifier.IsT20(identity);
                    CadFactKind t20Kind = T20Classifier.Classify(identity);
                    bool isT20Annotation = isT20 && T20Classifier.IsAnnotation(identity);
                    bool isT20OutOfScope = isT20 && T20Classifier.IsExplicitlyOutOfScope(identity);
                    if (isT20)
                        state.DetectedT20 = true;

                    // 第一层保留原始 CAD 身份和几何；T20 精确事实稍后覆盖原始身份，避免重复分解。
                    CadPrimitive rawPrimitive = BuildRawPrimitive(
                        entity,
                        identity,
                        parentTransform,
                        blockPath,
                        xrefPath,
                        xrefHashes,
                        rawLayer,
                        effectiveLayer,
                        stablePath,
                        isT20,
                        transaction,
                        state);
                    StampXclipVisibility(
                        rawPrimitive.RawProperties,
                        rawPrimitive.RawGeometry,
                        activeClips,
                        state,
                        true);
                    state.RawPrimitives.Add(rawPrimitive);

                    if (entity is ProxyEntity proxy)
                    {
                        ProxyDisposition disposition;
                        string reason;
                        if (isT20Annotation)
                        {
                            disposition = ProxyDisposition.IgnoredAnnotation;
                            reason = "T20_ANNOTATION_IGNORED";
                        }
                        else if (isT20OutOfScope)
                        {
                            disposition = ProxyDisposition.IgnoredOutOfScope;
                            reason = BuildingSemanticReasonCodes.T20OutOfScopeIgnored;
                        }
                        else if (isT20)
                        {
                            disposition = ProxyDisposition.ReviewUnknown;
                            reason = BuildingSemanticReasonCodes.T20InterpreterRequired;
                            state.UnresolvedSemanticT20Count++;
                        }
                        else
                        {
                            disposition = ProxyDisposition.ReviewUnknown;
                            reason = BuildingSemanticReasonCodes.UnsupportedProxyObject;
                        }

                        state.Snapshot.ProxyLedger.Add(new ProxyLedgerEntry
                        {
                            StablePath = stablePath,
                            Handle = handle,
                            OriginalDxfName = proxy.OriginalDxfName ?? identity.DxfName,
                            OriginalClassName = proxy.OriginalClassName ?? identity.ClassName,
                            ApplicationDescription = proxy.ApplicationDescription ?? string.Empty,
                            EffectiveLayer = effectiveLayer,
                            Disposition = disposition,
                            ReasonCode = reason
                        });
                    }
                    else if (isT20)
                    {
                        if (!isT20Annotation && !isT20OutOfScope)
                            state.NativeT20ObjectCount++;
                        ProxyDisposition disposition = t20Kind == CadFactKind.Text
                            ? ProxyDisposition.SupportedFact
                            : isT20Annotation
                            ? ProxyDisposition.IgnoredAnnotation
                            : isT20OutOfScope
                                ? ProxyDisposition.IgnoredOutOfScope
                            : t20Kind != CadFactKind.Unknown
                                ? ProxyDisposition.SupportedFact
                                : ProxyDisposition.ReviewUnknown;
                        string reason = disposition == ProxyDisposition.SupportedFact
                            ? BuildingSemanticReasonCodes.Ok
                            : disposition == ProxyDisposition.IgnoredAnnotation
                                ? "T20_ANNOTATION_IGNORED"
                                : disposition == ProxyDisposition.IgnoredOutOfScope
                                    ? BuildingSemanticReasonCodes.T20OutOfScopeIgnored
                                : BuildingSemanticReasonCodes.UnsupportedProxyObject;
                        state.Snapshot.ProxyLedger.Add(new ProxyLedgerEntry
                        {
                            StablePath = stablePath,
                            Handle = handle,
                            OriginalDxfName = identity.DxfName,
                            OriginalClassName = identity.ClassName,
                            ApplicationDescription = identity.AppName,
                            EffectiveLayer = effectiveLayer,
                            Disposition = disposition,
                            ReasonCode = reason
                        });
                        if (disposition == ProxyDisposition.ReviewUnknown)
                        {
                            AddDiagnostic(state, FindingSeverity.Review, BuildingSemanticReasonCodes.UnsupportedProxyObject,
                                "T20 对象已核账但尚无事实映射。", stablePath);
                        }
                    }

                    if (isT20
                        && !(entity is ProxyEntity)
                        && t20Kind != CadFactKind.Unknown)
                    {
                        bool requiresExactNativeGeometry = t20Kind != CadFactKind.Text;
                        if (requiresExactNativeGeometry)
                            state.NativeSemanticT20Count++;
                        CadFact fact = BuildFact(entity, identity, t20Kind, parentTransform, blockPath, xrefPath, xrefHashes,
                            rawLayer, effectiveLayer, stablePath, true, transaction, state);
                        if (fact != null)
                        {
                            StampXclipVisibility(fact.Properties, fact.Geometry, activeClips, state, false);
                            state.T20Facts.Add(fact);
                            if (requiresExactNativeGeometry)
                            {
                                if (SemanticGeometryAlgorithms.IsUsable(fact.Geometry, true))
                                    state.NativeT20GeometrySuccessCount++;
                                else
                                    state.NativeT20GeometryFailureCount++;
                            }
                        }
                    }
                    else if (!isT20 && !(entity is ProxyEntity))
                    {
                        CadFactKind standardKind = StandardCadClassifier.Classify(entity, identity, effectiveLayer, transaction);
                        if (standardKind != CadFactKind.Unknown && standardKind != CadFactKind.Annotation)
                        {
                            CadFact fact = BuildFact(entity, identity, standardKind, parentTransform, blockPath, xrefPath, xrefHashes,
                                rawLayer, effectiveLayer, stablePath, false, transaction, state);
                            if (fact != null)
                            {
                                StampXclipVisibility(fact.Properties, fact.Geometry, activeClips, state, false);
                                state.StandardFacts.Add(fact);
                            }
                        }
                    }

                    if (entity is BlockReference blockReference)
                    {
                        List<string> nextBlockPath = new List<string>(blockPath)
                        {
                            handle + ":" + ResolveBlockName(blockReference.BlockTableRecord, transaction)
                        };
                        List<string> nextXrefPath = new List<string>(xrefPath);
                        List<string> nextXrefHashes = new List<string>(xrefHashes);
                        ObjectId childRecordId = blockReference.BlockTableRecord;
                        try
                        {
                            BlockTableRecord? child = transaction.GetObject(childRecordId, OpenMode.ForRead) as BlockTableRecord;
                            if (child != null && child.IsFromExternalReference)
                            {
                                nextXrefPath.Add(child.Name ?? string.Empty);
                                string xrefHash = ResolveXrefHash(child.PathName, state);
                                nextXrefHashes.Add(xrefHash);
                                if (string.Equals(xrefHash, "UNAVAILABLE", StringComparison.Ordinal))
                                {
                                    AddDiagnostic(state, FindingSeverity.Review, BuildingSemanticReasonCodes.XrefHashUnavailable,
                                        "外参文件无法解析或计算 SHA-256。", stablePath);
                                }
                            }
                        }
                        catch
                        {
                        }

                        try
                        {
                            Matrix3d combined = blockReference.BlockTransform.PreMultiplyBy(parentTransform);
                            var nextClips = new List<ClipBoundary>(activeClips);
                            ClipBoundary? clip = ReadXclipBoundary(
                                blockReference,
                                parentTransform,
                                string.Join("/", nextBlockPath),
                                transaction,
                                state);
                            if (clip != null)
                                nextClips.Add(clip);
                            TraverseRecord(childRecordId, transaction, combined, nextBlockPath, nextXrefPath, nextXrefHashes,
                                nextClips, effectiveLayer, stack, state);
                        }
                        catch (System.Exception ex)
                        {
                            AddDiagnostic(state, FindingSeverity.Review, BuildingSemanticReasonCodes.NestedTransformFailed,
                                "块变换失败: " + ex.Message, stablePath);
                        }
                    }
                }
            }
            finally
            {
                stack.Remove(recordId);
            }
        }

        private static ClipBoundary? ReadXclipBoundary(
            BlockReference blockReference,
            Matrix3d parentTransform,
            string stablePath,
            Transaction transaction,
            ScanState state)
        {
            if (blockReference.ExtensionDictionary.IsNull)
                return null;
            try
            {
                DBDictionary? extension = transaction.GetObject(
                    blockReference.ExtensionDictionary,
                    OpenMode.ForRead) as DBDictionary;
                if (extension == null || !extension.Contains("ACAD_FILTER"))
                    return null;
                DBDictionary? filters = transaction.GetObject(
                    extension.GetAt("ACAD_FILTER"),
                    OpenMode.ForRead) as DBDictionary;
                if (filters == null || !filters.Contains("SPATIAL"))
                    return null;
                SpatialFilter? filter = transaction.GetObject(
                    filters.GetAt("SPATIAL"),
                    OpenMode.ForRead) as SpatialFilter;
                if (filter == null)
                    throw new InvalidDataException("SPATIAL 记录不是 SpatialFilter。");

                SpatialFilterDefinition definition = filter.Definition;
                if (!definition.Enabled)
                    return null;
                Point2dCollection points = definition.GetPoints();
                var local = new List<Point2d>();
                if (points.Count == 2)
                {
                    Point2d first = points[0];
                    Point2d second = points[1];
                    local.Add(new Point2d(first.X, first.Y));
                    local.Add(new Point2d(second.X, first.Y));
                    local.Add(new Point2d(second.X, second.Y));
                    local.Add(new Point2d(first.X, second.Y));
                }
                else
                {
                    foreach (Point2d point in points)
                        local.Add(point);
                }
                if (local.Count < 3)
                    throw new InvalidDataException("XCLIP 边界少于三个顶点。");

                Matrix3d clipToWcs = ComposeXclipTransform(
                    filter.ClipSpaceToWorldCoordinateSystemTransform,
                    filter.OriginalInverseBlockTransform,
                    blockReference.BlockTransform,
                    parentTransform);
                List<SemanticPoint> world = local
                    .Select(point => new Point3d(point.X, point.Y, 0).TransformBy(clipToWcs))
                    .Select(point => new SemanticPoint(point.X, point.Y, point.Z))
                    .ToList();
                if (world.Any(point => !SemanticGeometryAlgorithms.IsFinite(point)))
                    throw new InvalidDataException("XCLIP 边界变换后包含 NaN/Infinity。");

                var geometry = new SemanticGeometry
                {
                    Kind = GeometryKind.Polygon,
                    IsClosed = true,
                    IsExact = true,
                    ExtractionMethod = "autocad_spatial_filter_boundary",
                    Paths = new List<List<SemanticPoint>> { world }
                };
                geometry.Bounds = SemanticGeometryAlgorithms.CalculateBounds(geometry.Paths);
                if (state.XclipDiagnosticEnabled)
                {
                    AddDiagnostic(
                        state,
                        FindingSeverity.Information,
                        "XCLIP_VISIBILITY_APPLIED",
                        "XCLIP_TRACE enabled=true;inverted=" + filter.Inverted
                        + ";local_points=" + string.Join("|", local.Select(FormatPoint))
                        + ";clip_to_wcs=" + FormatMatrix(filter.ClipSpaceToWorldCoordinateSystemTransform)
                        + ";original_inverse_block=" + FormatMatrix(filter.OriginalInverseBlockTransform)
                        + ";parent=" + FormatMatrix(parentTransform)
                        + ";block=" + FormatMatrix(blockReference.BlockTransform)
                        + ";effective=" + FormatMatrix(clipToWcs)
                        + ";wcs_bounds=" + FormatBounds(geometry.Bounds),
                        stablePath);
                }
                state.XclipFilterCount++;
                return new ClipBoundary
                {
                    StablePath = stablePath,
                    Geometry = geometry,
                    Inverted = filter.Inverted
                };
            }
            catch (System.Exception ex)
            {
                state.XclipReadFailureCount++;
                AddDiagnostic(
                    state,
                    FindingSeverity.Error,
                    BuildingSemanticReasonCodes.XclipFilterUnreadable,
                    "块/外参存在 XCLIP，但无法读取裁剪边界: " + ex.Message,
                    stablePath);
                return null;
            }
        }

        private static void StampXclipVisibility(
            IDictionary<string, string> properties,
            SemanticGeometry? geometry,
            IReadOnlyList<ClipBoundary> activeClips,
            ScanState state,
            bool countHiddenPrimitive)
        {
            if (activeClips == null || activeClips.Count == 0)
                return;
            List<SemanticPoint> points = (geometry?.Paths ?? new List<List<SemanticPoint>>())
                .Where(path => path != null)
                .SelectMany(path => path)
                .Where(SemanticGeometryAlgorithms.IsFinite)
                .ToList();
            properties["xclip_filter_paths"] = string.Join("|", activeClips.Select(clip => clip.StablePath));
            if (points.Count == 0)
            {
                properties["xclip_visibility"] = "unknown";
                return;
            }

            bool hidden;
            if (!state.XclipDiagnosticEnabled)
            {
                hidden = activeClips.Any(clip => clip.Inverted
                    ? points.All(point => SemanticGeometryAlgorithms.ContainsPoint(clip.Geometry, point))
                    : !SemanticGeometryAlgorithms.Intersects2D(geometry, clip.Geometry));
            }
            else
            {
                var decisions = activeClips.Select(clip => new
                {
                    Clip = clip,
                    BoundsIntersect = SemanticGeometryAlgorithms.BoundsIntersect(geometry, clip.Geometry, 0),
                    Intersects = SemanticGeometryAlgorithms.Intersects2D(geometry, clip.Geometry),
                    AllPointsInside = points.All(point => SemanticGeometryAlgorithms.ContainsPoint(clip.Geometry, point))
                }).ToList();
                hidden = decisions.Any(item => item.Clip.Inverted
                    ? item.AllPointsInside
                    : !item.Intersects);
                properties["xclip_diagnostic"] = string.Join("|", decisions.Select(item =>
                    item.Clip.StablePath
                    + ":inverted=" + item.Clip.Inverted
                    + ",bounds_intersect=" + item.BoundsIntersect
                    + ",intersects=" + item.Intersects
                    + ",all_points_inside=" + item.AllPointsInside
                    + ",clip_bounds=" + FormatBounds(item.Clip.Geometry.Bounds)));
            }
            properties["xclip_visibility"] = hidden ? "hidden" : "visible";
            if (hidden && countHiddenPrimitive)
                state.XclipHiddenPrimitiveCount++;
        }

        private static Matrix3d ComposeXclipTransform(
            Matrix3d clipToWcs,
            Matrix3d originalInverseBlock,
            Matrix3d currentBlock,
            Matrix3d parent)
        {
            return clipToWcs
                .PreMultiplyBy(originalInverseBlock)
                .PreMultiplyBy(currentBlock)
                .PreMultiplyBy(parent);
        }

        private static string FormatPoint(Point2d point)
        {
            return point.X.ToString("R", CultureInfo.InvariantCulture)
                   + "," + point.Y.ToString("R", CultureInfo.InvariantCulture);
        }

        private static string FormatMatrix(Matrix3d matrix)
        {
            return string.Join(",", matrix.ToArray()
                .Select(value => value.ToString("R", CultureInfo.InvariantCulture)));
        }

        private static string FormatBounds(SemanticBounds bounds)
        {
            return bounds.MinX.ToString("R", CultureInfo.InvariantCulture)
                   + "," + bounds.MinY.ToString("R", CultureInfo.InvariantCulture)
                   + "," + bounds.MaxX.ToString("R", CultureInfo.InvariantCulture)
                   + "," + bounds.MaxY.ToString("R", CultureInfo.InvariantCulture);
        }

        private static CadPrimitive BuildRawPrimitive(
            Entity entity,
            NativeIdentity identity,
            Matrix3d transform,
            List<string> blockPath,
            List<string> xrefPath,
            List<string> xrefHashes,
            string rawLayer,
            string effectiveLayer,
            string stablePath,
            bool isT20,
            Transaction transaction,
            ScanState state)
        {
            string handle = SafeHandle(entity);
            CadPrimitiveKind primitiveKind = ClassifyPrimitive(entity, isT20);
            SemanticGeometry geometry = new SemanticGeometry();
            if (!isT20 && primitiveKind != CadPrimitiveKind.Proxy
                         && primitiveKind != CadPrimitiveKind.NativeObject
                         && primitiveKind != CadPrimitiveKind.BlockReference)
            {
                try
                {
                    geometry = AutoCadSemanticGeometryReader.ReadDirect(entity, transform, transaction, true)
                               ?? new SemanticGeometry();
                }
                catch
                {
                    // 第一层仍保留实体身份。几何读取失败由第二层按候选用途决定是否复核，
                    // 不能因为一个普通标注对象没有几何而丢掉整张图的原始对象账本。
                    geometry = new SemanticGeometry();
                }
            }

            string normalizedLayer = LayerNameNormalizer.Normalize(effectiveLayer, state.Analysis.Profile);
            var source = new SourceReference
            {
                DrawingHash = state.Analysis.DrawingHash,
                Handle = handle,
                StablePath = stablePath,
                RawLayer = rawLayer,
                EffectiveLayer = effectiveLayer,
                NormalizedLayer = normalizedLayer,
                NativeDxfName = identity.DxfName,
                NativeClassName = identity.ClassName,
                BlockPath = new List<string>(blockPath),
                XrefPath = new List<string>(xrefPath),
                XrefHashes = new List<string>(xrefHashes),
                WcsTransform = transform.ToArray().ToList()
            };
            string rawText = primitiveKind == CadPrimitiveKind.Text ? AutoCadTextReader.Read(entity) : string.Empty;
            var rawProperties = new Dictionary<string, string>(StringComparer.Ordinal);
            var evidence = new List<SemanticEvidence>
            {
                new SemanticEvidence
                {
                    Code = "CAD_PRIMITIVE_IDENTITY",
                    Kind = "rxclass",
                    Value = identity.DxfName + "/" + identity.ClassName,
                    SourceHandle = handle,
                    Weight = 1.0
                }
            };
            if (entity is Hatch hatch)
            {
                try
                {
                    string patternName = (hatch.PatternName ?? string.Empty).Trim();
                    if (!string.IsNullOrWhiteSpace(patternName))
                    {
                        rawProperties["hatch_pattern_name"] = patternName;
                        evidence.Add(new SemanticEvidence
                        {
                            Code = "CAD_HATCH_PATTERN_NAME",
                            Kind = "hatch_property",
                            Value = patternName,
                            SourceHandle = handle,
                            Weight = 1.0
                        });
                    }
                }
                catch
                {
                    // 图案名读取失败不丢弃 Hatch 身份和边界；需要该属性的 L3 规则自然不会命中。
                }
            }
            return new CadPrimitive
            {
                PrimitiveId = BuildingSemanticStableId.Create(
                    "primitive",
                    state.Analysis.DrawingHash,
                    stablePath,
                    identity.DxfName,
                    identity.ClassName),
                Kind = primitiveKind,
                IsSemanticCandidate = false,
                Source = source,
                RawText = rawText,
                RawGeometry = geometry,
                ExtractionConfidence = 1.0,
                RawProperties = rawProperties,
                Evidence = evidence
            };
        }

        private static CadPrimitiveKind ClassifyPrimitive(Entity entity, bool isT20)
        {
            if (entity is ProxyEntity) return CadPrimitiveKind.Proxy;
            if (isT20) return CadPrimitiveKind.NativeObject;
            if (entity is DBText || entity is MText) return CadPrimitiveKind.Text;
            if (entity is BlockReference) return CadPrimitiveKind.BlockReference;
            if (entity is Line) return CadPrimitiveKind.Line;
            if (entity is Polyline || entity is Polyline2d || entity is Polyline3d) return CadPrimitiveKind.Polyline;
            if (entity is Arc) return CadPrimitiveKind.Arc;
            if (entity is Circle) return CadPrimitiveKind.Circle;
            if (entity is DBPoint) return CadPrimitiveKind.Point;
            if (entity is Hatch) return CadPrimitiveKind.Hatch;
            if (entity is Autodesk.AutoCAD.DatabaseServices.Region) return CadPrimitiveKind.Region;
            return CadPrimitiveKind.NativeObject;
        }

        private static CadFact BuildFact(
            Entity entity,
            NativeIdentity identity,
            CadFactKind kind,
            Matrix3d transform,
            List<string> blockPath,
            List<string> xrefPath,
            List<string> xrefHashes,
            string rawLayer,
            string effectiveLayer,
            string stablePath,
            bool isNativeT20,
            Transaction transaction,
            ScanState state)
        {
            string handle = SafeHandle(entity);
            Dictionary<string, string> properties = isNativeT20
                ? ReadOnlyComPropertyReader.Read(entity)
                : new Dictionary<string, string>(StringComparer.Ordinal);
            ExplodedGeometryReadResult? t20GeometryRead = null;
            SemanticGeometry geometry;
            if (isNativeT20)
            {
                t20GeometryRead = AutoCadSemanticGeometryReader.ReadExplodedDetailed(
                    entity,
                    transform,
                    transaction,
                    kind == CadFactKind.Wall,
                    kind == CadFactKind.Stair
                    && T20CrossStairGeometryPolicy.IsCrossStair(identity.DxfName, identity.ClassName));
                geometry = t20GeometryRead.Geometry;
            }
            else
            {
                geometry = AutoCadSemanticGeometryReader.ReadDirect(entity, transform, transaction, true);
            }

            string normalizedLayer = LayerNameNormalizer.Normalize(effectiveLayer, state.Analysis.Profile);
            var source = new SourceReference
            {
                DrawingHash = state.Analysis.DrawingHash,
                Handle = handle,
                StablePath = stablePath,
                RawLayer = rawLayer,
                EffectiveLayer = effectiveLayer,
                NormalizedLayer = normalizedLayer,
                NativeDxfName = identity.DxfName,
                NativeClassName = identity.ClassName,
                BlockPath = new List<string>(blockPath),
                XrefPath = new List<string>(xrefPath),
                XrefHashes = new List<string>(xrefHashes),
                WcsTransform = transform.ToArray().ToList()
            };

            string rawLabel = ResolveRawLabel(properties);
            if (kind == CadFactKind.Text)
            {
                string text = AutoCadTextReader.Read(entity);
                if (string.IsNullOrWhiteSpace(text))
                    text = ResolveRawTextLabel(properties);
                if (string.IsNullOrWhiteSpace(text) && isNativeT20)
                    text = AutoCadTextReader.ReadExploded(entity);
                rawLabel = text;
            }

            var evidence = new List<SemanticEvidence>
            {
                new SemanticEvidence
                {
                    Code = isNativeT20 ? "T20_RXCLASS_IDENTITY" : "AUTOCAD_NATIVE_IDENTITY",
                    Kind = "rxclass",
                    Value = identity.DxfName + "/" + identity.ClassName,
                    SourceHandle = handle,
                    Weight = isNativeT20 ? 0.99 : 0.70
                },
                new SemanticEvidence
                {
                    Code = "EFFECTIVE_LAYER",
                    Kind = "layer",
                    Value = rawLayer + "=>" + effectiveLayer + "=>" + normalizedLayer,
                    SourceHandle = handle,
                    Weight = 0.70
                }
            };
            foreach (KeyValuePair<string, string> property in properties.OrderBy(item => item.Key, StringComparer.Ordinal))
            {
                evidence.Add(new SemanticEvidence
                {
                    Code = "T20_COM_PROPERTY_" + property.Key.ToUpperInvariant(),
                    Kind = "idispatch_property",
                    Value = property.Value,
                    SourceHandle = handle,
                    Weight = 0.85
                });
            }
            if (geometry != null && geometry.Kind != GeometryKind.None)
            {
                evidence.Add(new SemanticEvidence
                {
                    Code = isNativeT20 ? "T20_MEMORY_EXPLODE_GEOMETRY" : "AUTOCAD_SOURCE_GEOMETRY",
                    Kind = "geometry",
                    Value = geometry.ExtractionMethod,
                    SourceHandle = handle,
                    Weight = geometry.IsExact ? 0.99 : 0.55
                });
            }
            if (t20GeometryRead != null && t20GeometryRead.OmittedAuxiliaryHatchChildCount > 0)
            {
                evidence.Add(new SemanticEvidence
                {
                    Code = "T20_AUXILIARY_HATCH_OMITTED",
                    Kind = "geometry_policy",
                    Value = t20GeometryRead.OmittedAuxiliaryHatchChildCount.ToString(CultureInfo.InvariantCulture),
                    SourceHandle = handle,
                    Weight = 0.99
                });
            }
            if (t20GeometryRead != null && t20GeometryRead.OmittedAuxiliaryArrowChildCount > 0)
            {
                evidence.Add(new SemanticEvidence
                {
                    Code = "T20_AUXILIARY_STAIR_ARROW_OMITTED",
                    Kind = "geometry_policy",
                    Value = t20GeometryRead.OmittedAuxiliaryArrowChildCount.ToString(CultureInfo.InvariantCulture),
                    SourceHandle = handle,
                    Weight = 0.99
                });
            }

            var fact = new CadFact
            {
                Kind = kind,
                Source = source,
                Geometry = geometry ?? new SemanticGeometry(),
                RawLabel = rawLabel,
                Confidence = isNativeT20 ? 0.99 : StandardCadClassifier.Confidence(kind, entity, effectiveLayer),
                Properties = properties,
                Evidence = evidence
            };
            fact.FactId = BuildingSemanticStableId.Create("fact", state.Analysis.DrawingHash, stablePath, kind.ToString());

            if (isNativeT20
                && kind != CadFactKind.Text
                && !SemanticGeometryAlgorithms.IsUsable(fact.Geometry, true))
            {
                state.NativeGeometryFailures.Add(new NativeGeometryFailureRecord
                {
                    StablePath = stablePath,
                    Handle = handle,
                    DxfName = identity.DxfName,
                    ClassName = identity.ClassName,
                    RuntimeTypeName = identity.RuntimeTypeName,
                    ExtractionMethod = fact.Geometry?.ExtractionMethod ?? string.Empty,
                    TopLevelEntityChildCount = t20GeometryRead?.TopLevelEntityChildCount ?? 0,
                    TopLevelSuccessfulChildCount = t20GeometryRead?.TopLevelSuccessfulChildCount ?? 0,
                    TraceTruncated = t20GeometryRead?.TraceTruncated ?? false,
                    IssueTypeSignature = t20GeometryRead?.IssueTypeSignature ?? "NO_RECORDED_ISSUE",
                    IssueSummary = t20GeometryRead?.IssueSummary ?? "no recorded child issue"
                });
            }

            if (fact.Source.XrefPath.Count != fact.Source.XrefHashes.Count
                || fact.Source.XrefHashes.Any(value => string.Equals(value, "UNAVAILABLE", StringComparison.Ordinal)))
            {
                AddReason(fact.ReasonCodes, BuildingSemanticReasonCodes.XrefHashUnavailable);
            }

            if (!SemanticGeometryAlgorithms.IsUsable(fact.Geometry, false) && kind != CadFactKind.Storey)
            {
                AddReason(fact.ReasonCodes, BuildingSemanticReasonCodes.InvalidGeometry);
                AddDiagnostic(state, isNativeT20 && kind != CadFactKind.Text ? FindingSeverity.Error : FindingSeverity.Review,
                    BuildingSemanticReasonCodes.InvalidGeometry,
                    (isNativeT20 ? "T20" : "普通 CAD") + "事实未取得可用源几何。", stablePath);
            }
            return fact;
        }

        private static string ResolveRawLabel(Dictionary<string, string> properties)
        {
            string[] preferred = { "RoomName", "SpaceName", "Name", "Usage", "Use", "RoomNumber", "Number" };
            foreach (string key in preferred)
            {
                if (properties.TryGetValue(key, out string value) && !string.IsNullOrWhiteSpace(value))
                    return value.Trim();
            }
            return string.Empty;
        }

        private static string ResolveRawTextLabel(Dictionary<string, string> properties)
        {
            string[] textProperties = { "TextString", "Contents", "Text", "Content" };
            foreach (string key in textProperties)
            {
                if (properties.TryGetValue(key, out string value) && !string.IsNullOrWhiteSpace(value))
                    return value.Trim();
            }
            return ResolveRawLabel(properties);
        }

        private static string ResolveBlockName(ObjectId id, Transaction transaction)
        {
            try
            {
                return (transaction.GetObject(id, OpenMode.ForRead) as BlockTableRecord)?.Name ?? string.Empty;
            }
            catch
            {
                return string.Empty;
            }
        }

        private static string BuildStablePath(IEnumerable<string> blockPath, string handle)
        {
            var values = new List<string>(blockPath ?? Enumerable.Empty<string>()) { handle ?? string.Empty };
            return string.Join("/", values);
        }

        private static string ResolveXrefHash(string path, ScanState state)
        {
            if (string.IsNullOrWhiteSpace(path))
                return "UNAVAILABLE";
            try
            {
                string candidate = Environment.ExpandEnvironmentVariables(path);
                if (!Path.IsPathRooted(candidate))
                {
                    string drawingDirectory = Path.GetDirectoryName(state.Analysis.DrawingPath) ?? string.Empty;
                    candidate = Path.Combine(drawingDirectory, candidate);
                }
                candidate = Path.GetFullPath(candidate);
                if (!File.Exists(candidate))
                    return "UNAVAILABLE";
                if (!state.XrefHashCache.TryGetValue(candidate, out string hash))
                {
                    hash = BuildingSemanticStableId.Sha256File(candidate);
                    state.XrefHashCache[candidate] = hash;
                }
                return hash;
            }
            catch
            {
                return "UNAVAILABLE";
            }
        }

        private static string SafeHandle(DBObject value)
        {
            try { return value.Handle.ToString(); }
            catch { return "NO_HANDLE"; }
        }

        private static string SafeLayer(Entity entity)
        {
            try { return entity.Layer ?? string.Empty; }
            catch { return string.Empty; }
        }

        private static bool IsFinite(Matrix3d matrix)
        {
            return matrix.ToArray().All(value => !double.IsNaN(value) && !double.IsInfinity(value));
        }

        private static bool ContainsAny(string value, params string[] terms)
        {
            string normalized = (value ?? string.Empty).ToUpperInvariant();
            return terms.Any(term => normalized.Contains(term.ToUpperInvariant()));
        }

        private static void AddReason(ICollection<string> reasons, string reason)
        {
            if (!reasons.Contains(reason))
                reasons.Add(reason);
        }

        private static void AppendNativeGeometryFailureDiagnostics(ScanState state)
        {
            List<IGrouping<string, NativeGeometryFailureRecord>> classGroups = state.NativeGeometryFailures
                .OrderBy(item => item.StablePath, StringComparer.Ordinal)
                .GroupBy(item => string.Join("|", new[]
                {
                    item.ClassName ?? string.Empty,
                    item.DxfName ?? string.Empty,
                    item.RuntimeTypeName ?? string.Empty
                }), StringComparer.Ordinal)
                .OrderByDescending(group => group.Count())
                .ThenBy(group => group.Key, StringComparer.Ordinal)
                .ToList();

            foreach (IGrouping<string, NativeGeometryFailureRecord> classGroup in classGroups)
            {
                List<NativeGeometryFailureRecord> failures = classGroup
                    .OrderBy(item => item.StablePath, StringComparer.Ordinal)
                    .ToList();
                NativeGeometryFailureRecord first = failures[0];
                string methods = string.Join(",", failures
                    .Select(item => item.ExtractionMethod)
                    .Where(value => !string.IsNullOrWhiteSpace(value))
                    .Distinct(StringComparer.Ordinal)
                    .OrderBy(value => value, StringComparer.Ordinal));
                string handles = string.Join(",", failures
                    .Select(item => item.Handle)
                    .Where(value => !string.IsNullOrWhiteSpace(value))
                    .Distinct(StringComparer.Ordinal)
                    .OrderBy(value => value, StringComparer.Ordinal)
                    .Take(5));
                string issuePatterns = string.Join(" || ", failures
                    .GroupBy(item => item.IssueTypeSignature, StringComparer.Ordinal)
                    .OrderByDescending(group => group.Count())
                    .ThenBy(group => group.Key, StringComparer.Ordinal)
                    .Take(3)
                    .Select(group => group.Count().ToString(CultureInfo.InvariantCulture)
                                     + "x [" + group.First().IssueSummary + "]"));

                state.Snapshot.Diagnostics.Add(new ProviderDiagnostic
                {
                    Severity = FindingSeverity.Error,
                    ReasonCode = BuildingSemanticReasonCodes.T20NativeGeometryUnavailable,
                    StablePath = first.StablePath,
                    Message = "T20 几何失败分类: class=" + SafeDiagnosticValue(first.ClassName)
                              + "; dxf=" + SafeDiagnosticValue(first.DxfName)
                              + "; runtime=" + SafeDiagnosticValue(first.RuntimeTypeName)
                              + "; count=" + failures.Count.ToString(CultureInfo.InvariantCulture)
                              + "; method=" + SafeDiagnosticValue(methods)
                              + "; top_children=" + failures.Min(item => item.TopLevelEntityChildCount).ToString(CultureInfo.InvariantCulture)
                              + ".." + failures.Max(item => item.TopLevelEntityChildCount).ToString(CultureInfo.InvariantCulture)
                              + "; exact_children=" + failures.Min(item => item.TopLevelSuccessfulChildCount).ToString(CultureInfo.InvariantCulture)
                              + ".." + failures.Max(item => item.TopLevelSuccessfulChildCount).ToString(CultureInfo.InvariantCulture)
                              + "; representative_handles=" + SafeDiagnosticValue(handles)
                              + "; issue_patterns=" + SafeDiagnosticValue(issuePatterns)
                });

                foreach (NativeGeometryFailureRecord representative in failures.Take(3))
                {
                    state.Snapshot.Diagnostics.Add(new ProviderDiagnostic
                    {
                        Severity = FindingSeverity.Error,
                        ReasonCode = BuildingSemanticReasonCodes.T20NativeGeometryUnavailable,
                        StablePath = representative.StablePath,
                        Message = "T20 几何失败样本: handle=" + SafeDiagnosticValue(representative.Handle)
                                  + "; class=" + SafeDiagnosticValue(representative.ClassName)
                                  + "; dxf=" + SafeDiagnosticValue(representative.DxfName)
                                  + "; top_children=" + representative.TopLevelEntityChildCount.ToString(CultureInfo.InvariantCulture)
                                  + "; exact_children=" + representative.TopLevelSuccessfulChildCount.ToString(CultureInfo.InvariantCulture)
                                  + "; method=" + SafeDiagnosticValue(representative.ExtractionMethod)
                                  + "; trace=" + SafeDiagnosticValue(representative.IssueSummary)
                    });
                }
            }

            int unrecorded = Math.Max(0, state.NativeT20GeometryFailureCount - state.NativeGeometryFailures.Count);
            if (unrecorded > 0)
            {
                state.Snapshot.Diagnostics.Add(new ProviderDiagnostic
                {
                    Severity = FindingSeverity.Error,
                    ReasonCode = BuildingSemanticReasonCodes.T20NativeGeometryUnavailable,
                    Message = "另有 " + unrecorded.ToString(CultureInfo.InvariantCulture)
                              + " 个 T20 几何失败对象未生成详细追踪记录。"
                });
            }
        }

        private static string SafeDiagnosticValue(string value)
        {
            return (value ?? string.Empty)
                .Replace("\r", " ")
                .Replace("\n", " ")
                .Replace(";", ",");
        }

        private static void AddDiagnostic(ScanState state, FindingSeverity severity, string reason, string message, string stablePath)
        {
            state.Snapshot.Diagnostics.Add(new ProviderDiagnostic
            {
                Severity = severity,
                ReasonCode = reason,
                Message = message,
                StablePath = stablePath ?? string.Empty
            });
            AddReason(state.Snapshot.ReasonCodes, reason);
        }

        private sealed class ScanState
        {
            public ScanState(AnalysisRequest analysis, CadFactSnapshot snapshot)
            {
                Analysis = analysis;
                Snapshot = snapshot;
            }

            public AnalysisRequest Analysis { get; }
            public CadFactSnapshot Snapshot { get; }
            public bool DetectedT20 { get; set; }
            public int UnresolvedSemanticT20Count { get; set; }
            public int NativeT20ObjectCount { get; set; }
            public int NativeSemanticT20Count { get; set; }
            public int NativeT20GeometrySuccessCount { get; set; }
            public int NativeT20GeometryFailureCount { get; set; }
            public int XclipFilterCount { get; set; }
            public int XclipHiddenPrimitiveCount { get; set; }
            public int XclipReadFailureCount { get; set; }
            public bool XclipDiagnosticEnabled { get; } = string.Equals(
                Environment.GetEnvironmentVariable("JZBP_XCLIP_DIAGNOSTIC"),
                "1",
                StringComparison.Ordinal);
            public List<NativeGeometryFailureRecord> NativeGeometryFailures { get; } = new List<NativeGeometryFailureRecord>();
            public List<CadPrimitive> RawPrimitives { get; } = new List<CadPrimitive>();
            public List<CadFact> T20Facts { get; } = new List<CadFact>();
            public List<CadFact> StandardFacts { get; } = new List<CadFact>();
            public Dictionary<string, string> XrefHashCache { get; } = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        }

        private sealed class ClipBoundary
        {
            public string StablePath { get; set; } = string.Empty;
            public SemanticGeometry Geometry { get; set; } = new SemanticGeometry();
            public bool Inverted { get; set; }
        }

        private sealed class NativeGeometryFailureRecord
        {
            public string StablePath { get; set; } = string.Empty;
            public string Handle { get; set; } = string.Empty;
            public string DxfName { get; set; } = string.Empty;
            public string ClassName { get; set; } = string.Empty;
            public string RuntimeTypeName { get; set; } = string.Empty;
            public string ExtractionMethod { get; set; } = string.Empty;
            public int TopLevelEntityChildCount { get; set; }
            public int TopLevelSuccessfulChildCount { get; set; }
            public bool TraceTruncated { get; set; }
            public string IssueTypeSignature { get; set; } = string.Empty;
            public string IssueSummary { get; set; } = string.Empty;
        }
    }

    internal sealed class NativeIdentity
    {
        public string DxfName { get; set; } = string.Empty;
        public string ClassName { get; set; } = string.Empty;
        public string AppName { get; set; } = string.Empty;
        public string RuntimeTypeName { get; set; } = string.Empty;

        public static NativeIdentity Read(Entity entity)
        {
            var identity = new NativeIdentity { RuntimeTypeName = entity.GetType().FullName ?? entity.GetType().Name };
            try
            {
                RXClass rxClass = entity.GetRXClass();
                identity.DxfName = rxClass?.DxfName ?? string.Empty;
                identity.ClassName = rxClass?.Name ?? string.Empty;
                identity.AppName = rxClass?.AppName ?? string.Empty;
            }
            catch
            {
            }

            if (entity is ProxyEntity proxy)
            {
                if (!string.IsNullOrWhiteSpace(proxy.OriginalDxfName))
                    identity.DxfName = proxy.OriginalDxfName;
                if (!string.IsNullOrWhiteSpace(proxy.OriginalClassName))
                    identity.ClassName = proxy.OriginalClassName;
            }
            return identity;
        }

        public string SearchText => (DxfName + "|" + ClassName + "|" + RuntimeTypeName).ToUpperInvariant();
    }

    internal static class T20Classifier
    {
        public static bool IsT20(NativeIdentity identity)
        {
            return T20ObjectPolicy.IsT20(identity?.DxfName ?? string.Empty, identity?.ClassName ?? string.Empty, identity?.RuntimeTypeName ?? string.Empty);
        }

        public static CadFactKind Classify(NativeIdentity identity)
        {
            return T20ObjectPolicy.Classify(identity?.DxfName ?? string.Empty, identity?.ClassName ?? string.Empty, identity?.RuntimeTypeName ?? string.Empty);
        }

        public static bool IsAnnotation(NativeIdentity identity)
        {
            return T20ObjectPolicy.IsAnnotation(identity?.DxfName ?? string.Empty, identity?.ClassName ?? string.Empty, identity?.RuntimeTypeName ?? string.Empty);
        }

        public static bool IsExplicitlyOutOfScope(NativeIdentity identity)
        {
            return T20ObjectPolicy.IsExplicitlyOutOfScope(identity?.DxfName ?? string.Empty, identity?.ClassName ?? string.Empty, identity?.RuntimeTypeName ?? string.Empty);
        }
    }

    internal static class StandardCadClassifier
    {
        public static CadFactKind Classify(Entity entity, NativeIdentity identity, string layer, Transaction transaction)
        {
            if (entity is DBText || entity is MText)
                return CadFactKind.Text;

            string blockName = entity is BlockReference block
                ? ResolveBlockName(block, transaction)
                : string.Empty;
            string material = (layer + "|" + blockName + "|" + identity.SearchText).ToUpperInvariant();
            if (ContainsAny(material, "FIRE-ZONE", "FIRE_ZONE", "防火分区", "人防分区")) return CadFactKind.Zone;
            if (ContainsAny(material, "COLUMN", "COLU", "S-COL", "结构柱", "柱")) return CadFactKind.Column;
            if (ContainsAny(material, "WALL", "A-WALL", "墙")) return CadFactKind.Wall;
            if (ContainsAny(material, "DOOR", "门")) return entity is BlockReference ? CadFactKind.Opening : CadFactKind.Boundary;
            if (ContainsAny(material, "WINDOW", "WIND", "窗")) return entity is BlockReference ? CadFactKind.Opening : CadFactKind.Boundary;
            if (ContainsAny(material, "STAIR", "楼梯")) return CadFactKind.Stair;
            if (ContainsAny(material, "RAMP", "坡道")) return CadFactKind.Ramp;
            if (ContainsAny(material, "SHAFT", "井道", "管井", "风井", "电井")) return CadFactKind.Shaft;
            if (entity is Polyline polyline && polyline.Closed && ContainsAny(material, "SPACE", "ROOM", "房间")) return CadFactKind.Space;
            return CadFactKind.Unknown;
        }

        public static double Confidence(CadFactKind kind, Entity entity, string layer)
        {
            if (kind == CadFactKind.Text)
                return 0.90;
            if (entity is Polyline polyline && polyline.Closed)
                return 0.82;
            if (entity is BlockReference)
                return 0.75;
            return 0.60;
        }

        private static string ResolveBlockName(BlockReference block, Transaction transaction)
        {
            try
            {
                ObjectId id = block.IsDynamicBlock ? block.DynamicBlockTableRecord : block.BlockTableRecord;
                return (transaction.GetObject(id, OpenMode.ForRead) as BlockTableRecord)?.Name ?? string.Empty;
            }
            catch
            {
                return string.Empty;
            }
        }

        private static bool ContainsAny(string value, params string[] terms)
        {
            return terms.Any(term => value.Contains(term.ToUpperInvariant()));
        }
    }

    internal static class ReadOnlyComPropertyReader
    {
        private static readonly string[] AllowedProperties =
        {
            "RoomName", "SpaceName", "Name", "Usage", "Use", "RoomNumber", "Number",
            "TextString", "Contents", "Text", "Content",
            "Area", "Width", "Height", "WallType", "DoorType", "WindowType", "FireRating",
            "IsFireProof", "CivilDefense", "Material", "MaterialName", "WallMaterial", "墙体材料"
        };

        public static Dictionary<string, string> Read(Entity entity)
        {
            var result = new Dictionary<string, string>(StringComparer.Ordinal);
            object dispatch;
            try
            {
                dispatch = entity.AcadObject;
            }
            catch
            {
                return result;
            }
            if (dispatch == null)
                return result;

            Type type = dispatch.GetType();
            foreach (string propertyName in AllowedProperties)
            {
                try
                {
                    object value = type.InvokeMember(
                        propertyName,
                        BindingFlags.GetProperty | BindingFlags.Public | BindingFlags.Instance | BindingFlags.IgnoreCase,
                        null,
                        dispatch,
                        null,
                        CultureInfo.InvariantCulture);
                    if (value == null)
                        continue;
                    string text = Convert.ToString(value, CultureInfo.InvariantCulture) ?? string.Empty;
                    if (!string.IsNullOrWhiteSpace(text))
                        result[propertyName] = text.Trim();
                }
                catch
                {
                    // IDispatch 属性并非所有 T20 类型都实现；只读探测失败不调用任何方法或写属性。
                }
            }
            return result;
        }
    }

    internal static class AutoCadTextReader
    {
        public static string Read(Entity entity)
        {
            if (entity is DBText text)
                return Normalize(text.TextString);
            if (entity is MText mText)
                return Normalize(mText.Contents);
            return string.Empty;
        }

        public static string ReadExploded(Entity entity)
        {
            var fragments = new List<string>();
            CollectExploded(entity, 0, fragments);
            return string.Join(" ", fragments
                .Where(value => !string.IsNullOrWhiteSpace(value))
                .Distinct(StringComparer.Ordinal));
        }

        private static void CollectExploded(Entity entity, int depth, ICollection<string> fragments)
        {
            string direct = Read(entity);
            if (!string.IsNullOrWhiteSpace(direct))
            {
                fragments.Add(direct);
                return;
            }
            if (depth >= 4)
                return;

            var values = new DBObjectCollection();
            try
            {
                entity.Explode(values);
                foreach (DBObject value in values)
                {
                    if (value is Entity child)
                        CollectExploded(child, depth + 1, fragments);
                }
            }
            catch
            {
                // 天正文字若既无只读属性也不能内存分解，保留为空文字并进入 Review。
            }
            finally
            {
                foreach (DBObject value in values)
                {
                    try { value.Dispose(); }
                    catch { }
                }
            }
        }

        private static string Normalize(string value)
        {
            return (value ?? string.Empty)
                .Replace("\\P", " ")
                .Replace("\r", " ")
                .Replace("\n", " ")
                .Replace("{", string.Empty)
                .Replace("}", string.Empty)
                .Trim();
        }
    }
}
