// SPDX-License-Identifier: MPL-2.0
// Copyright (c) 2026 张田; 著作权人、原作者及维护者：张田；其他贡献者和第三方保留各自权利。
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;

namespace JZBP.BuildingSemantics.Core
{
    /// <summary>
    /// 从天正墙边线形成可计算闭合面，并用已核实的钢筋混凝土墙 Hatch 边界补充围合。
    /// 这里只做 5mm 节点归并与平面环追踪；
    /// 不读取房名，也不把闭合面直接命名为房间。
    /// </summary>
    internal static class WallLoopGeometryBuilder
    {
        private const double SnapMillimeters = 5.0;
        private const long SpatialCellGridUnits = 200; // 1000mm
        private const double MinimumAreaSquareMillimeters = 10000.0;
        private const double MaximumAreaSquareMillimeters = 500000000.0;

        public static List<GeometryFact> Build(CadPrimitiveSnapshot source)
        {
            List<CadPrimitive> walls = (source.Primitives ?? new List<CadPrimitive>())
                .Where(IsUsableWall)
                .OrderBy(item => item.Source?.StablePath ?? string.Empty, StringComparer.Ordinal)
                .ThenBy(item => item.PrimitiveId, StringComparer.Ordinal)
                .ToList();
            List<CadPrimitive> concreteWallBoundaries = (source.Primitives ?? new List<CadPrimitive>())
                .Where(IsUsableConcreteWallBoundary)
                .OrderBy(item => item.Source?.StablePath ?? string.Empty, StringComparer.Ordinal)
                .ThenBy(item => item.PrimitiveId, StringComparer.Ordinal)
                .ToList();
            Dictionary<GridPoint, HashSet<GridPoint>> wallNeighbors = WallNeighbors(walls);
            HashSet<GridPoint> wallGapEndpoints = wallNeighbors
                .Where(item => item.Value.Count == 1)
                .Select(item => item.Key)
                .ToHashSet();
            var openingBoundaries = new List<CadPrimitive>();
            foreach (CadPrimitive opening in (source.Primitives ?? new List<CadPrimitive>())
                         .Where(IsUsableOpeningBoundary)
                         .OrderBy(item => item.Source?.StablePath ?? string.Empty, StringComparer.Ordinal)
                         .ThenBy(item => item.PrimitiveId, StringComparer.Ordinal))
            {
                CadPrimitive? boundary = SelectOpeningClosurePaths(opening, wallGapEndpoints, wallNeighbors);
                if (boundary != null)
                    openingBoundaries.Add(boundary);
            }
            List<CadPrimitive> allBoundaries = walls.Concat(concreteWallBoundaries).Concat(openingBoundaries).ToList();
            Dictionary<string, CadPrimitive> byId = allBoundaries
                .GroupBy(item => item.PrimitiveId ?? string.Empty, StringComparer.Ordinal)
                .ToDictionary(group => group.Key, group => group.First(), StringComparer.Ordinal);
            var byLoop = new SortedDictionary<string, Face>(StringComparer.Ordinal);
            AppendLoops(byLoop, walls);
            if (concreteWallBoundaries.Count > 0 || openingBoundaries.Count > 0)
                AppendLoops(byLoop, allBoundaries);

            if (byLoop.Count == 0)
                return new List<GeometryFact>();

            var result = new List<GeometryFact>();
            foreach (KeyValuePair<string, Face> item in byLoop)
            {
                List<string> sourceIds = item.Value.SourcePrimitiveIds
                    .Where(byId.ContainsKey)
                    .OrderBy(value => value, StringComparer.Ordinal)
                    .ToList();
                if (sourceIds.Count == 0)
                    continue;
                bool usesConcreteWallBoundary = sourceIds.Any(id =>
                    string.Equals(byId[id].Source?.NativeClassName, "AcDbHatch", StringComparison.OrdinalIgnoreCase));
                bool usesOpeningBoundary = sourceIds.Any(id =>
                    string.Equals(byId[id].Source?.NativeClassName, "TDbOpening", StringComparison.OrdinalIgnoreCase));
                int wallSourceCount = sourceIds.Count(id =>
                    string.Equals(byId[id].Source?.NativeClassName, "TDbWall", StringComparison.OrdinalIgnoreCase)
                    || string.Equals(byId[id].Source?.NativeClassName, "TDbCurtainWall", StringComparison.OrdinalIgnoreCase));
                if (usesOpeningBoundary && wallSourceCount < 1)
                    continue;
                CadPrimitive first = byId[sourceIds[0]];
                string geometryId = BuildingSemanticStableId.Create(
                    "geometry", source.Drawing?.Sha256 ?? string.Empty, "wall_loop_v1", item.Key);
                SemanticGeometry geometry = new SemanticGeometry
                {
                    Kind = GeometryKind.Polygon,
                    IsClosed = true,
                    IsExact = false,
                    ExtractionMethod = "wall_network_polygonize_snap_5mm",
                    Paths = new List<List<SemanticPoint>>
                    {
                        item.Value.Points.Select(point => new SemanticPoint(
                            point.X * SnapMillimeters,
                            point.Y * SnapMillimeters,
                            0)).ToList()
                    }
                };
                geometry.Bounds = SemanticGeometryAlgorithms.CalculateBounds(geometry.Paths);
                SourceReference reference = RecognitionLayerClone.CloneSource(first.Source);
                reference.StablePath = "derived:wall-loop/" + geometryId;
                reference.RawLayer = "__DERIVED__";
                reference.EffectiveLayer = "__DERIVED__";
                reference.NormalizedLayer = "DERIVED-WALL-LOOP";
                reference.NativeDxfName = "DERIVED";
                reference.NativeClassName = "WallBoundedRegion";
                reference.BlockPath.Clear();
                reference.XrefPath.Clear();
                reference.XrefHashes.Clear();
                reference.WcsTransform = IdentityTransform();

                result.Add(new GeometryFact
                {
                    GeometryId = geometryId,
                    SourcePrimitiveIds = sourceIds,
                    FeatureKind = GeometryFeatureKind.ClosedRegion,
                    IsSemanticCandidate = false,
                    Source = reference,
                    Geometry = geometry,
                    Measurements = BuildingGeometryService.Measure(geometry),
                    ExtractionConfidence = 0.90,
                    RawProperties = new Dictionary<string, string>(StringComparer.Ordinal)
                    {
                        ["derived_geometry"] = "wall_bounded_region",
                        ["snap_tolerance_millimeters"] = "5",
                        ["boundary_sources"] = BoundarySources(usesConcreteWallBoundary, usesOpeningBoundary),
                        ["opening_boundary_policy"] = usesOpeningBoundary
                            ? "straight_path_with_wall_gap_or_paired_returns"
                            : string.Empty
                    },
                    Evidence = new List<SemanticEvidence>
                    {
                        new SemanticEvidence
                        {
                            Code = "WALL_NETWORK_BOUNDED_REGION",
                            Kind = "geometry_topology",
                            Value = "sources=" + sourceIds.Count.ToString(CultureInfo.InvariantCulture)
                                    + ";snap=5mm;boundary_sources="
                                    + BoundarySources(usesConcreteWallBoundary, usesOpeningBoundary)
                                    + (usesOpeningBoundary
                                        ? ";opening_policy=straight_path_with_wall_gap_or_paired_returns"
                                        : string.Empty),
                            SourceHandle = reference.Handle,
                            Weight = 0.90
                        }
                    }
                });
            }
            return result;
        }

        private static void AppendLoops(IDictionary<string, Face> byLoop, IEnumerable<CadPrimitive> boundaries)
        {
            List<Segment> segments = BuildSegments(boundaries);
            if (segments.Count < 3)
                return;
            NodeSegments(segments);
            Dictionary<EdgeKey, HashSet<string>> edgeSources = BuildEdges(segments);
            if (edgeSources.Count < 3)
                return;
            foreach (Face face in TraceFaces(edgeSources))
            {
                List<GridPoint> loop = NormalizeLoop(face.Points);
                if (loop.Count < 3 || loop.Distinct().Count() != loop.Count)
                    continue;
                double area = SignedArea(loop) * SnapMillimeters * SnapMillimeters;
                if (area < MinimumAreaSquareMillimeters || area > MaximumAreaSquareMillimeters)
                    continue;
                string key = string.Join(";", loop.Select(item => item.X.ToString(CultureInfo.InvariantCulture)
                                                                  + "," + item.Y.ToString(CultureInfo.InvariantCulture)));
                if (!byLoop.TryGetValue(key, out Face? existing))
                    byLoop[key] = new Face(loop, face.SourcePrimitiveIds);
                else
                    existing.SourcePrimitiveIds.UnionWith(face.SourcePrimitiveIds);
            }
        }

        private static bool IsUsableWall(CadPrimitive primitive)
        {
            string nativeClass = primitive.Source?.NativeClassName ?? string.Empty;
            return primitive.IsSemanticCandidate
                   && string.Equals(primitive.AdapterRoleHint, CadFactKind.Wall.ToString(), StringComparison.OrdinalIgnoreCase)
                   && (string.Equals(nativeClass, "TDbWall", StringComparison.OrdinalIgnoreCase)
                       || string.Equals(nativeClass, "TDbCurtainWall", StringComparison.OrdinalIgnoreCase))
                   && SemanticGeometryAlgorithms.IsUsable(primitive.RawGeometry, true)
                   && !(primitive.RawProperties != null
                        && primitive.RawProperties.TryGetValue("xclip_visibility", out string? visibility)
                        && string.Equals(visibility, "hidden", StringComparison.OrdinalIgnoreCase));
        }

        private static bool IsUsableConcreteWallBoundary(CadPrimitive primitive)
        {
            return string.Equals(primitive.Source?.NativeClassName, "AcDbHatch", StringComparison.OrdinalIgnoreCase)
                   && string.Equals(primitive.Source?.NormalizedLayer, "S-PATT-WALL", StringComparison.OrdinalIgnoreCase)
                   && primitive.RawProperties.TryGetValue("hatch_pattern_name", out string? pattern)
                   && string.Equals(pattern, "钢筋混凝土", StringComparison.OrdinalIgnoreCase)
                   && SemanticGeometryAlgorithms.IsUsable(primitive.RawGeometry, true)
                   && !(primitive.RawProperties.TryGetValue("xclip_visibility", out string? visibility)
                        && string.Equals(visibility, "hidden", StringComparison.OrdinalIgnoreCase));
        }

        private static bool IsUsableOpeningBoundary(CadPrimitive primitive)
        {
            return primitive.IsSemanticCandidate
                   && string.Equals(primitive.AdapterRoleHint, CadFactKind.Opening.ToString(), StringComparison.OrdinalIgnoreCase)
                   && string.Equals(primitive.Source?.NativeClassName, "TDbOpening", StringComparison.OrdinalIgnoreCase)
                   && SemanticGeometryAlgorithms.IsUsable(primitive.RawGeometry, true)
                   && !(primitive.RawProperties != null
                        && primitive.RawProperties.TryGetValue("xclip_visibility", out string? visibility)
                        && string.Equals(visibility, "hidden", StringComparison.OrdinalIgnoreCase));
        }

        private static Dictionary<GridPoint, HashSet<GridPoint>> WallNeighbors(IEnumerable<CadPrimitive> walls)
        {
            var neighbors = new Dictionary<GridPoint, HashSet<GridPoint>>();
            foreach (CadPrimitive wall in walls)
            foreach (List<SemanticPoint> path in wall.RawGeometry.Paths ?? new List<List<SemanticPoint>>())
            {
                for (int index = 1; index < path.Count; index++)
                {
                    GridPoint start = GridPoint.From(path[index - 1]);
                    GridPoint end = GridPoint.From(path[index]);
                    if (start.Equals(end))
                        continue;
                    if (!neighbors.TryGetValue(start, out HashSet<GridPoint>? startNeighbors))
                        neighbors[start] = startNeighbors = new HashSet<GridPoint>();
                    if (!neighbors.TryGetValue(end, out HashSet<GridPoint>? endNeighbors))
                        neighbors[end] = endNeighbors = new HashSet<GridPoint>();
                    startNeighbors.Add(end);
                    endNeighbors.Add(start);
                }
            }
            return neighbors;
        }

        private static CadPrimitive? SelectOpeningClosurePaths(
            CadPrimitive opening,
            ISet<GridPoint> wallGapEndpoints,
            IReadOnlyDictionary<GridPoint, HashSet<GridPoint>> wallNeighbors)
        {
            List<List<SemanticPoint>> sourcePaths = opening.RawGeometry.Paths ?? new List<List<SemanticPoint>>();
            var straightPaths = sourcePaths
                .Select((path, index) => new { Path = path, Index = index })
                .Where(item => IsStraightPath(item.Path))
                .ToList();
            var accepted = new HashSet<int>(straightPaths
                .Where(item => IsStraightWallEndpointSpan(item.Path, wallGapEndpoints))
                .Select(item => item.Index));
            var pairMatches = straightPaths.ToDictionary(item => item.Index, _ => new List<int>());
            for (int left = 0; left < straightPaths.Count; left++)
            for (int right = left + 1; right < straightPaths.Count; right++)
            {
                if (!HasPairedWallReturns(straightPaths[left].Path, straightPaths[right].Path, wallNeighbors))
                    continue;
                pairMatches[straightPaths[left].Index].Add(straightPaths[right].Index);
                pairMatches[straightPaths[right].Index].Add(straightPaths[left].Index);
            }
            foreach (var item in straightPaths)
            {
                if (pairMatches[item.Index].Count != 1)
                    continue;
                int pair = pairMatches[item.Index][0];
                if (pairMatches[pair].Count == 1 && pairMatches[pair][0] == item.Index)
                {
                    accepted.Add(item.Index);
                    accepted.Add(pair);
                }
            }
            List<List<SemanticPoint>> paths = sourcePaths
                .Select((path, index) => new { Path = path, Index = index })
                .Where(item => accepted.Contains(item.Index))
                .Select(item => item.Path.Select(point => new SemanticPoint(point.X, point.Y, point.Z)).ToList())
                .ToList();
            if (paths.Count == 0)
                return null;

            CadPrimitive boundary = RecognitionLayerClone.ClonePrimitive(opening);
            boundary.RawGeometry.Paths = paths;
            boundary.RawGeometry.IsClosed = false;
            boundary.RawGeometry.Bounds = SemanticGeometryAlgorithms.CalculateBounds(paths);
            return boundary;
        }

        private static bool IsStraightWallEndpointSpan(
            IReadOnlyList<SemanticPoint> path,
            ISet<GridPoint> wallGapEndpoints)
        {
            if (!IsStraightPath(path))
                return false;
            GridPoint start = GridPoint.From(path[0]);
            GridPoint end = GridPoint.From(path[path.Count - 1]);
            if (start.Equals(end)
                || !wallGapEndpoints.Contains(start)
                || !wallGapEndpoints.Contains(end))
                return false;

            return true;
        }

        private static bool IsStraightPath(IReadOnlyList<SemanticPoint> path)
        {
            if (path == null || path.Count < 2)
                return false;
            GridPoint start = GridPoint.From(path[0]);
            GridPoint end = GridPoint.From(path[path.Count - 1]);
            if (start.Equals(end))
                return false;
            long dx = end.X - start.X;
            long dy = end.Y - start.Y;
            for (int index = 1; index < path.Count - 1; index++)
            {
                GridPoint point = GridPoint.From(path[index]);
                if (Cross(point.X - start.X, point.Y - start.Y, dx, dy) != 0)
                    return false;
            }
            return true;
        }

        private static bool HasPairedWallReturns(
            IReadOnlyList<SemanticPoint> firstPath,
            IReadOnlyList<SemanticPoint> secondPath,
            IReadOnlyDictionary<GridPoint, HashSet<GridPoint>> wallNeighbors)
        {
            GridPoint firstStart = GridPoint.From(firstPath[0]);
            GridPoint firstEnd = GridPoint.From(firstPath[firstPath.Count - 1]);
            GridPoint secondStart = GridPoint.From(secondPath[0]);
            GridPoint secondEnd = GridPoint.From(secondPath[secondPath.Count - 1]);
            return HasPairedWallReturns(firstStart, firstEnd, secondStart, secondEnd, wallNeighbors)
                   || HasPairedWallReturns(firstStart, firstEnd, secondEnd, secondStart, wallNeighbors);
        }

        private static bool HasPairedWallReturns(
            GridPoint firstStart,
            GridPoint firstEnd,
            GridPoint secondStart,
            GridPoint secondEnd,
            IReadOnlyDictionary<GridPoint, HashSet<GridPoint>> wallNeighbors)
        {
            if (firstEnd.X - firstStart.X != secondEnd.X - secondStart.X
                || firstEnd.Y - firstStart.Y != secondEnd.Y - secondStart.Y
                || Cross(secondStart.X - firstStart.X, secondStart.Y - firstStart.Y,
                    firstEnd.X - firstStart.X, firstEnd.Y - firstStart.Y) == 0)
                return false;
            long spanX = firstEnd.X - firstStart.X;
            long spanY = firstEnd.Y - firstStart.Y;
            return HasWallReturnAndContinuation(firstStart, secondStart, spanX, spanY, true, wallNeighbors)
                   && HasWallReturnAndContinuation(secondStart, firstStart, spanX, spanY, true, wallNeighbors)
                   && HasWallReturnAndContinuation(firstEnd, secondEnd, spanX, spanY, false, wallNeighbors)
                   && HasWallReturnAndContinuation(secondEnd, firstEnd, spanX, spanY, false, wallNeighbors);
        }

        private static bool HasWallReturnAndContinuation(
            GridPoint endpoint,
            GridPoint pairedEndpoint,
            long spanX,
            long spanY,
            bool isStart,
            IReadOnlyDictionary<GridPoint, HashSet<GridPoint>> wallNeighbors)
        {
            return wallNeighbors.TryGetValue(endpoint, out HashSet<GridPoint>? neighbors)
                   && neighbors.Contains(pairedEndpoint)
                   && neighbors.Any(item =>
                   {
                       long dx = item.X - endpoint.X;
                       long dy = item.Y - endpoint.Y;
                       long dot = dx * spanX + dy * spanY;
                       return !item.Equals(pairedEndpoint)
                              && Cross(dx, dy, spanX, spanY) == 0
                              && (isStart ? dot < 0 : dot > 0);
                   });
        }

        private static string BoundarySources(bool usesConcreteWallBoundary, bool usesOpeningBoundary)
        {
            string value = "t20_wall";
            if (usesConcreteWallBoundary)
                value += "+reinforced_concrete_hatch";
            if (usesOpeningBoundary)
                value += "+t20_opening";
            return value;
        }

        private static List<Segment> BuildSegments(IEnumerable<CadPrimitive> walls)
        {
            var result = new List<Segment>();
            foreach (CadPrimitive wall in walls)
            foreach (List<SemanticPoint> path in wall.RawGeometry.Paths ?? new List<List<SemanticPoint>>())
            for (int index = 1; index < path.Count; index++)
            {
                GridPoint start = GridPoint.From(path[index - 1]);
                GridPoint end = GridPoint.From(path[index]);
                if (!start.Equals(end))
                    result.Add(new Segment(start, end, wall.PrimitiveId ?? string.Empty));
            }
            return result;
        }

        private static void NodeSegments(IReadOnlyList<Segment> segments)
        {
            var buckets = new Dictionary<CellKey, List<int>>();
            for (int index = 0; index < segments.Count; index++)
            foreach (CellKey cell in CellsFor(segments[index]))
            {
                if (!buckets.TryGetValue(cell, out List<int>? values))
                    buckets[cell] = values = new List<int>();
                values.Add(index);
            }

            for (int index = 0; index < segments.Count; index++)
            {
                var candidates = new HashSet<int>();
                foreach (CellKey cell in CellsFor(segments[index]))
                foreach (int other in buckets[cell])
                    if (other > index)
                        candidates.Add(other);
                foreach (int other in candidates)
                    AddIntersections(segments[index], segments[other]);
            }
        }

        private static IEnumerable<CellKey> CellsFor(Segment segment)
        {
            long minX = FloorDivide(Math.Min(segment.Start.X, segment.End.X), SpatialCellGridUnits);
            long maxX = FloorDivide(Math.Max(segment.Start.X, segment.End.X), SpatialCellGridUnits);
            long minY = FloorDivide(Math.Min(segment.Start.Y, segment.End.Y), SpatialCellGridUnits);
            long maxY = FloorDivide(Math.Max(segment.Start.Y, segment.End.Y), SpatialCellGridUnits);
            for (long x = minX; x <= maxX; x++)
            for (long y = minY; y <= maxY; y++)
                yield return new CellKey(x, y);
        }

        private static long FloorDivide(long value, long divisor)
        {
            long quotient = value / divisor;
            return value % divisor < 0 ? quotient - 1 : quotient;
        }

        private static void AddIntersections(Segment first, Segment second)
        {
            if (!BoundsOverlap(first, second))
                return;
            double rx = first.End.X - first.Start.X;
            double ry = first.End.Y - first.Start.Y;
            double sx = second.End.X - second.Start.X;
            double sy = second.End.Y - second.Start.Y;
            double qx = second.Start.X - first.Start.X;
            double qy = second.Start.Y - first.Start.Y;
            double denominator = Cross(rx, ry, sx, sy);
            if (denominator != 0)
            {
                double firstParameter = Cross(qx, qy, sx, sy) / denominator;
                double secondParameter = Cross(qx, qy, rx, ry) / denominator;
                if (firstParameter < -1e-9 || firstParameter > 1 + 1e-9
                    || secondParameter < -1e-9 || secondParameter > 1 + 1e-9)
                    return;
                var point = new GridPoint(
                    (long)Math.Round(first.Start.X + firstParameter * rx),
                    (long)Math.Round(first.Start.Y + firstParameter * ry));
                if (Within(point, first, 1) && Within(point, second, 1))
                {
                    first.Splits.Add(point);
                    second.Splits.Add(point);
                }
                return;
            }

            if (Cross(qx, qy, rx, ry) != 0)
                return;
            AddCollinearEndpoint(first.Start, first, second);
            AddCollinearEndpoint(first.End, first, second);
            AddCollinearEndpoint(second.Start, first, second);
            AddCollinearEndpoint(second.End, first, second);
        }

        private static void AddCollinearEndpoint(GridPoint point, Segment first, Segment second)
        {
            if (OnSegment(point, first) && OnSegment(point, second))
            {
                first.Splits.Add(point);
                second.Splits.Add(point);
            }
        }

        private static bool BoundsOverlap(Segment first, Segment second)
        {
            return Math.Min(first.Start.X, first.End.X) <= Math.Max(second.Start.X, second.End.X)
                   && Math.Max(first.Start.X, first.End.X) >= Math.Min(second.Start.X, second.End.X)
                   && Math.Min(first.Start.Y, first.End.Y) <= Math.Max(second.Start.Y, second.End.Y)
                   && Math.Max(first.Start.Y, first.End.Y) >= Math.Min(second.Start.Y, second.End.Y);
        }

        private static bool Within(GridPoint point, Segment segment, long expansion)
        {
            return point.X >= Math.Min(segment.Start.X, segment.End.X) - expansion
                   && point.X <= Math.Max(segment.Start.X, segment.End.X) + expansion
                   && point.Y >= Math.Min(segment.Start.Y, segment.End.Y) - expansion
                   && point.Y <= Math.Max(segment.Start.Y, segment.End.Y) + expansion;
        }

        private static bool OnSegment(GridPoint point, Segment segment)
        {
            return Cross(point.X - segment.Start.X, point.Y - segment.Start.Y,
                       segment.End.X - segment.Start.X, segment.End.Y - segment.Start.Y) == 0
                   && Within(point, segment, 0);
        }

        private static Dictionary<EdgeKey, HashSet<string>> BuildEdges(IEnumerable<Segment> segments)
        {
            var result = new Dictionary<EdgeKey, HashSet<string>>();
            foreach (Segment segment in segments)
            {
                double dx = segment.End.X - segment.Start.X;
                double dy = segment.End.Y - segment.Start.Y;
                List<GridPoint> ordered = segment.Splits
                    .OrderBy(point => (point.X - segment.Start.X) * dx + (point.Y - segment.Start.Y) * dy)
                    .ToList();
                for (int index = 1; index < ordered.Count; index++)
                {
                    if (ordered[index - 1].Equals(ordered[index]))
                        continue;
                    var edge = new EdgeKey(ordered[index - 1], ordered[index]);
                    if (!result.TryGetValue(edge, out HashSet<string>? sources))
                        result[edge] = sources = new HashSet<string>(StringComparer.Ordinal);
                    sources.Add(segment.SourcePrimitiveId);
                }
            }
            return result;
        }

        private static IEnumerable<Face> TraceFaces(Dictionary<EdgeKey, HashSet<string>> edgeSources)
        {
            var adjacency = new Dictionary<GridPoint, HashSet<GridPoint>>();
            foreach (EdgeKey edge in edgeSources.Keys)
            {
                AddNeighbor(adjacency, edge.First, edge.Second);
                AddNeighbor(adjacency, edge.Second, edge.First);
            }
            Dictionary<GridPoint, List<GridPoint>> ordered = adjacency.ToDictionary(
                item => item.Key,
                item => item.Value.OrderBy(point => Math.Atan2(point.Y - item.Key.Y, point.X - item.Key.X)).ToList());
            var visited = new HashSet<DirectedEdge>();
            foreach (EdgeKey edge in edgeSources.Keys.OrderBy(item => item))
            {
                Face? forward = TraceFace(edge.First, edge.Second, ordered, edgeSources, visited);
                if (forward != null && SignedArea(forward.Points) > 0)
                    yield return forward;
                Face? reverse = TraceFace(edge.Second, edge.First, ordered, edgeSources, visited);
                if (reverse != null && SignedArea(reverse.Points) > 0)
                    yield return reverse;
            }
        }

        private static Face? TraceFace(
            GridPoint startFrom,
            GridPoint startTo,
            IReadOnlyDictionary<GridPoint, List<GridPoint>> adjacency,
            IReadOnlyDictionary<EdgeKey, HashSet<string>> edgeSources,
            ISet<DirectedEdge> visited)
        {
            var start = new DirectedEdge(startFrom, startTo);
            if (visited.Contains(start))
                return null;
            var points = new List<GridPoint>();
            var sources = new HashSet<string>(StringComparer.Ordinal);
            DirectedEdge current = start;
            bool closed = false;
            for (int step = 0; step <= edgeSources.Count * 2; step++)
            {
                if (visited.Contains(current))
                {
                    closed = current.Equals(start);
                    break;
                }
                visited.Add(current);
                points.Add(current.From);
                sources.UnionWith(edgeSources[new EdgeKey(current.From, current.To)]);
                List<GridPoint> neighbors = adjacency[current.To];
                int incoming = neighbors.IndexOf(current.From);
                if (incoming < 0 || neighbors.Count == 0)
                    break;
                GridPoint next = neighbors[(incoming - 1 + neighbors.Count) % neighbors.Count];
                current = new DirectedEdge(current.To, next);
                if (current.Equals(start))
                {
                    closed = true;
                    break;
                }
            }
            return closed && points.Count >= 3 ? new Face(points, sources) : null;
        }

        private static void AddNeighbor(IDictionary<GridPoint, HashSet<GridPoint>> adjacency, GridPoint from, GridPoint to)
        {
            if (!adjacency.TryGetValue(from, out HashSet<GridPoint>? values))
                adjacency[from] = values = new HashSet<GridPoint>();
            values.Add(to);
        }

        private static List<GridPoint> NormalizeLoop(IEnumerable<GridPoint> source)
        {
            var points = new List<GridPoint>();
            foreach (GridPoint point in source)
            {
                if (points.Count >= 2 && points[points.Count - 2].Equals(point))
                {
                    points.RemoveAt(points.Count - 1);
                    continue;
                }
                if (points.Count == 0 || !points[points.Count - 1].Equals(point))
                    points.Add(point);
            }
            bool changed = true;
            while (changed && points.Count >= 3)
            {
                changed = false;
                for (int index = 0; index < points.Count; index++)
                {
                    GridPoint previous = points[(index - 1 + points.Count) % points.Count];
                    GridPoint current = points[index];
                    GridPoint next = points[(index + 1) % points.Count];
                    if (Cross(current.X - previous.X, current.Y - previous.Y,
                              next.X - current.X, next.Y - current.Y) != 0)
                        continue;
                    points.RemoveAt(index);
                    changed = true;
                    break;
                }
            }
            if (points.Count < 3)
                return points;
            int first = 0;
            for (int index = 1; index < points.Count; index++)
                if (points[index].CompareTo(points[first]) < 0)
                    first = index;
            return Enumerable.Range(0, points.Count).Select(offset => points[(first + offset) % points.Count]).ToList();
        }

        private static double SignedArea(IReadOnlyList<GridPoint> points)
        {
            double sum = 0;
            for (int index = 0; index < points.Count; index++)
            {
                GridPoint current = points[index];
                GridPoint next = points[(index + 1) % points.Count];
                sum += (double)current.X * next.Y - (double)next.X * current.Y;
            }
            return sum * 0.5;
        }

        private static double Cross(double ax, double ay, double bx, double by)
        {
            return ax * by - ay * bx;
        }

        private static List<double> IdentityTransform()
        {
            return new List<double> { 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1 };
        }

        private sealed class Segment
        {
            public Segment(GridPoint start, GridPoint end, string sourcePrimitiveId)
            {
                Start = start;
                End = end;
                SourcePrimitiveId = sourcePrimitiveId;
                Splits = new HashSet<GridPoint> { start, end };
            }

            public GridPoint Start { get; }
            public GridPoint End { get; }
            public string SourcePrimitiveId { get; }
            public HashSet<GridPoint> Splits { get; }
        }

        private sealed class Face
        {
            public Face(IEnumerable<GridPoint> points, IEnumerable<string> sourcePrimitiveIds)
            {
                Points = points.ToList();
                SourcePrimitiveIds = new HashSet<string>(sourcePrimitiveIds, StringComparer.Ordinal);
            }

            public List<GridPoint> Points { get; }
            public HashSet<string> SourcePrimitiveIds { get; }
        }

        private readonly struct GridPoint : IEquatable<GridPoint>, IComparable<GridPoint>
        {
            public GridPoint(long x, long y) { X = x; Y = y; }
            public long X { get; }
            public long Y { get; }
            public static GridPoint From(SemanticPoint point) => new GridPoint(
                (long)Math.Round(point.X / SnapMillimeters),
                (long)Math.Round(point.Y / SnapMillimeters));
            public int CompareTo(GridPoint other) => X != other.X ? X.CompareTo(other.X) : Y.CompareTo(other.Y);
            public bool Equals(GridPoint other) => X == other.X && Y == other.Y;
            public override bool Equals(object? obj) => obj is GridPoint other && Equals(other);
            public override int GetHashCode() => unchecked(((int)(X ^ (X >> 32)) * 397) ^ (int)(Y ^ (Y >> 32)));
        }

        private readonly struct EdgeKey : IEquatable<EdgeKey>, IComparable<EdgeKey>
        {
            public EdgeKey(GridPoint first, GridPoint second)
            {
                if (first.CompareTo(second) <= 0) { First = first; Second = second; }
                else { First = second; Second = first; }
            }
            public GridPoint First { get; }
            public GridPoint Second { get; }
            public int CompareTo(EdgeKey other)
            {
                int first = First.CompareTo(other.First);
                return first != 0 ? first : Second.CompareTo(other.Second);
            }
            public bool Equals(EdgeKey other) => First.Equals(other.First) && Second.Equals(other.Second);
            public override bool Equals(object? obj) => obj is EdgeKey other && Equals(other);
            public override int GetHashCode() => unchecked((First.GetHashCode() * 397) ^ Second.GetHashCode());
        }

        private readonly struct DirectedEdge : IEquatable<DirectedEdge>
        {
            public DirectedEdge(GridPoint from, GridPoint to) { From = from; To = to; }
            public GridPoint From { get; }
            public GridPoint To { get; }
            public bool Equals(DirectedEdge other) => From.Equals(other.From) && To.Equals(other.To);
            public override bool Equals(object? obj) => obj is DirectedEdge other && Equals(other);
            public override int GetHashCode() => unchecked((From.GetHashCode() * 397) ^ To.GetHashCode());
        }

        private readonly struct CellKey : IEquatable<CellKey>
        {
            public CellKey(long x, long y) { X = x; Y = y; }
            public long X { get; }
            public long Y { get; }
            public bool Equals(CellKey other) => X == other.X && Y == other.Y;
            public override bool Equals(object? obj) => obj is CellKey other && Equals(other);
            public override int GetHashCode() => unchecked(((int)(X ^ (X >> 32)) * 397) ^ (int)(Y ^ (Y >> 32)));
        }
    }
}
