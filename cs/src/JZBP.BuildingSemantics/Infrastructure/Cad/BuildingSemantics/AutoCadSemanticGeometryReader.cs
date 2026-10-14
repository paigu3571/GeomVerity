// SPDX-License-Identifier: MPL-2.0
// Copyright (c) 2026 张田; 著作权人、原作者及维护者：张田；其他贡献者和第三方保留各自权利。
using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using JZBP.BuildingSemantics.Core;

namespace JZBP.BuildingSemantics.Infrastructure.Cad
{
    internal sealed class ExplodedGeometryReadResult
    {
        public SemanticGeometry Geometry { get; set; } = new SemanticGeometry();
        public int TopLevelEntityChildCount { get; set; }
        public int TopLevelSuccessfulChildCount { get; set; }
        public int OmittedAuxiliaryHatchChildCount { get; set; }
        public int OmittedAuxiliaryArrowChildCount { get; set; }
        public bool TraceTruncated { get; set; }
        public List<GeometryReadIssue> Issues { get; set; } = new List<GeometryReadIssue>();

        public string IssueTypeSignature
        {
            get
            {
                string value = string.Join(";", Issues
                    .Select(issue => issue.Signature)
                    .Distinct(StringComparer.Ordinal)
                    .OrderBy(signature => signature, StringComparer.Ordinal));
                return string.IsNullOrWhiteSpace(value) ? "NO_RECORDED_ISSUE" : value;
            }
        }

        public string IssueSummary
        {
            get
            {
                string value = string.Join("; ", Issues
                    .GroupBy(issue => issue.Signature, StringComparer.Ordinal)
                    .OrderByDescending(group => group.Count())
                    .ThenBy(group => group.Key, StringComparer.Ordinal)
                    .Take(8)
                    .Select(group => group.Count().ToString(System.Globalization.CultureInfo.InvariantCulture)
                                     + "x " + group.First().Display));
                if (string.IsNullOrWhiteSpace(value))
                    value = "no recorded child issue";
                if (TraceTruncated)
                    value += "; trace truncated at 64 issues";
                return value;
            }
        }
    }

    internal sealed class GeometryReadIssue
    {
        public int Depth { get; set; }
        public string Reason { get; set; } = string.Empty;
        public string RuntimeType { get; set; } = string.Empty;
        public string DxfName { get; set; } = string.Empty;
        public string RxClassName { get; set; } = string.Empty;
        public string ExtractionMethod { get; set; } = string.Empty;

        public string Signature => Clean(Reason)
                                   + "|d=" + Depth.ToString(System.Globalization.CultureInfo.InvariantCulture)
                                   + "|runtime=" + Clean(RuntimeType)
                                   + "|dxf=" + Clean(DxfName)
                                   + "|rx=" + Clean(RxClassName)
                                   + "|method=" + Clean(ExtractionMethod);

        public string Display => Clean(Reason)
                                 + "@depth" + Depth.ToString(System.Globalization.CultureInfo.InvariantCulture)
                                 + " runtime=" + Clean(RuntimeType)
                                 + " dxf=" + Clean(DxfName)
                                 + " rx=" + Clean(RxClassName)
                                 + " method=" + Clean(ExtractionMethod);

        private static string Clean(string value)
        {
            return (value ?? string.Empty)
                .Replace("|", "/")
                .Replace(";", ",")
                .Replace("\r", " ")
                .Replace("\n", " ");
        }
    }

    internal static class AutoCadSemanticGeometryReader
    {
        public static SemanticGeometry ReadExploded(
            Entity entity,
            Matrix3d transform,
            Transaction transaction)
        {
            return ReadExplodedDetailed(entity, transform, transaction).Geometry;
        }

        public static ExplodedGeometryReadResult ReadExplodedDetailed(
            Entity entity,
            Matrix3d transform,
            Transaction transaction,
            bool allowWallAuxiliaryHatchOmission = false,
            bool allowCrossStairAuxiliaryArrowOmission = false)
        {
            var paths = new List<List<SemanticPoint>>();
            var issues = new List<GeometryReadIssue>();
            bool anyClosed = false;
            bool partialFailure = false;
            int entityChildren = 0;
            int successfulChildren = 0;
            int successfulCurveChildren = 0;
            int auxiliaryHatchChildren = 0;
            int auxiliaryArrowChildren = 0;
            bool auxiliaryHatchOmissionAccepted = false;
            bool auxiliaryArrowOmissionAccepted = false;
            var exploded = new DBObjectCollection();
            try
            {
                entity.Explode(exploded);
                foreach (DBObject value in exploded)
                {
                    try
                    {
                        if (!(value is Entity child))
                            continue;
                        entityChildren++;
                        if (allowWallAuxiliaryHatchOmission && child is Hatch)
                        {
                            auxiliaryHatchChildren++;
                            continue;
                        }
                        if (allowCrossStairAuxiliaryArrowOmission && IsAuxiliaryStairArrow(child))
                        {
                            auxiliaryArrowChildren++;
                            continue;
                        }
                        int issueCountBefore = issues.Count;
                        SemanticGeometry geometry = ReadTemporary(child, transform, transaction, 0, issues);
                        if (!SemanticGeometryAlgorithms.IsUsable(geometry, false) || !geometry.IsExact)
                        {
                            partialFailure = true;
                            if (issues.Count == issueCountBefore)
                                AddIssue(issues, child, 0, "top_child_not_exact", geometry?.ExtractionMethod);
                            continue;
                        }
                        foreach (List<SemanticPoint> path in geometry.Paths)
                            paths.Add(path);
                        anyClosed |= geometry.IsClosed;
                        successfulChildren++;
                        if (child is Curve)
                            successfulCurveChildren++;
                    }
                    catch (System.Exception ex)
                    {
                        partialFailure = true;
                        AddIssue(issues, value as Entity ?? entity, 0,
                            "top_child_exception_" + ex.GetType().Name, string.Empty);
                    }
                }

                if (entityChildren == 0)
                {
                    partialFailure = true;
                    AddIssue(issues, entity, 0, "explode_no_entity_children", "t20_memory_explode");
                }

                auxiliaryHatchOmissionAccepted = T20WallGeometryPolicy.CanOmitAuxiliaryHatch(
                    entityChildren,
                    successfulChildren,
                    successfulCurveChildren,
                    auxiliaryHatchChildren,
                    partialFailure);
                if (auxiliaryHatchChildren > 0 && !auxiliaryHatchOmissionAccepted)
                {
                    partialFailure = true;
                    AddIssue(issues, entity, 0,
                        "wall_auxiliary_hatch_without_complete_exact_boundaries",
                        "t20_memory_explode");
                }
                auxiliaryArrowOmissionAccepted = T20CrossStairGeometryPolicy.CanOmitAuxiliaryArrows(
                    entityChildren,
                    successfulChildren,
                    auxiliaryArrowChildren,
                    partialFailure);
                if (auxiliaryArrowChildren > 0 && !auxiliaryArrowOmissionAccepted)
                {
                    partialFailure = true;
                    AddIssue(issues, entity, 0,
                        "cross_stair_auxiliary_arrow_without_complete_exact_geometry",
                        "t20_memory_explode");
                }
            }
            catch (System.Exception ex)
            {
                partialFailure = true;
                AddIssue(issues, entity, 0, "explode_exception_" + ex.GetType().Name, "t20_memory_explode");
            }
            finally
            {
                foreach (DBObject value in exploded)
                    SafeDispose(value);
            }

            if (paths.Count == 0)
            {
                SemanticGeometry direct = ReadDirect(entity, transform, transaction, false);
                if (SemanticGeometryAlgorithms.IsUsable(direct, true))
                {
                    return CreateReadResult(direct, entityChildren, successfulChildren, issues);
                }
                AddIssue(issues, entity, 0, "direct_source_geometry_unavailable", direct?.ExtractionMethod);
                return CreateReadResult(new SemanticGeometry
                {
                    Kind = GeometryKind.None,
                    IsExact = false,
                    ExtractionMethod = "t20_explode_failed_no_bbox_fallback",
                    Bounds = new SemanticBounds { IsValid = false }
                }, entityChildren, successfulChildren, issues);
            }

            int accountedChildren = successfulChildren
                                    + (auxiliaryHatchOmissionAccepted ? auxiliaryHatchChildren : 0)
                                    + (auxiliaryArrowOmissionAccepted ? auxiliaryArrowChildren : 0);
            bool complete = !partialFailure
                            && entityChildren > 0
                            && accountedChildren == entityChildren;
            string extractionMethod = auxiliaryHatchOmissionAccepted
                ? "t20_memory_explode_exact_wall_boundaries_hatch_omitted"
                : auxiliaryArrowOmissionAccepted
                    ? "t20_memory_explode_exact_cross_stair_arrows_omitted"
                : complete ? "t20_memory_explode" : "t20_memory_explode_partial";
            SemanticGeometry resultGeometry = CreateGeometry(
                paths,
                anyClosed,
                complete,
                extractionMethod);
            if (!complete && issues.Count == 0)
                AddIssue(issues, entity, 0, "explode_incomplete_without_child_detail", resultGeometry.ExtractionMethod);
            return CreateReadResult(
                resultGeometry,
                entityChildren,
                successfulChildren,
                issues,
                auxiliaryHatchOmissionAccepted ? auxiliaryHatchChildren : 0,
                auxiliaryArrowOmissionAccepted ? auxiliaryArrowChildren : 0);
        }

        public static SemanticGeometry ReadDirect(
            Entity entity,
            Matrix3d transform,
            Transaction transaction,
            bool allowBoundsFallback)
        {
            try
            {
                if (entity is Line line)
                {
                    return CreateGeometry(new List<List<SemanticPoint>>
                    {
                        new List<SemanticPoint> { P(line.StartPoint, transform), P(line.EndPoint, transform) }
                    }, false, true, "native_line");
                }

                if (entity is Polyline polyline)
                    return ReadPolyline(polyline, transform);

                if (entity is Arc arc)
                    return ReadArc(arc, transform);

                if (entity is Circle circle)
                    return ReadCircle(circle, transform);

                if (entity is DBPoint point)
                {
                    return CreateGeometry(new List<List<SemanticPoint>>
                    {
                        new List<SemanticPoint> { P(point.Position, transform) }
                    }, false, true, "native_point");
                }

                if (entity is DBText text)
                {
                    return CreateGeometry(new List<List<SemanticPoint>>
                    {
                        new List<SemanticPoint> { P(ResolveTextPoint(text), transform) }
                    }, false, true, "native_text_point");
                }

                if (entity is MText mText)
                {
                    return CreateGeometry(new List<List<SemanticPoint>>
                    {
                        new List<SemanticPoint> { P(mText.Location, transform) }
                    }, false, true, "native_mtext_point");
                }

                if (entity is Curve curve)
                    return ReadCurve(curve, transform);

                if (entity is Hatch hatch)
                {
                    // Hatch.Explode() returns every pattern stroke, not the engineering boundary.
                    // Dense wall/fill patterns can therefore turn one raw entity into thousands of
                    // unrelated two-point paths.  L1/L2 retain the native hatch loops instead.
                    SemanticGeometry boundary = ReadHatchBoundary(hatch, transform);
                    if (SemanticGeometryAlgorithms.IsUsable(boundary, true))
                        return boundary;
                }

                if (entity is Region)
                {
                    SemanticGeometry exploded = ReadTemporary(entity, transform, transaction, 0, new List<GeometryReadIssue>());
                    if (SemanticGeometryAlgorithms.IsUsable(exploded, true))
                        return exploded;
                }
            }
            catch
            {
                // 下方仅对普通 CAD 候选允许包围盒复核；T20 调用方会传 false。
            }

            return allowBoundsFallback
                ? ReadBounds(entity, transform)
                : new SemanticGeometry
                {
                    Kind = GeometryKind.None,
                    IsExact = false,
                    ExtractionMethod = "no_source_geometry",
                    Bounds = new SemanticBounds { IsValid = false }
                };
        }

        private static SemanticGeometry ReadTemporary(
            Entity entity,
            Matrix3d transform,
            Transaction transaction,
            int depth,
            List<GeometryReadIssue> issues)
        {
            if (depth > 4)
            {
                AddIssue(issues, entity, depth, "recursive_depth_limit", "temporary_recursive_explode");
                return new SemanticGeometry
                {
                    Kind = GeometryKind.None,
                    IsExact = false,
                    ExtractionMethod = "recursive_depth_limit",
                    Bounds = new SemanticBounds { IsValid = false }
                };
            }

            if (entity is Line || entity is Polyline || entity is Arc || entity is Circle
                || entity is DBPoint || entity is DBText || entity is MText || entity is Curve || entity is Hatch)
                return ReadDirect(entity, transform, transaction, false);

            var values = new DBObjectCollection();
            var paths = new List<List<SemanticPoint>>();
            bool closed = false;
            bool partialFailure = false;
            int entityChildren = 0;
            int successfulChildren = 0;
            try
            {
                entity.Explode(values);
                foreach (DBObject value in values)
                {
                    try
                    {
                        if (!(value is Entity child))
                            continue;
                        entityChildren++;
                        int issueCountBefore = issues.Count;
                        SemanticGeometry geometry = ReadTemporary(child, transform, transaction, depth + 1, issues);
                        if (!SemanticGeometryAlgorithms.IsUsable(geometry, true))
                        {
                            partialFailure = true;
                            if (issues.Count == issueCountBefore)
                                AddIssue(issues, child, depth + 1, "recursive_child_unusable", geometry?.ExtractionMethod);
                            continue;
                        }
                        paths.AddRange(geometry.Paths);
                        closed |= geometry.IsClosed;
                        successfulChildren++;
                    }
                    catch (System.Exception ex)
                    {
                        partialFailure = true;
                        AddIssue(issues, value as Entity ?? entity, depth + 1,
                            "recursive_child_exception_" + ex.GetType().Name, string.Empty);
                    }
                }

                if (entityChildren == 0)
                {
                    partialFailure = true;
                    AddIssue(issues, entity, depth, "recursive_explode_no_entity_children", "temporary_recursive_explode");
                }
            }
            catch (System.Exception ex)
            {
                partialFailure = true;
                AddIssue(issues, entity, depth,
                    "recursive_explode_exception_" + ex.GetType().Name, "temporary_recursive_explode");
            }
            finally
            {
                foreach (DBObject value in values)
                    SafeDispose(value);
            }

            return paths.Count == 0
                ? new SemanticGeometry
                {
                    Kind = GeometryKind.None,
                    IsExact = false,
                    ExtractionMethod = "temporary_explode_failed",
                    Bounds = new SemanticBounds { IsValid = false }
                }
                : CreateGeometry(
                    paths,
                    closed,
                    !partialFailure && entityChildren > 0 && successfulChildren == entityChildren,
                    !partialFailure && entityChildren > 0 && successfulChildren == entityChildren
                        ? "temporary_recursive_explode"
                        : "temporary_recursive_explode_partial");
        }

        private static ExplodedGeometryReadResult CreateReadResult(
            SemanticGeometry geometry,
            int entityChildren,
            int successfulChildren,
            List<GeometryReadIssue> issues,
            int omittedAuxiliaryHatchChildren = 0,
            int omittedAuxiliaryArrowChildren = 0)
        {
            return new ExplodedGeometryReadResult
            {
                Geometry = geometry ?? new SemanticGeometry(),
                TopLevelEntityChildCount = entityChildren,
                TopLevelSuccessfulChildCount = successfulChildren,
                OmittedAuxiliaryHatchChildCount = omittedAuxiliaryHatchChildren,
                OmittedAuxiliaryArrowChildCount = omittedAuxiliaryArrowChildren,
                TraceTruncated = issues != null && issues.Count >= 64,
                Issues = (issues ?? new List<GeometryReadIssue>()).Take(64).ToList()
            };
        }

        private static bool IsAuxiliaryStairArrow(Entity entity)
        {
            try
            {
                var rxClass = entity?.GetRXClass();
                return T20CrossStairGeometryPolicy.IsAuxiliaryArrow(
                    rxClass?.DxfName ?? string.Empty,
                    rxClass?.Name ?? string.Empty);
            }
            catch
            {
                return false;
            }
        }

        private static void AddIssue(
            List<GeometryReadIssue> issues,
            Entity? entity,
            int depth,
            string reason,
            string? extractionMethod)
        {
            if (issues == null || issues.Count >= 64)
                return;

            string runtimeType = string.Empty;
            string dxfName = string.Empty;
            string rxClassName = string.Empty;
            try { runtimeType = entity?.GetType().FullName ?? entity?.GetType().Name ?? string.Empty; }
            catch { }
            try
            {
                var rxClass = entity?.GetRXClass();
                dxfName = rxClass?.DxfName ?? string.Empty;
                rxClassName = rxClass?.Name ?? string.Empty;
            }
            catch { }

            issues.Add(new GeometryReadIssue
            {
                Depth = depth,
                Reason = reason ?? string.Empty,
                RuntimeType = runtimeType,
                DxfName = dxfName,
                RxClassName = rxClassName,
                ExtractionMethod = extractionMethod ?? string.Empty
            });
        }

        private static SemanticGeometry ReadPolyline(Polyline polyline, Matrix3d transform)
        {
            var points = new List<SemanticPoint>();
            int vertexCount = polyline.NumberOfVertices;
            if (vertexCount == 0)
                return new SemanticGeometry { Kind = GeometryKind.None, Bounds = new SemanticBounds { IsValid = false } };

            int segmentCount = polyline.Closed ? vertexCount : Math.Max(0, vertexCount - 1);
            for (int segment = 0; segment < segmentCount; segment++)
            {
                if (segment == 0)
                    points.Add(P(polyline.GetPoint3dAt(0), transform));
                double bulge = polyline.GetBulgeAt(segment);
                int samples = Math.Abs(bulge) < 1e-10 ? 1 : 12;
                for (int sample = 1; sample <= samples; sample++)
                {
                    double parameter = segment + sample / (double)samples;
                    if (polyline.Closed && parameter >= vertexCount)
                        parameter = vertexCount;
                    points.Add(P(polyline.GetPointAtParameter(parameter), transform));
                }
            }
            if (!polyline.Closed && vertexCount == 1)
                points.Add(P(polyline.GetPoint3dAt(0), transform));

            if (polyline.Closed && points.Count > 1 && Same(points[0], points[points.Count - 1]))
                points.RemoveAt(points.Count - 1);
            return CreateGeometry(new List<List<SemanticPoint>> { points }, polyline.Closed, true, "native_polyline_with_bulge_sampling");
        }

        private static SemanticGeometry ReadArc(Arc arc, Matrix3d transform)
        {
            int count = Math.Max(2, (int)Math.Ceiling(arc.TotalAngle / (Math.PI / 36.0)));
            var points = new List<SemanticPoint>(count + 1);
            for (int index = 0; index <= count; index++)
            {
                double parameter = arc.StartParam + (arc.EndParam - arc.StartParam) * index / count;
                points.Add(P(arc.GetPointAtParameter(parameter), transform));
            }
            return CreateGeometry(new List<List<SemanticPoint>> { points }, false, true, "native_arc_5deg_sampling");
        }

        private static SemanticGeometry ReadCircle(Circle circle, Matrix3d transform)
        {
            const int count = 72;
            var points = new List<SemanticPoint>(count);
            for (int index = 0; index < count; index++)
            {
                double parameter = circle.StartParam + (circle.EndParam - circle.StartParam) * index / count;
                points.Add(P(circle.GetPointAtParameter(parameter), transform));
            }
            return CreateGeometry(new List<List<SemanticPoint>> { points }, true, true, "native_circle_5deg_sampling");
        }

        private static SemanticGeometry ReadHatchBoundary(Hatch hatch, Matrix3d transform)
        {
            var paths = new List<List<SemanticPoint>>();
            using (Plane plane = hatch.GetPlane())
            {
                for (int loopIndex = 0; loopIndex < hatch.NumberOfLoops; loopIndex++)
                {
                    HatchLoop loop = hatch.GetLoopAt(loopIndex);
                    List<SemanticPoint> path = loop.IsPolyline
                        ? ReadHatchPolylineLoop(loop.Polyline, plane, transform)
                        : ReadHatchCurveLoop(loop.Curves, plane, transform);
                    if (path.Count > 1 && Same(path[0], path[path.Count - 1]))
                        path.RemoveAt(path.Count - 1);
                    if (path.Count >= 3)
                        paths.Add(path);
                }
            }

            return CreateGeometry(paths, true, true, "native_hatch_boundary_loops");
        }

        private static List<SemanticPoint> ReadHatchPolylineLoop(
            BulgeVertexCollection vertices,
            Plane plane,
            Matrix3d transform)
        {
            var points = new List<SemanticPoint>();
            if (vertices == null || vertices.Count < 2)
                return points;

            Point2d first = vertices[0].Vertex;
            points.Add(P(plane.EvaluatePoint(first), transform));
            for (int index = 0; index < vertices.Count; index++)
            {
                BulgeVertex current = vertices[index];
                Point2d start = current.Vertex;
                Point2d end = vertices[(index + 1) % vertices.Count].Vertex;
                AppendBulgeSegment(points, start, end, current.Bulge, plane, transform);
            }
            return points;
        }

        private static void AppendBulgeSegment(
            ICollection<SemanticPoint> target,
            Point2d start,
            Point2d end,
            double bulge,
            Plane plane,
            Matrix3d transform)
        {
            double dx = end.X - start.X;
            double dy = end.Y - start.Y;
            double chord = Math.Sqrt(dx * dx + dy * dy);
            if (chord <= 1e-9 || Math.Abs(bulge) < 1e-10 || double.IsNaN(bulge) || double.IsInfinity(bulge))
            {
                AddUnique(target, P(plane.EvaluatePoint(end), transform));
                return;
            }

            double sweep = 4.0 * Math.Atan(bulge);
            double centerOffset = chord * (1.0 - bulge * bulge) / (4.0 * bulge);
            double middleX = (start.X + end.X) * 0.5;
            double middleY = (start.Y + end.Y) * 0.5;
            double centerX = middleX - dy / chord * centerOffset;
            double centerY = middleY + dx / chord * centerOffset;
            double radius = Math.Sqrt(
                (start.X - centerX) * (start.X - centerX)
                + (start.Y - centerY) * (start.Y - centerY));
            double startAngle = Math.Atan2(start.Y - centerY, start.X - centerX);
            int samples = Math.Max(2, Math.Min(72, (int)Math.Ceiling(Math.Abs(sweep) / (Math.PI / 18.0))));
            for (int sample = 1; sample <= samples; sample++)
            {
                double angle = startAngle + sweep * sample / samples;
                var point = new Point2d(
                    centerX + radius * Math.Cos(angle),
                    centerY + radius * Math.Sin(angle));
                AddUnique(target, P(plane.EvaluatePoint(point), transform));
            }
        }

        private static List<SemanticPoint> ReadHatchCurveLoop(
            Curve2dCollection curves,
            Plane plane,
            Matrix3d transform)
        {
            var points = new List<SemanticPoint>();
            if (curves == null)
                return points;
            foreach (Curve2d curve in curves)
            {
                try
                {
                    Point2d[] samples;
                    if (curve is LineSegment2d line)
                        samples = new[] { line.StartPoint, line.EndPoint };
                    else
                        samples = curve.GetSamplePoints(curve is CircularArc2d || curve is EllipticalArc2d ? 19 : 49);
                    foreach (Point2d point in samples)
                        AddUnique(points, P(plane.EvaluatePoint(point), transform));
                }
                finally
                {
                    curve.Dispose();
                }
            }
            return points;
        }

        private static void AddUnique(ICollection<SemanticPoint> target, SemanticPoint point)
        {
            SemanticPoint last = target.LastOrDefault();
            if (last == null || !Same(last, point))
                target.Add(point);
        }

        private static SemanticGeometry ReadCurve(Curve curve, Matrix3d transform)
        {
            double start = curve.StartParam;
            double end = curve.EndParam;
            if (double.IsNaN(start) || double.IsNaN(end) || double.IsInfinity(start) || double.IsInfinity(end) || end <= start)
                return new SemanticGeometry { Kind = GeometryKind.None, Bounds = new SemanticBounds { IsValid = false } };
            const int count = 48;
            var points = new List<SemanticPoint>(count + 1);
            for (int index = 0; index <= count; index++)
            {
                double parameter = start + (end - start) * index / count;
                points.Add(P(curve.GetPointAtParameter(parameter), transform));
            }
            bool closed = Same(points[0], points[points.Count - 1]);
            if (closed)
                points.RemoveAt(points.Count - 1);
            return CreateGeometry(new List<List<SemanticPoint>> { points }, closed, true, "native_curve_parameter_sampling");
        }

        private static SemanticGeometry ReadBounds(Entity entity, Matrix3d transform)
        {
            try
            {
                Extents3d extents = entity.GeometricExtents;
                var points = new List<SemanticPoint>
                {
                    P(new Point3d(extents.MinPoint.X, extents.MinPoint.Y, extents.MinPoint.Z), transform),
                    P(new Point3d(extents.MaxPoint.X, extents.MinPoint.Y, extents.MinPoint.Z), transform),
                    P(new Point3d(extents.MaxPoint.X, extents.MaxPoint.Y, extents.MaxPoint.Z), transform),
                    P(new Point3d(extents.MinPoint.X, extents.MaxPoint.Y, extents.MaxPoint.Z), transform)
                };
                SemanticGeometry geometry = CreateGeometry(new List<List<SemanticPoint>> { points }, true, false, "geometric_extents_review_only");
                geometry.Kind = GeometryKind.Bounds;
                return geometry;
            }
            catch
            {
                return new SemanticGeometry
                {
                    Kind = GeometryKind.None,
                    IsExact = false,
                    ExtractionMethod = "bounds_unavailable",
                    Bounds = new SemanticBounds { IsValid = false }
                };
            }
        }

        private static SemanticGeometry CreateGeometry(
            List<List<SemanticPoint>> paths,
            bool closed,
            bool exact,
            string method)
        {
            paths = (paths ?? new List<List<SemanticPoint>>())
                .Where(path => path != null && path.Count > 0 && path.All(SemanticGeometryAlgorithms.IsFinite))
                .ToList();
            var geometry = new SemanticGeometry
            {
                Kind = paths.Count == 0
                    ? GeometryKind.None
                    : paths.Count > 1 ? GeometryKind.MultiPath
                    : paths[0].Count == 1 ? GeometryKind.Point
                    : closed ? GeometryKind.Polygon : GeometryKind.Polyline,
                IsClosed = closed,
                IsExact = exact,
                ExtractionMethod = method ?? string.Empty,
                Paths = paths
            };
            geometry.Bounds = SemanticGeometryAlgorithms.CalculateBounds(paths);
            return geometry;
        }

        private static Point3d ResolveTextPoint(DBText text)
        {
            return text.HorizontalMode != TextHorizontalMode.TextLeft || text.VerticalMode != TextVerticalMode.TextBase
                ? text.AlignmentPoint
                : text.Position;
        }

        private static SemanticPoint P(Point3d point, Matrix3d transform)
        {
            Point3d wcs = point.TransformBy(transform);
            return new SemanticPoint(wcs.X, wcs.Y, wcs.Z);
        }

        private static bool Same(SemanticPoint first, SemanticPoint second)
        {
            const double tolerance = 1e-6;
            return Math.Abs(first.X - second.X) <= tolerance
                   && Math.Abs(first.Y - second.Y) <= tolerance
                   && Math.Abs(first.Z - second.Z) <= tolerance;
        }

        private static void SafeDispose(DBObject value)
        {
            try { value?.Dispose(); }
            catch { }
        }

    }
}
