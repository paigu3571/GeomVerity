// SPDX-License-Identifier: MPL-2.0
// Copyright (c) 2026 张田; 著作权人、原作者及维护者：张田；其他贡献者和第三方保留各自权利。
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using JZBP.BuildingSemantics.Core;

internal static class Program
{
    private const string DrawingHash = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
    private const string ProfileHash = "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB";

    private static int Main(string[] args)
    {
        if (args.Length == 3 && args[0] == "--layers-replay")
        {
            try { return RunLayerReplay(args[1], args[2]); }
            catch (Exception ex) { Console.Error.WriteLine("LAYER_REPLAY_FAILED " + ex.Message); return 1; }
        }
        if (args.Length == 3 && args[0] == "--roof-replay")
            return RunRoofReplay(args[1], args[2]);
        if (args.Length == 4 && args[0] == "--shaft-replay")
        {
            try
            {
                return RunShaftReplay(args[1], args[2], args[3]);
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine("SHAFT_REPLAY_37 exception=" + ex.GetType().FullName + " message=" + ex.Message);
                return 1;
            }
        }
        if (args.Length == 2 && args[0] == "--shaft-topology-diagnostic")
            return RunShaftTopologyDiagnostic(args[1]);
        if (args.Length == 1 && args[0] == "--shaft-boundary-tests")
        {
            try
            {
                TestShaftBoundarySourceGrouping();
                TestOpeningSwingPathDoesNotSubdivideShaft();
                TestPairedOpeningSpansRequireBothWallReturns();
                Console.WriteLine("SHAFT_BOUNDARY_TESTS passed=3 failed=0");
                return 0;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine("SHAFT_BOUNDARY_TESTS passed=0 failed=1 message=" + ex.Message);
                return 1;
            }
        }
        if (args.Length == 1 && args[0] == "--profile-discovery-tests")
        {
            TestInstalledProfileFallbackPreservesPriorityAndFailures();
            Console.WriteLine("PROFILE_DISCOVERY_TESTS passed=1 failed=0");
            return 0;
        }
        if (args.Length == 1 && (args[0] == "--primitive-schema-fixture"
                                 || args[0] == "--geometry-schema-fixture"
                                 || args[0] == "--semantic-schema-fixture"))
        {
            // Synthetic, in-memory DTO fixture only; never write it into project drawing artifacts.
            CadFactKind kind = args[0] == "--semantic-schema-fixture" ? CadFactKind.RoofLine : CadFactKind.Column;
            BuildingRecognitionBundle fixture = AnalyzeLayers(CreateFact(kind, "fixture-schema", 0, 0, string.Empty));
            if (args[0] == "--semantic-schema-fixture")
            {
                fixture.SemanticSnapshot.ProducerBinarySha256 = new string('C', 64);
                fixture.SemanticSnapshot.Integrity.SourceHashBefore = DrawingHash;
                fixture.SemanticSnapshot.Integrity.SourceHashAfter = DrawingHash;
                fixture.SemanticSnapshot.Integrity.SourceBytesUnchanged = true;
                fixture.SemanticSnapshot.Integrity.ScanInputMode = ScanInputMode.DiskSideDatabase;
                fixture.SemanticSnapshot.Integrity.InputDatabaseReadOnly = true;
                fixture.SemanticSnapshot.Integrity.DbmodCleanAtStart = false;
                fixture.SemanticSnapshot.Integrity.DbmodUnchanged = true;
                fixture.SemanticSnapshot.DeterministicContentHash = BuildingSemanticDeterminism.Compute(fixture.SemanticSnapshot);
            }
            Console.WriteLine(args[0] == "--primitive-schema-fixture"
                ? BuildingSemanticJson.SerializePrimitiveSnapshot(fixture.PrimitiveSnapshot)
                : args[0] == "--geometry-schema-fixture"
                    ? BuildingSemanticJson.SerializeGeometrySnapshot(fixture.GeometrySnapshot)
                    : BuildingSemanticJson.SerializeSnapshot(fixture.SemanticSnapshot));
            return 0;
        }
        if (args.Length != 0)
            return 2;
        var tests = new (string Name, Action Run)[]
        {
            ("profile requires explicit millimeters", TestProfileRequiresMillimeters),
            ("installed profile fallback preserves existing priority and failures", TestInstalledProfileFallbackPreservesPriorityAndFailures),
            ("unlisted drawings run offline only as Review", TestGenericUnlistedDrawingReview),
            ("unlisted drawings receive isolated runtime project identities", TestGenericRuntimeProjectIsolation),
            ("unfrozen regions cannot carry invented coordinates", TestUnfrozenRegionCannotCarryCoordinates),
            ("semantic ids and content hash are deterministic", TestDeterminism),
            ("T20 interpreter failure is fail closed", TestT20InterpreterFailClosed),
            ("unknown T20 proxies require interpreter by default", TestT20UnknownProxyPolicy),
            ("T20 room labels remain readable helper facts", TestT20TextPolicy),
            ("T20 wall hatch omission requires complete exact boundaries", TestT20WallHatchOmissionPolicy),
            ("T20 cross-stair omission accepts only exact geometry plus symbol arrows", TestT20CrossStairArrowOmissionPolicy),
            ("civil-defense objects cannot be auto-accepted", TestSensitiveObjectReview),
            ("fire and civil-defense openings cannot be auto-accepted", TestSensitiveOpeningReview),
            ("unknown room use stays Review with stable code", TestUnknownRoomUseReview),
            ("door fill relation keeps source traceability", TestDoorFillTraceability),
            ("pending observation regions block positive output", TestPendingObservationRegionGate),
            ("calibration mode excludes holdout objects", TestCalibrationGate),
            ("rotated calibration region rejects bounding-box corner leakage", TestRotatedCalibrationRegionGate),
            ("holdout drawing stays locked until rule freeze", TestHoldoutDrawingGate),
            ("registered production drawing without holdout regions stays Review", TestRegisteredProductionReview),
            ("drawing snapshot breaks mutable aliases", TestDrawingSnapshotImmutability),
            ("content hash covers source chain and bounds", TestDeterminismCoverage),
            ("disk side database allows stable nonzero active DBMOD", TestSideDatabaseAllowsStableNonzeroDbmod),
            ("active document scan still requires clean DBMOD", TestActiveDocumentRequiresCleanDbmod),
            ("unavailable DBMOD quarantines semantic output", TestUnavailableDbmodQuarantinesOutput),
            ("changing DBMOD quarantines semantic output", TestChangingDbmodQuarantinesOutput),
            ("writable side database quarantines semantic output", TestWritableSideDatabaseQuarantinesOutput),
            ("view payload ignores audit ledger but detects rendered semantic drift", TestSemanticPayloadHashForView),
            ("shared immutable snapshot supports concurrent replay", TestConcurrentReplay),
            ("replay stays below five seconds", TestReplayPerformance),
            ("semantic dictionary does not change primitive or geometry hashes", TestLayerIsolationFromSemanticDictionary),
            ("geometry semantic rules validate fail closed", TestGeometrySemanticRuleValidation),
            ("room rule-pack metadata validates fail closed", TestRoomRulePackValidation),
            ("profile rule promotes a closed structural column only at layer three", TestProfileColumnPromotion),
            ("xclip-hidden geometry stays reusable but cannot become semantics", TestXclipHiddenGeometry),
            ("profile rule requires reinforced-concrete hatch evidence for shear walls", TestProfileShearWallPromotion),
            ("masonry classification requires material evidence", TestMasonryMaterialClassification),
            ("profile room rule requires one known name and matching area text", TestProfileRoomPromotion),
            ("wall network closes T-junction rooms before name semantics", TestWallNetworkRoomPromotion),
            ("reinforced-concrete hatch supplements wall-bounded rooms without replacing wall loops", TestConcreteWallBoundarySupplement),
            ("confirmed light well label becomes a dedicated shaft semantic", TestLightWellShaftPromotion),
            ("small named shaft uses an exact opening edge without inventing wall closure", TestSmallShaftOpeningBoundaryPromotion),
            ("named shaft recognition is invariant across size translation and rotation", TestShaftSizeAndTransformInvariance),
            ("named shaft preserves an L-shaped wall loop", TestLShapedShaftPromotion),
            ("single-source and segmented opening boundaries preserve the same shaft", TestShaftBoundarySourceGrouping),
            ("opening swing paths cannot subdivide a shaft boundary", TestOpeningSwingPathDoesNotSubdivideShaft),
            ("paired opening spans require both wall-thickness returns", TestPairedOpeningSpansRequireBothWallReturns),
            ("confirmed room vocabulary stays explicit and excludes electric-looking nonrooms", TestConfirmedRoomUseVocabulary),
            ("ground and basement room rule packs remain traceable and exclude void labels", TestGroundAndBasementRulePacks),
            ("producer version stays aligned across all three layers", TestProducerVersionAlignment),
            ("approved semantic override creates a separate Review view", TestApprovedSemanticOverride),
            ("stale or mismatched semantic override fails closed", TestSemanticOverrideMismatch),
            ("invalid override result preserves raw snapshot and removes Accepted", TestSemanticOverrideFailClosed),
            ("fire water tank becomes a non-room semantic zone", TestFireWaterTankPromotion),
            ("semantic region gate preserves primitive and geometry layers", TestLayerGateIsolation),
            ("geometry layer calculates a thirty square meter region", TestGeometryAreaMeasurement),
            ("noncandidate geometry does not leak into semantics", TestNoncandidateGeometryIsolation),
            ("standard A-Roof polylines become traceable Review roof lines only", TestStandardRoofLinePromotion),
            ("layered facade preserves existing semantic ids", TestLayeredFacadeCompatibility),
            ("primitive snapshot breaks mutable aliases", TestPrimitiveSnapshotImmutability),
            ("nonfinite coordinates cannot become accepted geometry", TestNonfiniteGeometryQuarantine),
            ("missing points cannot become invented origin vertices", TestMissingPointQuarantine),
            ("degenerate closed regions cannot be accepted", TestDegenerateRegionQuarantine),
            ("multi-loop geometry does not claim a net area", TestMultiLoopAreaUnavailable),
            ("invalid noncandidate geometry stays visible for review", TestNoncandidateInvalidGeometry),
            ("layered facade collects CAD exactly once", TestLayeredFacadeCollectsOnce),
            ("layer snapshots roundtrip and reject tampered geometry", TestLayerJsonRoundtrip),
            ("legacy text hashes remain readable", TestLegacyLayerHashCompatibility),
            ("integrity failure quarantines both reusable layers", TestLayerIntegrityQuarantine)
        };

        int failed = 0;
        foreach ((string name, Action run) in tests)
        {
            try
            {
                run();
                Console.WriteLine("PASS " + name);
            }
            catch (Exception ex)
            {
                failed++;
                Console.Error.WriteLine("FAIL " + name + ": " + ex.Message);
            }
        }

        Console.WriteLine("RESULT passed=" + (tests.Length - failed) + " failed=" + failed);
        return failed == 0 ? 0 : 1;
    }

    private static int RunRoofReplay(string geometryPath, string baselineSemanticPath)
    {
        BuildingGeometrySnapshot geometry = BuildingSemanticJson.DeserializeGeometrySnapshot(File.ReadAllText(geometryPath));
        BuildingSemanticSnapshot baseline = BuildingSemanticJson.DeserializeSnapshot(File.ReadAllText(baselineSemanticPath));
        ProjectProfile profile = CreateProfile();
        profile.ProjectId = geometry.Profile.ProjectId;
        profile.AllowUnlistedDrawings = true;
        profile.Drawings.Clear();

        List<CadFact> facts = GeometryFactCompatibility.ToCadFacts(geometry, profile);
        var provider = new FakeProvider(new CadFactSnapshot
        {
            ProviderId = "verification:005-l2-roof-replay",
            IsSuccess = true,
            ReasonCodes = new List<string> { BuildingSemanticReasonCodes.Ok },
            Facts = facts
        });
        var request = new AnalysisRequest
        {
            Profile = profile,
            ProfileHash = geometry.Profile.Sha256,
            RuntimeProjectId = geometry.Profile.ProjectId,
            DrawingHash = geometry.Drawing.Sha256,
            DrawingId = geometry.Drawing.DrawingId,
            DrawingPath = geometry.Drawing.FileName,
            SourceFileLength = geometry.Drawing.FileLength
        };
        BuildingSemanticSnapshot replay = new BuildingSemanticService(provider).Analyze(request);
        List<SemanticObject> roofLines = replay.Objects.Where(item => item.Type == SemanticObjectType.RoofLine).ToList();
        List<SemanticObject> baselineWalls = baseline.Objects.Where(item => item.Type == SemanticObjectType.Wall).OrderBy(WallReplayKey, StringComparer.Ordinal).ToList();
        List<SemanticObject> replayWalls = replay.Objects.Where(item => item.Type == SemanticObjectType.Wall).OrderBy(WallReplayKey, StringComparer.Ordinal).ToList();

        bool wallsUnchanged = baselineWalls.Select(WallReplayKey).SequenceEqual(replayWalls.Select(WallReplayKey), StringComparer.Ordinal);
        bool passed = roofLines.Count == 104
                      && roofLines.Count(item => item.Geometry.IsClosed) == 14
                      && roofLines.Count(item => !item.Geometry.IsClosed) == 90
                      && roofLines.All(item => item.Status == DecisionStatus.Review)
                      && roofLines.All(item => string.Equals(item.Source.NormalizedLayer, "A-Roof", StringComparison.Ordinal))
                      && replay.Objects.All(item => !string.Equals(item.Source.NormalizedLayer, "A-Roof-Drng", StringComparison.Ordinal))
                      && baselineWalls.Count == 63
                      && wallsUnchanged;

        Console.WriteLine(
            "ROOF_REPLAY_005 result=" + (passed ? "PASS" : "FAIL")
            + " roof_lines=" + roofLines.Count
            + " open=" + roofLines.Count(item => !item.Geometry.IsClosed)
            + " closed=" + roofLines.Count(item => item.Geometry.IsClosed)
            + " review=" + roofLines.Count(item => item.Status == DecisionStatus.Review)
            + " baseline_walls=" + baselineWalls.Count
            + " replay_walls=" + replayWalls.Count
            + " wall_identity_geometry_unchanged=" + wallsUnchanged
            + " a_roof_drng_semantics=" + replay.Objects.Count(item => string.Equals(item.Source.NormalizedLayer, "A-Roof-Drng", StringComparison.Ordinal)));
        return passed ? 0 : 1;
    }

    // Offline evaluation entry point only; reuses existing recognition without CAD or new logic.
    private static int RunLayerReplay(string primitivePath, string profilePath)
    {
        CadPrimitiveSnapshot input = BuildingSemanticJson.LoadPrimitiveSnapshot(primitivePath);
        LoadedProjectProfile loaded = BuildingSemanticJson.LoadProfile(profilePath);
        var provider = new FakeProvider(new CadFactSnapshot
        {
            ProviderId = "offline:l1-snapshot-replay",
            IsSuccess = true,
            Primitives = input.Primitives,
            ProxyLedger = input.ProxyLedger,
            Diagnostics = input.ProviderDiagnostics
        });
        DrawingProfileRule? drawingRule = ProjectProfileValidator.FindDrawing(loaded.Profile, input.Drawing.Sha256);
        var request = new AnalysisRequest
        {
            Profile = loaded.Profile,
            ProfileHash = loaded.Sha256,
            RuntimeProjectId = ProjectProfileValidator.ResolveRuntimeProjectId(loaded.Profile, drawingRule, input.Drawing.Sha256),
            DrawingHash = input.Drawing.Sha256,
            DrawingId = input.Drawing.DrawingId,
            DrawingPath = input.Drawing.FileName,
            SourceFileLength = input.Drawing.FileLength
        };
        BuildingRecognitionBundle output = new BuildingSemanticService(provider).AnalyzeLayers(request);
        RecognitionLayerProvenance.Apply(output, BuildingSemanticStableId.Sha256File(typeof(Program).Assembly.Location));
        output.SemanticSnapshot.DeterministicContentHash = BuildingSemanticDeterminism.Compute(output.SemanticSnapshot);
        Console.WriteLine("LAYER_REPLAY geometry_facts=" + output.GeometrySnapshot.Facts.Count
            + " objects=" + output.SemanticSnapshot.Objects.Count
            + " spaces=" + output.SemanticSnapshot.Objects.Count(o => o.Type == SemanticObjectType.Space)
            + " status=" + output.SemanticSnapshot.Status
            + " l2_hash=" + output.GeometrySnapshot.DeterministicContentHash
            + " l3_hash=" + output.SemanticSnapshot.DeterministicContentHash);
        return output.SemanticSnapshot.Status == AnalysisRunStatus.Failed ? 1 : 0;
    }

    private static int RunShaftReplay(string primitivePath, string profilePath, string baselineSemanticPath)
    {
        CadPrimitiveSnapshot primitives = BuildingSemanticJson.LoadPrimitiveSnapshot(primitivePath);
        LoadedProjectProfile loaded = BuildingSemanticJson.LoadProfile(profilePath);
        BuildingSemanticSnapshot baseline = BuildingSemanticJson.DeserializeSnapshot(File.ReadAllText(baselineSemanticPath));
        var provider = new FakeProvider(new CadFactSnapshot
        {
            ProviderId = "verification:37-shaft-replay",
            IsSuccess = true,
            ReasonCodes = new List<string> { BuildingSemanticReasonCodes.Ok },
            Primitives = primitives.Primitives,
            ProxyLedger = primitives.ProxyLedger,
            Diagnostics = primitives.ProviderDiagnostics
        });
        var request = new AnalysisRequest
        {
            Profile = loaded.Profile,
            ProfileHash = loaded.Sha256,
            RuntimeProjectId = loaded.Profile.ProjectId,
            DrawingHash = primitives.Drawing.Sha256,
            DrawingId = primitives.Drawing.DrawingId,
            DrawingPath = primitives.Drawing.FileName,
            SourceFileLength = primitives.Drawing.FileLength
        };
        BuildingRecognitionBundle replayBundle = new BuildingSemanticService(provider).AnalyzeLayers(request);
        BuildingSemanticSnapshot replay = replayBundle.SemanticSnapshot;
        List<SemanticObject> shafts = replay.Objects
            .Where(item => item.Type == SemanticObjectType.Shaft && item.UseCode == "ELECTRICAL_SHAFT")
            .ToList();
        List<SemanticObject> targetShafts = shafts.Where(item => item.Evidence.Any(evidence =>
            evidence.Code == "ROOM_LABEL_CONTAINED_TEXT" && evidence.SourceHandle == "707D")).ToList();
        SemanticObject? shaft = targetShafts
            .OrderBy(item => (item.Geometry.Bounds.MaxX - item.Geometry.Bounds.MinX)
                             * (item.Geometry.Bounds.MaxY - item.Geometry.Bounds.MinY))
            .ThenBy(item => item.SemanticId, StringComparer.Ordinal)
            .FirstOrDefault();
        double shaftArea = shaft == null ? 0 : PolygonArea(shaft.Geometry);
        bool baselineIdentity = baseline.ProducerVersion == "0.2.8"
                                && baseline.DeterministicContentHash == "098F3C7D39DB4CA5FCBDA541F422D951EB3773D5E61EFBE6179A440116FB795D";
        bool passed = baselineIdentity
                      && baseline.Objects.Count == 16
                      && baseline.Objects.All(item => item.Type != SemanticObjectType.Shaft)
                      && shafts.Count == 1
                      && targetShafts.Count == 1
                      && shaft != null
                      && shaft.Status == DecisionStatus.Review
                      && Math.Abs(shaft.Geometry.Bounds.MinX - 16100) < 1
                      && Math.Abs(shaft.Geometry.Bounds.MinY - 9095) < 1
                      && Math.Abs(shaft.Geometry.Bounds.MaxX - 18100) < 1
                      && Math.Abs(shaft.Geometry.Bounds.MaxY - 9695) < 1
                      && Math.Abs(shaftArea - 1200000) < 1
                      && replay.Objects.Count == 17
                      && replay.Objects.Count(item => item.Type == SemanticObjectType.Opening) == 3
                      && replay.Objects.Count(item => item.Type == SemanticObjectType.Window) == 3
                      && shaft.Evidence.Any(item => item.Code == "SHAFT_LABEL_SMALL_WALL_LOOP")
                      && shaft.Evidence.Any(item => item.Code == "WALL_NETWORK_BOUNDED_REGION"
                                                   && item.Value.Contains("t20_opening"))
                      && shaft.Evidence.Any(item => item.Code == "ROOM_LABEL_CONTAINED_TEXT"
                                                   && item.SourceHandle == "707D")
                      && replay.Objects.Count(item => item.Type == SemanticObjectType.Wall) == 10
                      && replay.Objects.Count(item => item.Source.Handle == "1468" && item.Type == SemanticObjectType.Window) == 1
                      && replay.Objects.Count(item => item.Source.Handle == "1468" && item.Type == SemanticObjectType.Opening) == 1;
        Console.WriteLine(
            "SHAFT_REPLAY_37 result=" + (passed ? "PASS" : "FAIL")
            + " baseline_objects=" + baseline.Objects.Count
            + " baseline_shafts=" + baseline.Objects.Count(item => item.Type == SemanticObjectType.Shaft)
            + " replay_objects=" + replay.Objects.Count
            + " replay_shafts=" + shafts.Count
            + " target_shafts=" + targetShafts.Count
            + " geometry_facts=" + replayBundle.GeometrySnapshot.Facts.Count
            + " wall_loops=" + replayBundle.GeometrySnapshot.Facts.Count(item =>
                item.RawProperties.TryGetValue("derived_geometry", out string value) && value == "wall_bounded_region")
            + " replay_walls=" + replay.Objects.Count(item => item.Type == SemanticObjectType.Wall)
            + " handle_1468_windows=" + replay.Objects.Count(item => item.Source.Handle == "1468" && item.Type == SemanticObjectType.Window)
            + " handle_1468_openings=" + replay.Objects.Count(item => item.Source.Handle == "1468" && item.Type == SemanticObjectType.Opening)
            + " shaft_status=" + (shaft?.Status.ToString() ?? "missing")
            + " shaft_area=" + shaftArea.ToString("R"));
        foreach (SemanticObject target in targetShafts.OrderBy(item => item.SemanticId, StringComparer.Ordinal))
            Console.WriteLine("SHAFT_REPLAY_37 target=" + target.SemanticId
                              + " bounds=" + target.Geometry.Bounds.MinX + "," + target.Geometry.Bounds.MinY
                              + "," + target.Geometry.Bounds.MaxX + "," + target.Geometry.Bounds.MaxY
                              + " source=" + target.Source.StablePath);
        return passed ? 0 : 1;
    }

    private static int RunShaftTopologyDiagnostic(string primitivePath)
    {
        CadPrimitiveSnapshot snapshot = BuildingSemanticJson.LoadPrimitiveSnapshot(primitivePath);
        List<CadPrimitive> walls = snapshot.Primitives.Where(item =>
            item.IsSemanticCandidate
            && string.Equals(item.AdapterRoleHint, CadFactKind.Wall.ToString(), StringComparison.OrdinalIgnoreCase)
            && (string.Equals(item.Source?.NativeClassName, "TDbWall", StringComparison.OrdinalIgnoreCase)
                || string.Equals(item.Source?.NativeClassName, "TDbCurtainWall", StringComparison.OrdinalIgnoreCase))
            && SemanticGeometryAlgorithms.IsUsable(item.RawGeometry, true)
            && !(item.RawProperties.TryGetValue("xclip_visibility", out string visibility)
                 && string.Equals(visibility, "hidden", StringComparison.OrdinalIgnoreCase))).ToList();
        var segments = new List<(CadPrimitive Wall, int PathIndex, int SegmentIndex, SemanticPoint Start, SemanticPoint End,
            (long X, long Y) GridStart, (long X, long Y) GridEnd)>();
        var neighbors = new Dictionary<(long X, long Y), HashSet<(long X, long Y)>>();
        foreach (CadPrimitive wall in walls)
        for (int pathIndex = 0; pathIndex < wall.RawGeometry.Paths.Count; pathIndex++)
        {
            List<SemanticPoint> path = wall.RawGeometry.Paths[pathIndex];
            for (int segmentIndex = 1; segmentIndex < path.Count; segmentIndex++)
            {
                SemanticPoint start = path[segmentIndex - 1];
                SemanticPoint end = path[segmentIndex];
                (long X, long Y) gridStart = DiagnosticGridPoint(start);
                (long X, long Y) gridEnd = DiagnosticGridPoint(end);
                if (gridStart == gridEnd)
                    continue;
                segments.Add((wall, pathIndex, segmentIndex - 1, start, end, gridStart, gridEnd));
                if (!neighbors.TryGetValue(gridStart, out HashSet<(long X, long Y)> startNeighbors))
                    neighbors[gridStart] = startNeighbors = new HashSet<(long X, long Y)>();
                if (!neighbors.TryGetValue(gridEnd, out HashSet<(long X, long Y)> endNeighbors))
                    neighbors[gridEnd] = endNeighbors = new HashSet<(long X, long Y)>();
                startNeighbors.Add(gridEnd);
                endNeighbors.Add(gridStart);
            }
        }

        CadPrimitive opening = snapshot.Primitives.Single(item => item.Source?.Handle == "1468");
        Console.WriteLine("SHAFT_TOPOLOGY opening_handle=1468 stable_path=" + opening.Source.StablePath
                          + " wall_count=" + walls.Count + " wall_segments=" + segments.Count
                          + " opening_paths=" + opening.RawGeometry.Paths.Count);
        int horizontalCount = 0;
        for (int pathIndex = 0; pathIndex < opening.RawGeometry.Paths.Count; pathIndex++)
        {
            List<SemanticPoint> path = opening.RawGeometry.Paths[pathIndex];
            if (path.Count < 2)
                continue;
            SemanticPoint start = path[0];
            SemanticPoint end = path[path.Count - 1];
            Console.WriteLine("SHAFT_TOPOLOGY opening_path=" + pathIndex + " points=" + path.Count
                              + " start=" + DiagnosticPoint(start) + " end=" + DiagnosticPoint(end));
            if (Math.Abs(start.Y - end.Y) > 0.001 || Math.Abs(start.X - end.X) < 0.001)
                continue;
            horizontalCount++;
            WriteEndpoint("path" + pathIndex + ":start", start, segments, neighbors);
            WriteEndpoint("path" + pathIndex + ":end", end, segments, neighbors);
        }
        return horizontalCount == 2 ? 0 : 1;
    }

    private static void WriteEndpoint(
        string label,
        SemanticPoint point,
        IEnumerable<(CadPrimitive Wall, int PathIndex, int SegmentIndex, SemanticPoint Start, SemanticPoint End,
            (long X, long Y) GridStart, (long X, long Y) GridEnd)> segments,
        IReadOnlyDictionary<(long X, long Y), HashSet<(long X, long Y)>> neighbors)
    {
        (long X, long Y) grid = DiagnosticGridPoint(point);
        HashSet<(long X, long Y)> adjacent = neighbors.TryGetValue(grid, out HashSet<(long X, long Y)> found)
            ? found
            : new HashSet<(long X, long Y)>();
        Console.WriteLine("SHAFT_TOPOLOGY endpoint=" + label + " raw=" + DiagnosticPoint(point)
                          + " snapped=" + (grid.X * 5.0).ToString("R") + "," + (grid.Y * 5.0).ToString("R")
                          + " unique_neighbors=" + adjacent.Count + " qualifies_gap=" + (adjacent.Count == 1));
        foreach (var segment in segments.Where(item => item.GridStart == grid || item.GridEnd == grid)
                     .OrderBy(item => item.Wall.Source.StablePath, StringComparer.Ordinal)
                     .ThenBy(item => item.PathIndex).ThenBy(item => item.SegmentIndex))
        {
            (long X, long Y) neighbor = segment.GridStart == grid ? segment.GridEnd : segment.GridStart;
            Console.WriteLine("SHAFT_TOPOLOGY incident handle=" + segment.Wall.Source.Handle
                              + " stable_path=" + segment.Wall.Source.StablePath
                              + " path=" + segment.PathIndex + " segment=" + segment.SegmentIndex
                              + " raw=" + DiagnosticPoint(segment.Start) + "->" + DiagnosticPoint(segment.End)
                              + " neighbor=" + (neighbor.X * 5.0).ToString("R") + "," + (neighbor.Y * 5.0).ToString("R"));
        }
        foreach (var segment in segments.Where(item => item.GridStart != grid && item.GridEnd != grid
                                                        && DiagnosticPointOnSegment(grid, item.GridStart, item.GridEnd))
                     .OrderBy(item => item.Wall.Source.StablePath, StringComparer.Ordinal)
                     .ThenBy(item => item.PathIndex).ThenBy(item => item.SegmentIndex))
            Console.WriteLine("SHAFT_TOPOLOGY crosses_without_endpoint handle=" + segment.Wall.Source.Handle
                              + " stable_path=" + segment.Wall.Source.StablePath
                              + " path=" + segment.PathIndex + " segment=" + segment.SegmentIndex
                              + " raw=" + DiagnosticPoint(segment.Start) + "->" + DiagnosticPoint(segment.End));
    }

    private static (long X, long Y) DiagnosticGridPoint(SemanticPoint point)
    {
        return ((long)Math.Round(point.X / 5.0, MidpointRounding.AwayFromZero),
            (long)Math.Round(point.Y / 5.0, MidpointRounding.AwayFromZero));
    }

    private static bool DiagnosticPointOnSegment(
        (long X, long Y) point,
        (long X, long Y) start,
        (long X, long Y) end)
    {
        long cross = (point.X - start.X) * (end.Y - start.Y) - (point.Y - start.Y) * (end.X - start.X);
        return cross == 0
               && point.X >= Math.Min(start.X, end.X) && point.X <= Math.Max(start.X, end.X)
               && point.Y >= Math.Min(start.Y, end.Y) && point.Y <= Math.Max(start.Y, end.Y);
    }

    private static string DiagnosticPoint(SemanticPoint point)
    {
        return point.X.ToString("R") + "," + point.Y.ToString("R");
    }

    private static string WallReplayKey(SemanticObject item)
    {
        IEnumerable<string> points = (item.Geometry?.Paths ?? new List<List<SemanticPoint>>())
            .SelectMany(path => path)
            .Select(point => point.X.ToString("R") + "," + point.Y.ToString("R") + "," + point.Z.ToString("R"));
        return string.Join("|", new[]
        {
            item.SemanticId,
            item.Source?.Handle ?? string.Empty,
            item.Source?.StablePath ?? string.Empty,
            item.Geometry?.Kind.ToString() ?? string.Empty,
            (item.Geometry?.IsClosed ?? false).ToString(),
            string.Join(";", points)
        });
    }

    private static void TestProfileRequiresMillimeters()
    {
        ProjectProfile profile = CreateProfile();
        profile.Units = string.Empty;
        ProfileValidationResult result = ProjectProfileValidator.Validate(profile);
        Assert(!result.IsValid, "missing units must fail");
        Assert(result.ReasonCodes.Contains(BuildingSemanticReasonCodes.UnitProfileRequired), "missing reason code");
    }

    private static void TestInstalledProfileFallbackPreservesPriorityAndFailures()
    {
        string root = Path.Combine(Path.GetTempPath(), "jzbp-profile-discovery-" + Guid.NewGuid().ToString("N"));
        string installedProfiles = Path.Combine(root, "profiles");
        string assemblyDirectory = Path.Combine(root, "deploy", "AutoCAD2016", "current");
        string existingProfiles = Path.Combine(root, "external", "profiles");
        string ambiguousProfiles = Path.Combine(root, "ambiguous", "profiles");
        Directory.CreateDirectory(installedProfiles);
        Directory.CreateDirectory(assemblyDirectory);
        Directory.CreateDirectory(existingProfiles);
        Directory.CreateDirectory(ambiguousProfiles);
        string assemblyPath = Path.Combine(assemblyDirectory, "JZBP.BuildingSemantics.dll");
        File.WriteAllText(assemblyPath, string.Empty);

        try
        {
            string? repositoryProfiles = ProjectProfileDiscovery.FindInstalledProfilesRoot(
                typeof(Program).Assembly.Location);
            Assert(!string.IsNullOrWhiteSpace(repositoryProfiles),
                "test assembly could not locate the repository profiles template");
            string deepAssembly = Path.Combine(root, "任意安装目录", "a", "b", "c", "d", "e", "f", "g", "net48", "JZBP.BuildingSemantics.dll");
            Assert(string.Equals(ProjectProfileDiscovery.FindInstalledProfilesRoot(deepAssembly), installedProfiles, StringComparison.OrdinalIgnoreCase),
                "deep installation paths still depend on a fixed ancestor count");
            string templateJson = File.ReadAllText(
                Path.Combine(repositoryProfiles!, "generic.project-profile.v1.json"));
            string repositoryRoot = Directory.GetParent(repositoryProfiles!)!.FullName;
            string deployedAssembly = Path.Combine(
                repositoryRoot, "deploy", "AutoCAD2016", "current", "JZBP.BuildingSemantics.dll");
            Assert(string.Equals(
                    ProjectProfileDiscovery.FindInstalledProfilesRoot(deployedAssembly),
                    repositoryProfiles,
                    StringComparison.OrdinalIgnoreCase),
                "the actual deploy/AutoCAD2016/current installation path did not resolve repository profiles");

            void WriteProfile(string path, string projectId, bool allowUnlisted)
            {
                string json = templateJson
                    .Replace("\"project_id\": \"generic\"", "\"project_id\": \"" + projectId + "\"")
                    .Replace("\"allow_unlisted_drawings\": true",
                        "\"allow_unlisted_drawings\": " + allowUnlisted.ToString().ToLowerInvariant());
                File.WriteAllText(path, json);
            }

            const string externalHash = "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC";
            string installedPath = Path.Combine(installedProfiles, "installed.json");
            WriteProfile(installedPath, "installed-generic", true);
            string? resolvedInstalledRoot = ProjectProfileDiscovery.FindInstalledProfilesRoot(assemblyPath);
            Assert(string.Equals(resolvedInstalledRoot, installedProfiles, StringComparison.OrdinalIgnoreCase),
                "assembly-relative profiles root was not resolved from the actual installation hierarchy");

            LoadedProjectProfile? fallback = ProjectProfileDiscovery.ResolveExistingThenInstalled(
                new[] { Path.Combine(root, "external-drawing", "profiles") },
                resolvedInstalledRoot,
                externalHash);
            Assert(fallback?.Profile.ProjectId == "installed-generic",
                "external drawing without a local profile did not use the installation-relative generic template");

            WriteProfile(Path.Combine(existingProfiles, "configured.json"), "configured-first", true);
            LoadedProjectProfile? configured = ProjectProfileDiscovery.ResolveExistingThenInstalled(
                new[] { existingProfiles },
                resolvedInstalledRoot,
                externalHash);
            Assert(configured?.Profile.ProjectId == "configured-first",
                "installation fallback overrode an existing configured match");

            WriteProfile(Path.Combine(ambiguousProfiles, "first.json"), "ambiguous-first", true);
            WriteProfile(Path.Combine(ambiguousProfiles, "second.json"), "ambiguous-second", true);
            AssertThrows<InvalidDataException>(() => ProjectProfileDiscovery.ResolveExistingThenInstalled(
                    new[] { ambiguousProfiles }, resolvedInstalledRoot, externalHash),
                "ambiguous existing profiles were silently bypassed by installation fallback");

            string explicitInvalid = Path.Combine(root, "explicit-invalid.json");
            WriteProfile(explicitInvalid, "explicit-invalid", false);
            AssertThrows<InvalidDataException>(
                () => ProjectProfileDiscovery.RequireMatchingProfile(explicitInvalid, externalHash),
                "an explicitly selected nonmatching profile did not fail closed");
        }
        finally
        {
            Directory.Delete(root, true);
        }
    }

    private static void TestGenericUnlistedDrawingReview()
    {
        const string unlistedHash = "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC";
        ProjectProfile profile = CreateProfile();
        Assert(ProjectProfileValidator.FindDrawing(profile, unlistedHash) == null,
            "strict profile unexpectedly admitted an unlisted drawing");

        profile.AllowUnlistedDrawings = true;
        DrawingProfileRule? genericRule = ProjectProfileValidator.FindDrawing(profile, unlistedHash);
        Assert(ProjectProfileValidator.IsGenericReviewDrawing(genericRule),
            "generic profile did not create a conservative unlisted-drawing rule");
        Assert(!ProjectProfileValidator.IsGenericReviewDrawing(
                ProjectProfileValidator.FindDrawing(profile, DrawingHash)),
            "exact golden drawing lost precedence over generic mode");

        CadFact wall = CreateFact(CadFactKind.Wall, "generic-wall", 0, 0, string.Empty);
        wall.Source.DrawingHash = unlistedHash;
        var provider = new FakeProvider(new CadFactSnapshot
        {
            ProviderId = "fixture:generic-unlisted",
            IsSuccess = true,
            ReasonCodes = new List<string> { BuildingSemanticReasonCodes.Ok },
            Facts = new List<CadFact> { wall }
        });
        AnalysisRequest request = CreateRequest(profile);
        request.DrawingHash = unlistedHash;
        request.DrawingId = genericRule!.DrawingId;
        BuildingSemanticSnapshot snapshot = new BuildingSemanticService(provider).AnalyzeLayers(request).SemanticSnapshot;
        SemanticObject result = snapshot.Objects.Single();
        Assert(snapshot.Status == AnalysisRunStatus.Review && result.Status == DecisionStatus.Review,
            "unlisted drawing produced an accepted semantic result");
        Assert(result.Evidence.Any(item => item.Code == "GENERIC_UNLISTED_DRAWING_REVIEW"),
            "generic review mode lacks explicit evidence");
    }

    private static void TestGenericRuntimeProjectIsolation()
    {
        const string firstHash = "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC";
        string secondHash = new string('D', 64);
        ProjectProfile profile = CreateProfile();
        profile.AllowUnlistedDrawings = true;

        DrawingProfileRule? firstRule = ProjectProfileValidator.FindDrawing(profile, firstHash);
        DrawingProfileRule? secondRule = ProjectProfileValidator.FindDrawing(profile, secondHash);
        string firstProjectId = ProjectProfileValidator.ResolveRuntimeProjectId(profile, firstRule, firstHash);
        string secondProjectId = ProjectProfileValidator.ResolveRuntimeProjectId(profile, secondRule, secondHash);
        Assert(firstProjectId == "auto-" + firstHash.Substring(0, 12).ToLowerInvariant(),
            "first automatic project id was not deterministic");
        Assert(secondProjectId == "auto-" + secondHash.Substring(0, 12).ToLowerInvariant(),
            "second automatic project id was not deterministic");
        Assert(firstProjectId != secondProjectId, "different unlisted drawings shared one project identity");

        profile.OutputRoot = Path.Combine(Path.GetTempPath(), "jzbp-project-scope-contract", "fixture-project");
        string firstOutput = BuildingSemanticProjectScope.ResolveOutputDirectory(
            profile,
            Path.Combine(Path.GetTempPath(), "first.dwg"),
            firstRule?.DrawingId ?? string.Empty,
            firstProjectId);
        string secondOutput = BuildingSemanticProjectScope.ResolveOutputDirectory(
            profile,
            Path.Combine(Path.GetTempPath(), "second.dwg"),
            secondRule?.DrawingId ?? string.Empty,
            secondProjectId);
        Assert(!string.Equals(firstOutput, secondOutput, StringComparison.OrdinalIgnoreCase),
            "different unlisted drawings shared one artifact directory");
        Assert(string.Equals(
                Directory.GetParent(firstOutput)?.FullName,
                Path.Combine(Directory.GetParent(profile.OutputRoot)?.FullName ?? string.Empty, firstProjectId),
                StringComparison.OrdinalIgnoreCase),
            "automatic artifact directory did not leave the configured project root");

        DrawingProfileRule? exactRule = ProjectProfileValidator.FindDrawing(profile, DrawingHash);
        Assert(ProjectProfileValidator.ResolveRuntimeProjectId(profile, exactRule, DrawingHash) == profile.ProjectId,
            "registered drawing lost its configured project identity");
        string exactOutput = BuildingSemanticProjectScope.ResolveOutputDirectory(
            profile,
            Path.Combine(Path.GetTempPath(), "fixture.dwg"),
            exactRule?.DrawingId ?? string.Empty,
            profile.ProjectId);
        Assert(string.Equals(
                exactOutput,
                Path.Combine(Path.GetFullPath(profile.OutputRoot), "fixture"),
                StringComparison.OrdinalIgnoreCase),
            "registered drawing left its configured project output root");

        CadFact fact = CreateFact(CadFactKind.Wall, "auto-project-wall", 0, 0, "Ordinary");
        fact.Source.DrawingHash = firstHash;
        var provider = new FakeProvider(new CadFactSnapshot
        {
            ProviderId = "fixture:auto-project-scope",
            IsSuccess = true,
            ReasonCodes = new List<string> { BuildingSemanticReasonCodes.Ok },
            Facts = new List<CadFact> { fact }
        });
        AnalysisRequest request = CreateRequest(profile);
        request.DrawingHash = firstHash;
        request.DrawingId = firstRule?.DrawingId ?? string.Empty;
        request.RuntimeProjectId = firstProjectId;
        BuildingRecognitionBundle bundle = new BuildingSemanticService(provider).AnalyzeLayers(request);
        Assert(bundle.PrimitiveSnapshot.Profile.ProjectId == firstProjectId,
            "primitive snapshot ignored runtime project identity");
        Assert(bundle.GeometrySnapshot.Profile.ProjectId == firstProjectId,
            "geometry snapshot ignored runtime project identity");
        Assert(bundle.SemanticSnapshot.Profile.ProjectId == firstProjectId,
            "semantic snapshot ignored runtime project identity");
    }

    private static void TestUnfrozenRegionCannotCarryCoordinates()
    {
        ProjectProfile profile = CreateProfile();
        profile.ObservationRegions.Add(new ObservationRegion
        {
            Code = "B1",
            Role = ObservationRegionRole.Calibration,
            State = ObservationRegionState.AwaitingHumanCoordinates,
            DrawingHash = DrawingHash,
            PolygonWcsMillimeters = new List<SemanticPoint>
            {
                new SemanticPoint(0, 0), new SemanticPoint(100, 0), new SemanticPoint(100, 100)
            }
        });
        Assert(!ProjectProfileValidator.Validate(profile).IsValid, "implementer-invented coordinates must fail");
    }

    private static void TestDeterminism()
    {
        ProjectProfile profile = CreateProfile();
        CadFact first = CreateFact(CadFactKind.Wall, "10", 0, 0, "Ordinary");
        CadFact second = CreateFact(CadFactKind.Column, "20", 2000, 0, string.Empty);
        BuildingSemanticSnapshot a = Analyze(profile, new[] { first, second });
        BuildingSemanticSnapshot b = Analyze(profile, new[] { second, first });
        Assert(a.DeterministicContentHash == b.DeterministicContentHash, "content hash changed with fact order");
        Assert(a.Objects.Select(item => item.SemanticId).SequenceEqual(b.Objects.Select(item => item.SemanticId)), "semantic IDs/order changed");
    }

    private static void TestT20InterpreterFailClosed()
    {
        ProjectProfile profile = CreateProfile();
        CadFact partial = CreateFact(CadFactKind.Wall, "10", 0, 0, "Ordinary");
        var provider = new FakeProvider(new CadFactSnapshot
        {
            ProviderId = "fixture:t20-proxy",
            IsSuccess = false,
            DetectedT20 = true,
            T20InterpreterAvailable = false,
            ReasonCodes = new List<string> { BuildingSemanticReasonCodes.T20InterpreterRequired },
            Facts = new List<CadFact> { partial }
        });
        BuildingSemanticSnapshot snapshot = new BuildingSemanticService(provider).Analyze(CreateRequest(profile));
        Assert(snapshot.Status == AnalysisRunStatus.Failed, "missing interpreter must fail");
        Assert(snapshot.Objects.Count == 0, "partial facts leaked into semantic output");
        Assert(snapshot.ReasonCodes.Contains(BuildingSemanticReasonCodes.T20InterpreterRequired), "reason code missing");
    }

    private static void TestT20UnknownProxyPolicy()
    {
        Assert(T20ObjectPolicy.Classify("TCH_CURTAIN_WALL", "TDbCurtainWall") == CadFactKind.Wall,
            "curtain wall was not mapped to Wall");
        Assert(T20ObjectPolicy.Classify("TCH_CROSSSTAIR", "TDbCrossStair") == CadFactKind.Stair,
            "cross stair was not mapped to Stair");
        Assert(T20ObjectPolicy.ProxyRequiresInterpreter("TCH_FUTURE_BUILDING", "TDbFutureBuilding"),
            "unknown non-annotation T20 proxy bypassed interpreter requirement");
        Assert(!T20ObjectPolicy.ProxyRequiresInterpreter("TCH_PIPE", "TDbPipe"),
            "audited out-of-scope pipe should not block the architecture adapter");
        Assert(!T20ObjectPolicy.ProxyRequiresInterpreter("TCH_DIMENSION2", "TDbDimension2"),
            "audited annotation should not block the architecture adapter");
    }

    private static void TestT20TextPolicy()
    {
        Assert(T20ObjectPolicy.Classify("TCH_TEXT", "TDbText") == CadFactKind.Text,
            "TDbText was not classified as a readable text fact");
        Assert(T20ObjectPolicy.Classify("TCH_MTEXT", "TDbMText") == CadFactKind.Text,
            "TDbMText was not classified as a readable text fact");
        Assert(T20ObjectPolicy.IsAnnotation("TCH_TEXT", "TDbText"),
            "TDbText should remain an annotation object at the primitive ledger level");
        Assert(!T20ObjectPolicy.ProxyRequiresInterpreter("TCH_TEXT", "TDbText"),
            "a text annotation proxy must not fail the whole drawing when its interpreter is absent");
    }

    private static void TestT20WallHatchOmissionPolicy()
    {
        Assert(T20WallGeometryPolicy.CanOmitAuxiliaryHatch(3, 2, 2, 1, false),
            "two exact wall curves plus one auxiliary hatch should be accepted");
        Assert(!T20WallGeometryPolicy.CanOmitAuxiliaryHatch(2, 1, 1, 1, false),
            "one exact curve is not a complete wall boundary set");
        Assert(!T20WallGeometryPolicy.CanOmitAuxiliaryHatch(4, 2, 2, 1, false),
            "an unaccounted non-hatch child must fail closed");
        Assert(!T20WallGeometryPolicy.CanOmitAuxiliaryHatch(3, 2, 2, 1, true),
            "another child failure must not be hidden by the hatch rule");
        Assert(!T20WallGeometryPolicy.CanOmitAuxiliaryHatch(2, 2, 2, 0, false),
            "the policy only applies when an auxiliary hatch is present");
    }

    private static void TestT20CrossStairArrowOmissionPolicy()
    {
        Assert(T20CrossStairGeometryPolicy.IsCrossStair("TCH_CROSSSTAIR", "TDbCrossStair"),
            "exact cross-stair identity was rejected");
        Assert(!T20CrossStairGeometryPolicy.IsCrossStair("TCH_STAIR", "TDbCrossStair"),
            "non-cross-stair identity was admitted");
        Assert(T20CrossStairGeometryPolicy.IsAuxiliaryArrow("TCH_ARROW", "TDbSymbArrow"),
            "exact T20 symbol arrow identity was rejected");
        Assert(!T20CrossStairGeometryPolicy.IsAuxiliaryArrow("TCH_ARROW", "OtherArrow"),
            "unknown arrow class was admitted");
        Assert(T20CrossStairGeometryPolicy.CanOmitAuxiliaryArrows(8, 6, 2, false),
            "observed six-exact plus two-arrow cross-stair shape was rejected");
        Assert(!T20CrossStairGeometryPolicy.CanOmitAuxiliaryArrows(8, 5, 2, false),
            "unaccounted cross-stair child was silently omitted");
        Assert(!T20CrossStairGeometryPolicy.CanOmitAuxiliaryArrows(8, 6, 2, true),
            "cross-stair with another geometry failure was admitted");
    }

    private static void TestSensitiveObjectReview()
    {
        ProjectProfile profile = CreateProfile();
        CadFact fact = CreateFact(CadFactKind.Wall, "30", 0, 0, WallClassification.CivilDefense.ToString());
        fact.Source.RawLayer = "A-Wall-人防";
        fact.Source.EffectiveLayer = "A-Wall-人防";
        fact.Source.NormalizedLayer = "A-Wall-人防";
        BuildingSemanticSnapshot snapshot = Analyze(profile, new[] { fact });
        SemanticObject wall = snapshot.Objects.Single();
        Assert(wall.Status == DecisionStatus.Review, "civil-defense wall was auto-accepted");
    }

    private static void TestSensitiveOpeningReview()
    {
        ProjectProfile profile = CreateProfile();
        CadFact fireDoor = CreateFact(CadFactKind.Door, "31", 0, 0, string.Empty);
        fireDoor.Properties["FireRating"] = "60";
        BuildingSemanticSnapshot fireSnapshot = Analyze(profile, new[] { fireDoor });
        Assert(fireSnapshot.Objects.All(item => item.Status == DecisionStatus.Review), "fire door was auto-accepted");

        CadFact civilDoor = CreateFact(CadFactKind.Door, "32", 1000, 0, string.Empty);
        civilDoor.Properties["CivilDefense"] = "true";
        BuildingSemanticSnapshot civilSnapshot = Analyze(profile, new[] { civilDoor });
        Assert(civilSnapshot.Objects.All(item => item.Status == DecisionStatus.Review), "civil-defense door was auto-accepted");

        CadFact fireWindow = CreateFact(CadFactKind.Window, "33", 2000, 0, string.Empty);
        fireWindow.Properties["IsFireProof"] = "true";
        BuildingSemanticSnapshot windowSnapshot = Analyze(profile, new[] { fireWindow });
        Assert(windowSnapshot.Objects.All(item => item.Status == DecisionStatus.Review), "fire window was auto-accepted");
    }

    private static void TestDoorFillTraceability()
    {
        ProjectProfile profile = CreateProfile();
        CadFact fact = CreateFact(CadFactKind.Opening, "40", 0, 0, string.Empty);
        fact.Properties["opening_kind"] = "door";
        BuildingSemanticSnapshot snapshot = Analyze(profile, new[] { fact });
        Assert(snapshot.Objects.Count == 2, "opening and door pair not emitted");
        Assert(snapshot.Relations.Count(item => item.Type == SemanticRelationType.FillsOpening) == 1, "FILLS_OPENING relation missing");
        Assert(snapshot.Objects.All(item => item.Source.DrawingHash == DrawingHash && item.Source.Handle == "40"), "source traceability missing");
        Assert(snapshot.Objects.All(item => item.Evidence.Count > 0), "evidence missing");
    }

    private static void TestUnknownRoomUseReview()
    {
        ProjectProfile profile = CreateProfile();
        CadFact fact = CreateFact(CadFactKind.Space, "35", 0, 0, string.Empty);
        fact.RawLabel = "未收录用途房间";
        BuildingSemanticSnapshot snapshot = Analyze(profile, new[] { fact });
        SemanticObject space = snapshot.Objects.Single();
        Assert(space.Status == DecisionStatus.Review, "unknown room use was auto-accepted");
        Assert(space.UseCode == "UNKNOWN", "unknown room use did not receive a stable code");
    }

    private static void TestPendingObservationRegionGate()
    {
        ProjectProfile profile = CreateProfile();
        profile.RuleState = SemanticRuleState.Calibration;
        profile.ObservationRegions.Add(new ObservationRegion
        {
            Code = "B1",
            Role = ObservationRegionRole.Calibration,
            State = ObservationRegionState.AwaitingHumanCoordinates,
            DrawingHash = DrawingHash
        });
        BuildingSemanticSnapshot snapshot = Analyze(profile, new[] { CreateFact(CadFactKind.Wall, "50", 0, 0, "Ordinary") });
        Assert(snapshot.Status == AnalysisRunStatus.Failed, "pending human coordinates did not fail closed");
        Assert(snapshot.Objects.Count == 0, "positive objects leaked before coordinate freeze");
        Assert(snapshot.ReasonCodes.Contains(BuildingSemanticReasonCodes.ObservationRegionNotFrozen), "region gate reason missing");
    }

    private static void TestCalibrationGate()
    {
        ProjectProfile profile = CreateProfile();
        profile.RuleState = SemanticRuleState.Calibration;
        profile.Drawings[0].Role = "primary_calibration";
        profile.ObservationRegions.Add(FrozenRegion("B1", ObservationRegionRole.Calibration, 0, 0, 1000, 1000));
        profile.ObservationRegions.Add(FrozenRegion("B4", ObservationRegionRole.Holdout, 2000, 0, 3000, 1000));
        CadFact calibration = CreateFact(CadFactKind.Wall, "51", 100, 100, "Ordinary");
        CadFact holdout = CreateFact(CadFactKind.Wall, "52", 2200, 100, "Ordinary");
        BuildingSemanticSnapshot snapshot = Analyze(profile, new[] { calibration, holdout });
        Assert(snapshot.Status == AnalysisRunStatus.Review, "calibration run must stay Review");
        Assert(snapshot.Objects.Count == 1 && snapshot.Objects[0].Source.Handle == "51", "holdout object leaked into calibration output");
        Assert(snapshot.Objects[0].Status == DecisionStatus.Review, "calibration object was auto-accepted before rule freeze");
        Assert(snapshot.ReasonCodes.Contains(BuildingSemanticReasonCodes.RulesNotFrozen), "rule gate reason missing");
    }

    private static void TestRotatedCalibrationRegionGate()
    {
        ProjectProfile profile = CreateProfile();
        profile.RuleState = SemanticRuleState.Calibration;
        profile.Drawings[0].Role = "primary_calibration";
        profile.ObservationRegions.Add(new ObservationRegion
        {
            Code = "B1",
            Name = "rotated fixture",
            Role = ObservationRegionRole.Calibration,
            State = ObservationRegionState.Frozen,
            DrawingHash = DrawingHash,
            PolygonWcsMillimeters = new List<SemanticPoint>
            {
                new SemanticPoint(1000, 0),
                new SemanticPoint(2000, 1000),
                new SemanticPoint(1000, 2000),
                new SemanticPoint(0, 1000)
            },
            FrozenBy = "fixture-user",
            FrozenAtUtc = "2026-01-01T00:00:00Z"
        });

        CadFact outsideDiamond = CreateFact(CadFactKind.Wall, "outside-diamond", 100, 100, "Ordinary");
        ResizeRectangle(outsideDiamond, 100, 100);
        CadFact insideDiamond = CreateFact(CadFactKind.Wall, "inside-diamond", 950, 950, "Ordinary");
        ResizeRectangle(insideDiamond, 100, 100);
        BuildingSemanticSnapshot snapshot = Analyze(profile, new[] { outsideDiamond, insideDiamond });
        Assert(snapshot.Objects.Count == 1 && snapshot.Objects[0].Source.Handle == "inside-diamond",
            "axis-aligned bounds leaked an object outside the rotated human region");
    }

    private static void TestHoldoutDrawingGate()
    {
        ProjectProfile profile = CreateProfile();
        profile.RuleState = SemanticRuleState.Calibration;
        profile.Drawings[0].Role = "compatibility_holdout";
        profile.ObservationRegions.Add(FrozenRegion("G1", ObservationRegionRole.Holdout, 0, 0, 1000, 1000));
        BuildingSemanticSnapshot snapshot = Analyze(profile, new[] { CreateFact(CadFactKind.Wall, "53", 100, 100, "Ordinary") });
        Assert(snapshot.Status == AnalysisRunStatus.Failed, "holdout drawing opened before rule freeze");
        Assert(snapshot.Objects.Count == 0, "holdout object leaked before rule freeze");
        Assert(snapshot.ReasonCodes.Contains(BuildingSemanticReasonCodes.HoldoutEvaluationLocked), "holdout lock reason missing");
    }

    private static void TestRegisteredProductionReview()
    {
        ProjectProfile profile = CreateProfile();
        profile.RuleState = SemanticRuleState.Calibration;
        profile.Drawings[0].Role = "production_review";
        BuildingSemanticSnapshot snapshot = Analyze(profile,
            new[] { CreateFact(CadFactKind.Wall, "registered-review", 100, 100, "Ordinary") });

        Assert(snapshot.Status == AnalysisRunStatus.Review,
            "registered production drawing was not kept in Review before rule freeze");
        Assert(snapshot.Objects.Count == 1 && snapshot.Objects[0].Status == DecisionStatus.Review,
            "registered production object was blocked or auto-accepted");
        Assert(snapshot.ReasonCodes.Contains(BuildingSemanticReasonCodes.RulesNotFrozen),
            "registered production Review reason missing");
        Assert(snapshot.Objects[0].Evidence.Any(item => item.Code == "REGISTERED_DRAWING_REVIEW"),
            "registered production Review evidence missing");
    }

    private static void TestDrawingSnapshotImmutability()
    {
        ProjectProfile profile = CreateProfile();
        CadFact original = CreateFact(CadFactKind.Wall, "54", 0, 0, "Ordinary");
        var mutableBuilder = new CadFactSnapshot
        {
            ProviderId = "fixture:immutable",
            IsSuccess = true,
            Facts = new List<CadFact> { original }
        };
        DrawingSnapshot frozen = DrawingSnapshot.Freeze(mutableBuilder);
        CadFact exposedCopy = frozen.Facts.Single();
        exposedCopy.Source.RawLayer = "MUTATED_EXPOSED_COPY";
        var service = new BuildingSemanticService(new FrozenProvider(frozen));
        BuildingSemanticSnapshot output = service.Analyze(CreateRequest(profile));
        string originalHash = output.DeterministicContentHash;

        original.Source.RawLayer = "MUTATED_ORIGINAL";
        original.Geometry.Paths[0][0].X = 999999;
        Assert(output.Objects.Single().Source.RawLayer == "A-Test", "provider alias mutated returned semantic snapshot");
        Assert(output.Objects.Single().Geometry.Paths[0][0].X == 0, "provider geometry alias mutated returned semantic snapshot");
        Assert(BuildingSemanticDeterminism.Compute(output) == originalHash, "immutable input alias changed content hash");
    }

    private static void TestDeterminismCoverage()
    {
        BuildingSemanticSnapshot snapshot = Analyze(CreateProfile(), new[] { CreateFact(CadFactKind.Wall, "55", 0, 0, "Ordinary") });
        string baseline = snapshot.DeterministicContentHash;
        snapshot.Objects[0].Source.XrefPath.Add("xref-a");
        snapshot.Objects[0].Source.XrefHashes.Add(DrawingHash);
        snapshot.Objects[0].Source.WcsTransform.Add(42.0);
        snapshot.Objects[0].Geometry.Bounds.MaxX += 1.0;
        Assert(BuildingSemanticDeterminism.Compute(snapshot) != baseline, "source chain/transform/bounds were omitted from content hash");
    }

    private static void TestSideDatabaseAllowsStableNonzeroDbmod()
    {
        BuildingSemanticSnapshot snapshot = Analyze(
            CreateProfile(),
            new[] { CreateFact(CadFactKind.Wall, "57", 0, 0, "Ordinary") });
        ScanIntegrityPolicy.Apply(
            snapshot,
            DrawingHash,
            DrawingHash,
            1,
            1,
            ScanInputMode.DiskSideDatabase,
            true);

        Assert(snapshot.Status != AnalysisRunStatus.Failed, "stable T20 DBMOD incorrectly failed a disk side scan");
        Assert(snapshot.Integrity.ScanInputMode == ScanInputMode.DiskSideDatabase, "side scan mode missing");
        Assert(snapshot.Integrity.InputDatabaseReadOnly, "side database was not recorded read-only");
        Assert(!snapshot.Integrity.DbmodCleanAtStart && snapshot.Integrity.DbmodUnchanged,
            "nonzero but stable active DBMOD evidence was recorded incorrectly");
        Assert(!snapshot.ReasonCodes.Contains(BuildingSemanticReasonCodes.SourceDrawingDirty),
            "activity DBMOD was treated as the disk scan input");

        string boundHash = snapshot.DeterministicContentHash;
        snapshot.Integrity.InputDatabaseReadOnly = false;
        Assert(BuildingSemanticDeterminism.Compute(snapshot) != boundHash,
            "read-only side-input declaration was omitted from the content hash");
        snapshot.Integrity.InputDatabaseReadOnly = true;
        snapshot.Integrity.ScanInputMode = ScanInputMode.ActiveDocument;
        Assert(BuildingSemanticDeterminism.Compute(snapshot) != boundHash,
            "scan input mode was omitted from the content hash");
    }

    private static void TestActiveDocumentRequiresCleanDbmod()
    {
        BuildingSemanticSnapshot snapshot = Analyze(
            CreateProfile(),
            new[] { CreateFact(CadFactKind.Wall, "58", 0, 0, "Ordinary") });
        ScanIntegrityPolicy.Apply(
            snapshot,
            DrawingHash,
            DrawingHash,
            1,
            1,
            ScanInputMode.ActiveDocument,
            false);

        Assert(snapshot.Status == AnalysisRunStatus.Failed, "dirty active-document input did not fail closed");
        Assert(snapshot.ReasonCodes.Contains(BuildingSemanticReasonCodes.SourceDrawingDirty),
            "dirty active-document reason code missing");
        AssertQuarantined(snapshot, "dirty active-document input");
    }

    private static void TestUnavailableDbmodQuarantinesOutput()
    {
        BuildingSemanticSnapshot snapshot = SemanticSnapshotWithRelation("5A");
        ScanIntegrityPolicy.Apply(
            snapshot,
            DrawingHash,
            DrawingHash,
            -1,
            -1,
            ScanInputMode.DiskSideDatabase,
            true);

        Assert(snapshot.Status == AnalysisRunStatus.Failed, "unavailable DBMOD did not fail closed");
        Assert(snapshot.ReasonCodes.Contains(BuildingSemanticReasonCodes.DbmodEvidenceUnavailable),
            "unavailable DBMOD reason code missing");
        AssertQuarantined(snapshot, "unavailable DBMOD");
    }

    private static void TestChangingDbmodQuarantinesOutput()
    {
        BuildingSemanticSnapshot snapshot = SemanticSnapshotWithRelation("5B");
        ScanIntegrityPolicy.Apply(
            snapshot,
            DrawingHash,
            DrawingHash,
            1,
            2,
            ScanInputMode.DiskSideDatabase,
            true);

        Assert(snapshot.Status == AnalysisRunStatus.Failed, "changing DBMOD did not fail closed");
        Assert(snapshot.ReasonCodes.Contains(BuildingSemanticReasonCodes.SourceModifiedDuringScan),
            "changing DBMOD reason code missing");
        AssertQuarantined(snapshot, "changing DBMOD");
    }

    private static void TestWritableSideDatabaseQuarantinesOutput()
    {
        BuildingSemanticSnapshot snapshot = SemanticSnapshotWithRelation("5C");
        ScanIntegrityPolicy.Apply(
            snapshot,
            DrawingHash,
            DrawingHash,
            1,
            1,
            ScanInputMode.DiskSideDatabase,
            false);

        Assert(snapshot.Status == AnalysisRunStatus.Failed, "writable side database did not fail closed");
        Assert(snapshot.ReasonCodes.Contains(BuildingSemanticReasonCodes.ScanInputNotReadOnly),
            "writable side database reason code missing");
        AssertQuarantined(snapshot, "writable side database");
    }

    private static void TestSemanticPayloadHashForView()
    {
        BuildingSemanticSnapshot expected = Analyze(
            CreateProfile(),
            new[] { CreateFact(CadFactKind.Wall, "59", 0, 0, "Ordinary") });
        BuildingSemanticSnapshot active = Analyze(
            CreateProfile(),
            new[] { CreateFact(CadFactKind.Wall, "59", 0, 0, "Ordinary") });
        active.ProducerBinarySha256 = ProfileHash;
        active.Integrity.ScanInputMode = ScanInputMode.DiskSideDatabase;
        active.Integrity.InputDatabaseReadOnly = true;
        active.Integrity.DbmodBefore = 1;
        active.Integrity.DbmodAfter = 1;

        string expectedPayload = BuildingSemanticDeterminism.ComputeSemanticPayload(expected);
        string expectedViewPayload = BuildingSemanticDeterminism.ComputeViewPayload(expected);
        Assert(expectedPayload == BuildingSemanticDeterminism.ComputeSemanticPayload(active),
            "producer/integrity evidence leaked into view payload hash");
        Assert(expectedViewPayload == BuildingSemanticDeterminism.ComputeViewPayload(active),
            "producer/integrity evidence leaked into rendered view payload hash");

        active.Findings.Add(new ReviewFinding
        {
            FindingId = "active-only-review-ledger",
            Severity = FindingSeverity.Review,
            ReasonCode = BuildingSemanticReasonCodes.LowConfidence,
            Message = "active interpreter review bookkeeping"
        });
        active.ProxyLedger.Add(new ProxyLedgerEntry
        {
            StablePath = "active-only-proxy",
            Disposition = ProxyDisposition.ReviewUnknown,
            ReasonCode = BuildingSemanticReasonCodes.UnsupportedProxyObject
        });
        active.Metrics.ReviewUnknownProxyCount++;
        Assert(expectedPayload != BuildingSemanticDeterminism.ComputeSemanticPayload(active),
            "audit payload failed to detect review-ledger drift");
        Assert(expectedViewPayload == BuildingSemanticDeterminism.ComputeViewPayload(active),
            "non-rendered review ledger incorrectly blocked view payload");

        active.Objects[0].Geometry.Bounds.MaxX += 1.0;
        active.Objects[0].Geometry.Paths[0][0].X += 1.0;
        Assert(expectedViewPayload != BuildingSemanticDeterminism.ComputeViewPayload(active),
            "rendered semantic geometry drift was not detected by view payload hash");
    }

    private static BuildingSemanticSnapshot SemanticSnapshotWithRelation(string handle)
    {
        CadFact opening = CreateFact(CadFactKind.Opening, handle, 0, 0, string.Empty);
        opening.Properties["opening_kind"] = "door";
        BuildingSemanticSnapshot snapshot = Analyze(CreateProfile(), new[] { opening });
        Assert(snapshot.Objects.Count > 0 && snapshot.Relations.Count > 0,
            "integrity quarantine fixture did not contain semantic output");
        return snapshot;
    }

    private static void AssertQuarantined(BuildingSemanticSnapshot snapshot, string scenario)
    {
        Assert(snapshot.Objects.Count == 0, scenario + " retained semantic objects");
        Assert(snapshot.Relations.Count == 0, scenario + " retained semantic relations");
        Assert(snapshot.Metrics.SemanticObjectCount == 0, scenario + " retained semantic object metrics");
        Assert(snapshot.Metrics.AcceptedObjectCount == 0, scenario + " retained accepted metrics");
        Assert(snapshot.Metrics.ReviewObjectCount == 0, scenario + " retained review metrics");
        Assert(snapshot.Metrics.RejectedObjectCount == 0, scenario + " retained rejected metrics");
        Assert(snapshot.Metrics.RelationCount == 0, scenario + " retained relation metrics");
    }

    private static void TestConcurrentReplay()
    {
        ProjectProfile profile = CreateProfile();
        CadFact original = CreateFact(CadFactKind.Wall, "56", 0, 0, "Ordinary");
        DrawingSnapshot frozen = DrawingSnapshot.Freeze(new CadFactSnapshot
        {
            ProviderId = "fixture:concurrent",
            IsSuccess = true,
            Facts = new List<CadFact> { original }
        });
        var service = new BuildingSemanticService(new FrozenProvider(frozen));
        BuildingSemanticSnapshot? first = null;
        BuildingSemanticSnapshot? second = null;
        Parallel.Invoke(
            () => first = service.Analyze(CreateRequest(profile)),
            () => second = service.Analyze(CreateRequest(profile)));
        Assert(first != null && second != null && first.DeterministicContentHash == second.DeterministicContentHash,
            "concurrent replay was not deterministic");
        Assert(original.Source.RawLayer == "A-Test", "concurrent analysis mutated provider input");
    }

    private static void TestReplayPerformance()
    {
        ProjectProfile profile = CreateProfile();
        var facts = Enumerable.Range(1, 500)
            .Select(index => CreateFact(index % 2 == 0 ? CadFactKind.Wall : CadFactKind.Column,
                index.ToString("X"), index * 1000.0, 0, index % 2 == 0 ? "Ordinary" : string.Empty))
            .ToList();
        var stopwatch = Stopwatch.StartNew();
        BuildingSemanticSnapshot snapshot = Analyze(profile, facts);
        stopwatch.Stop();
        Assert(snapshot.Objects.Count == 500, "replay object count mismatch");
        Assert(stopwatch.Elapsed < TimeSpan.FromSeconds(profile.Thresholds.ReplayMaximumSeconds), "replay exceeded five seconds");
    }

    private static void TestLayerIsolationFromSemanticDictionary()
    {
        ProjectProfile firstProfile = CreateProfile();
        CadFact space = CreateFact(CadFactKind.Space, "70", 0, 0, string.Empty);
        space.RawLabel = "厨房";
        var source = new CadFactSnapshot
        {
            ProviderId = "fixture:three-layers",
            IsSuccess = true,
            ReasonCodes = new List<string> { BuildingSemanticReasonCodes.Ok },
            Facts = new List<CadFact> { space }
        };
        BuildingRecognitionBundle first = new BuildingSemanticService(new FakeProvider(source)).AnalyzeLayers(CreateRequest(firstProfile));

        ProjectProfile secondProfile = CreateProfile();
        secondProfile.RoomUseDictionary.Add(new RoomUseRule
        {
            UseCode = "KITCHEN",
            SemanticType = SemanticObjectType.Space.ToString(),
            Keywords = new List<string> { "厨房" }
        });
        BuildingRecognitionBundle second = new BuildingSemanticService(new FakeProvider(source)).AnalyzeLayers(CreateRequest(secondProfile));

        Assert(first.PrimitiveSnapshot.DeterministicContentHash == second.PrimitiveSnapshot.DeterministicContentHash,
            "room dictionary changed primitive content hash");
        Assert(first.GeometrySnapshot.DeterministicContentHash == second.GeometrySnapshot.DeterministicContentHash,
            "room dictionary changed geometry content hash");
        Assert(first.SemanticSnapshot.Objects.Single().UseCode == "UNKNOWN", "baseline semantic use unexpectedly matched");
        Assert(second.SemanticSnapshot.Objects.Single().UseCode == "KITCHEN", "semantic dictionary was not applied at layer three");
    }

    private static void TestGeometrySemanticRuleValidation()
    {
        ProjectProfile profile = CreateProfile();
        profile.GeometrySemanticRules.Add(CreateColumnRule());
        Assert(ProjectProfileValidator.Validate(profile).IsValid, "valid geometry semantic rule was rejected");

        profile.GeometrySemanticRules[0].MaximumAreaSquareMillimeters =
            profile.GeometrySemanticRules[0].MinimumAreaSquareMillimeters;
        ProfileValidationResult invalid = ProjectProfileValidator.Validate(profile);
        Assert(!invalid.IsValid && invalid.ReasonCodes.Contains(BuildingSemanticReasonCodes.ProfileInvalid),
            "invalid geometry semantic area range bypassed profile validation");

        profile = CreateProfile();
        GeometrySemanticRule invalidClassification = CreateShearWallRule();
        invalidClassification.Classification = "InventedWallClass";
        profile.GeometrySemanticRules.Add(invalidClassification);
        invalid = ProjectProfileValidator.Validate(profile);
        Assert(!invalid.IsValid && invalid.ReasonCodes.Contains(BuildingSemanticReasonCodes.ProfileInvalid),
            "invalid wall classification bypassed profile validation");
    }

    private static void TestRoomRulePackValidation()
    {
        ProjectProfile profile = CreateProfile();
        profile.RoomUseDictionary.Add(new RoomUseRule
        {
            UseCode = "LIVING_ROOM",
            SemanticType = "Space",
            RulePack = "Ground Residential",
            Keywords = new List<string> { "客厅" }
        });
        ProfileValidationResult validation = ProjectProfileValidator.Validate(profile);
        Assert(!validation.IsValid
               && validation.ReasonCodes.Contains(BuildingSemanticReasonCodes.ProfileInvalid),
            "invalid room rule-pack identifier passed profile validation");
    }

    private static void TestProfileColumnPromotion()
    {
        CadPrimitive column = CreateNoncandidateRegionPrimitive("semantic-column", "S-COLU", 500, 500);
        ProjectProfile baselineProfile = CreateProfile();
        BuildingRecognitionBundle baseline = AnalyzePrimitives(baselineProfile, new[] { column });

        ProjectProfile promotedProfile = CreateProfile();
        promotedProfile.GeometrySemanticRules.Add(CreateColumnRule());
        BuildingRecognitionBundle promoted = AnalyzePrimitives(promotedProfile, new[] { column });

        Assert(baseline.PrimitiveSnapshot.DeterministicContentHash == promoted.PrimitiveSnapshot.DeterministicContentHash,
            "layer-three column rule changed the primitive layer");
        Assert(baseline.GeometrySnapshot.DeterministicContentHash == promoted.GeometrySnapshot.DeterministicContentHash,
            "layer-three column rule changed the geometry layer");
        Assert(baseline.SemanticSnapshot.Objects.Count == 0, "unconfigured geometry leaked into semantics");
        SemanticObject semanticColumn = promoted.SemanticSnapshot.Objects.Single();
        Assert(semanticColumn.Type == SemanticObjectType.Column, "configured structural outline was not promoted to Column");
        Assert(semanticColumn.Status == DecisionStatus.Review, "unreviewed profile inference was auto-accepted");
        Assert(semanticColumn.Evidence.Any(item => item.Code == "PROJECT_GEOMETRY_SEMANTIC_RULE"),
            "promoted column lacks its profile-rule evidence");
        Assert(promoted.GeometrySnapshot.Facts.Single().IsSemanticCandidate == false,
            "column promotion rewrote the reusable geometry fact");
    }

    private static void TestXclipHiddenGeometry()
    {
        CadPrimitive column = CreateNoncandidateRegionPrimitive("clipped-column", "S-COLU", 500, 500);
        column.RawProperties["xclip_visibility"] = "hidden";
        ProjectProfile profile = CreateProfile();
        profile.GeometrySemanticRules.Add(CreateColumnRule());
        BuildingRecognitionBundle result = AnalyzePrimitives(profile, new[] { column });
        Assert(result.PrimitiveSnapshot.Primitives.Count == 1, "xclip-hidden source vanished from L1 audit");
        Assert(result.GeometrySnapshot.Facts.Count == 1, "xclip-hidden geometry vanished from L2 audit");
        Assert(result.GeometrySnapshot.Facts[0].RawProperties["xclip_visibility"] == "hidden",
            "xclip visibility evidence did not survive into L2");
        Assert(result.SemanticSnapshot.Objects.All(item => item.Type != SemanticObjectType.Column),
            "xclip-hidden outline leaked into L3 semantics");
    }

    private static void TestProfileShearWallPromotion()
    {
        CadPrimitive outline = CreateNoncandidateRegionPrimitive("structural-outline", "S-WALL", 1000, 300);
        ProjectProfile profile = CreateProfile();
        profile.GeometrySemanticRules.Add(CreateShearWallRule());
        Assert(AnalyzePrimitives(profile, new[] { outline }).SemanticSnapshot.Objects.Count == 0,
            "S-WALL outline alone was incorrectly treated as a shear wall");

        CadPrimitive hatch = CreateNoncandidateRegionPrimitive("shear-hatch", "S-PATT-WALL", 1000, 300);
        hatch.Kind = CadPrimitiveKind.Hatch;
        hatch.Source.NativeDxfName = "HATCH";
        hatch.Source.NativeClassName = "AcDbHatch";
        hatch.RawProperties["hatch_pattern_name"] = "钢筋混凝土";
        SemanticObject wall = AnalyzePrimitives(profile, new[] { hatch }).SemanticSnapshot.Objects.Single();
        Assert(wall.Type == SemanticObjectType.Wall, "reinforced-concrete wall hatch was not promoted to Wall");
        Assert(wall.Classification == WallClassification.Shear.ToString(),
            "reinforced-concrete wall hatch did not retain Shear classification");
        Assert(wall.Status == DecisionStatus.Review, "shear wall was automatically accepted");

        CadPrimitive wrongPattern = RecognitionLayerClone.ClonePrimitive(hatch);
        wrongPattern.RawProperties["hatch_pattern_name"] = "ANSI31";
        Assert(AnalyzePrimitives(profile, new[] { wrongPattern }).SemanticSnapshot.Objects.Count == 0,
            "non-concrete hatch pattern bypassed the shear-wall evidence rule");
    }

    private static void TestMasonryMaterialClassification()
    {
        CadFact masonry = CreateFact(CadFactKind.Wall, "masonry", 0, 0, string.Empty);
        masonry.Properties["WallMaterial"] = "加气块";
        SemanticObject masonryWall = Analyze(CreateProfile(), new[] { masonry }).Objects.Single();
        Assert(masonryWall.Classification == WallClassification.Masonry.ToString(),
            "explicit masonry material was not preserved as Masonry");

        CadFact unknown = CreateFact(CadFactKind.Wall, "unknown-wall", 1000, 0, string.Empty);
        SemanticObject unknownWall = Analyze(CreateProfile(), new[] { unknown }).Objects.Single();
        Assert(unknownWall.Classification == WallClassification.Unknown.ToString(),
            "wall without material evidence was incorrectly treated as ordinary/masonry");
    }

    private static void TestProfileRoomPromotion()
    {
        ProjectProfile profile = CreateProfile();
        profile.RoomUseDictionary.Add(new RoomUseRule
        {
            UseCode = "ELECTRICAL_ROOM",
            SemanticType = SemanticObjectType.Space.ToString(),
            Keywords = new List<string> { "电气间", "电表间" }
        });
        profile.GeometrySemanticRules.Add(CreateRoomRule());

        CadPrimitive boundary = CreateNoncandidateRegionPrimitive("semantic-room", "X-Asst", 6000, 5000);
        CadPrimitive name = CreateTextPrimitive("semantic-room-name", "A-Spac-Iden-Auto", "电气间", 1000, 1000);
        CadPrimitive area = CreateTextPrimitive("semantic-room-area", "A-Spac-Area-Auto", "30.00m%%1402%%141", 1200, 1200);
        BuildingRecognitionBundle recognized = AnalyzePrimitives(profile, new[] { boundary, name, area });
        SemanticObject room = recognized.SemanticSnapshot.Objects.Single();
        Assert(room.Type == SemanticObjectType.Space && room.RawLabel == "电气间" && room.UseCode == "ELECTRICAL_ROOM",
            "room name/use was not derived from the contained project text");
        Assert(room.Evidence.Any(item => item.Code == "ROOM_LABEL_CONTAINED_TEXT")
               && room.Evidence.Any(item => item.Code == "ROOM_AREA_TEXT_MATCH"),
            "promoted room lacks name/area evidence");

        CadPrimitive wrongArea = CreateTextPrimitive("semantic-room-wrong-area", "A-Spac-Area-Auto", "8.64m%%1402%%141", 1200, 1200);
        BuildingRecognitionBundle mismatched = AnalyzePrimitives(profile, new[] { boundary, name, wrongArea });
        Assert(mismatched.SemanticSnapshot.Objects.Count == 0, "mismatched room area text was ignored");

        CadPrimitive parkingNumber = CreateTextPrimitive("semantic-parking-number", "A-Spac-Iden-Auto", "33", 1000, 1000);
        BuildingRecognitionBundle parking = AnalyzePrimitives(profile, new[] { boundary, parkingNumber, area });
        Assert(parking.SemanticSnapshot.Objects.Count == 0, "numbered parking frame was promoted as a room");
    }

    private static void TestWallNetworkRoomPromotion()
    {
        ProjectProfile profile = CreateProfile();
        profile.RoomUseDictionary.Add(new RoomUseRule
        {
            UseCode = "ELECTRICAL_ROOM",
            SemanticType = SemanticObjectType.Space.ToString(),
            Keywords = new List<string> { "电气间" }
        });
        profile.GeometrySemanticRules.Add(CreateWallBoundedRoomRule());
        Assert(ProjectProfileValidator.Validate(profile).IsValid, "wall-bounded room profile rule was rejected");

        var primitives = new List<CadPrimitive>
        {
            CreateWallLinePrimitive("wall-bottom", 0, 0, 6000, 0),
            CreateWallLinePrimitive("wall-top", 0, 5000, 6000, 5000),
            CreateWallLinePrimitive("wall-left", 0, 0, 0, 5000),
            CreateWallLinePrimitive("wall-right", 6000, 0, 6000, 5000),
            CreateWallLinePrimitive("wall-divider", 3000, 0, 3000, 5000),
            CreateTextPrimitive("left-room-name", "A-Spac-Iden-Auto", "电气间", 1500, 2500)
        };
        BuildingRecognitionBundle recognized = AnalyzePrimitives(profile, primitives);
        BuildingRecognitionBundle repeated = AnalyzePrimitives(profile, primitives);
        Assert(recognized.GeometrySnapshot.DeterministicContentHash == repeated.GeometrySnapshot.DeterministicContentHash
               && recognized.SemanticSnapshot.Objects.Select(item => item.SemanticId)
                   .SequenceEqual(repeated.SemanticSnapshot.Objects.Select(item => item.SemanticId)),
            "wall-bounded room replay was not deterministic");
        List<GeometryFact> loops = recognized.GeometrySnapshot.Facts
            .Where(item => item.RawProperties.TryGetValue("derived_geometry", out string value)
                           && value == "wall_bounded_region")
            .ToList();
        Assert(loops.Count == 2 && loops.All(item => item.SourcePrimitiveIds.Count >= 4),
            "wall T-junctions did not form two traceable L2 regions");
        SemanticObject room = recognized.SemanticSnapshot.Objects.Single(item => item.Type == SemanticObjectType.Space);
        Assert(room.RawLabel == "电气间" && room.UseCode == "ELECTRICAL_ROOM",
            "wall-bounded region did not receive the contained room use");
        Assert(room.Status == DecisionStatus.Review && !room.Geometry.IsExact,
            "5mm-derived room boundary was incorrectly auto-accepted as exact");

        primitives.Add(CreateTextPrimitive("left-room-ambiguous", "A-Spac-Iden-Auto", "电气间", 2000, 2500));
        BuildingRecognitionBundle ambiguous = AnalyzePrimitives(profile, primitives);
        Assert(ambiguous.SemanticSnapshot.Objects.All(item => item.Type != SemanticObjectType.Space),
            "wall-bounded region containing two room names bypassed the ambiguity gate");
        Assert(ambiguous.SemanticSnapshot.Findings.Count(item =>
                   item.ReasonCode == BuildingSemanticReasonCodes.KnownSpaceLabelUnresolved) == 2,
            "unresolved known room labels were not exposed as drafting-review findings");
    }

    private static void TestConcreteWallBoundarySupplement()
    {
        ProjectProfile profile = CreateProfile();
        profile.RoomUseDictionary.Add(new RoomUseRule
        {
            UseCode = "ELECTRICAL_ROOM",
            SemanticType = SemanticObjectType.Space.ToString(),
            Keywords = new List<string> { "配电房" }
        });
        profile.GeometrySemanticRules.Add(CreateWallBoundedRoomRule());

        var primitives = new List<CadPrimitive>
        {
            CreateWallLinePrimitive("wall-bottom", 0, 0, 6000, 0),
            CreateWallLinePrimitive("wall-top", 0, 5000, 6000, 5000),
            CreateWallLinePrimitive("wall-left", 0, 0, 0, 5000),
            CreateConcreteWallBoundaryPrimitive("concrete-wall-right", 5800, 0, 200, 5000),
            CreateTextPrimitive("room-name", "A-Spac-Iden-Auto", "配电房", 3000, 2500)
        };

        BuildingRecognitionBundle recognized = AnalyzePrimitives(profile, primitives);
        SemanticObject room = recognized.SemanticSnapshot.Objects.Single(item => item.Type == SemanticObjectType.Space);
        Assert(room.RawLabel == "配电房" && room.UseCode == "ELECTRICAL_ROOM",
            "reinforced-concrete boundary did not complete the named room");
        Assert(room.Evidence.Any(item => item.Code == "WALL_NETWORK_BOUNDED_REGION"
                                         && item.Value.Contains("boundary_sources=t20_wall+reinforced_concrete_hatch")),
            "supplemented room did not preserve its mixed boundary evidence");
    }

    private static void TestLightWellShaftPromotion()
    {
        ProjectProfile profile = CreateProfile();
        profile.RoomUseDictionary.Add(new RoomUseRule
        {
            UseCode = "LIGHT_WELL",
            SemanticType = SemanticObjectType.Shaft.ToString(),
            Keywords = new List<string> { "采光井" }
        });
        profile.GeometrySemanticRules.Add(CreateWallBoundedRoomRule());

        var primitives = new List<CadPrimitive>
        {
            CreateWallLinePrimitive("wall-bottom", 0, 0, 3000, 0),
            CreateWallLinePrimitive("wall-top", 0, 3000, 3000, 3000),
            CreateWallLinePrimitive("wall-left", 0, 0, 0, 3000),
            CreateWallLinePrimitive("wall-right", 3000, 0, 3000, 3000),
            CreateTextPrimitive("shaft-name", "A-Spac-Iden-Auto", "采光井", 1500, 1500)
        };

        BuildingRecognitionBundle recognized = AnalyzePrimitives(profile, primitives);
        SemanticObject shaft = recognized.SemanticSnapshot.Objects.Single(item => item.Type == SemanticObjectType.Shaft);
        Assert(shaft.Type == SemanticObjectType.Shaft && shaft.UseCode == "LIGHT_WELL",
            "confirmed light well was not separated from ordinary rooms");
        Assert(shaft.Status == DecisionStatus.Review,
            "derived light-well geometry bypassed the Review gate");
    }

    private static void TestSmallShaftOpeningBoundaryPromotion()
    {
        ProjectProfile profile = CreateProfile();
        profile.RoomUseDictionary.Add(new RoomUseRule
        {
            UseCode = "ELECTRICAL_SHAFT",
            SemanticType = SemanticObjectType.Shaft.ToString(),
            Keywords = new List<string> { "电井" }
        });
        profile.GeometrySemanticRules.Add(CreateWallBoundedRoomRule());

        var boundaries = new List<CadPrimitive>
        {
            CreateWallLinePrimitive("small-shaft-bottom", 0, 0, 2000, 0),
            CreateWallLinePrimitive("small-shaft-left", 0, 0, 0, 600),
            CreateWallLinePrimitive("small-shaft-right", 2000, 0, 2000, 600),
            CreateWallLinePrimitive("small-shaft-top-left", 0, 600, 200, 600),
            CreateWallLinePrimitive("small-shaft-top-right", 1600, 600, 2000, 600),
            CreateOpeningBoundaryPrimitive("small-shaft-opening", 200, 600, 1600, 600),
            CreateTextPrimitive("small-shaft-name", "A-Spac-Iden-Auto", "电井", 1000, 300)
        };

        BuildingRecognitionBundle recognized = AnalyzePrimitives(profile, boundaries);
        SemanticObject shaft = recognized.SemanticSnapshot.Objects.Single(item => item.Type == SemanticObjectType.Shaft);
        Assert(shaft.UseCode == "ELECTRICAL_SHAFT" && shaft.Status == DecisionStatus.Review,
            "small electrical shaft was not preserved as Review");
        Assert(Math.Abs((shaft.Geometry.Bounds.MaxX - shaft.Geometry.Bounds.MinX)
                        * (shaft.Geometry.Bounds.MaxY - shaft.Geometry.Bounds.MinY) - 1200000.0) < 1,
            "small electrical shaft did not retain its real 2000x600 geometry");
        Assert(shaft.Evidence.Any(item => item.Code == "WALL_NETWORK_BOUNDED_REGION"
                                         && item.Value.Contains("t20_opening")),
            "small electrical shaft lacks exact opening-boundary evidence");

        var closedWithoutOpening = new List<CadPrimitive>
        {
            CreateWallLinePrimitive("closed-small-shaft-bottom", 0, 0, 2000, 0),
            CreateWallLinePrimitive("closed-small-shaft-left", 0, 0, 0, 600),
            CreateWallLinePrimitive("closed-small-shaft-right", 2000, 0, 2000, 600),
            CreateWallLinePrimitive("closed-small-shaft-top", 0, 600, 2000, 600),
            CreateTextPrimitive("closed-small-shaft-name", "A-Spac-Iden-Auto", "电井", 1000, 300)
        };
        Assert(AnalyzePrimitives(profile, closedWithoutOpening).SemanticSnapshot.Objects.Any(item =>
                item.Type == SemanticObjectType.Shaft
                && item.Evidence.Any(evidence => evidence.Code == "SHAFT_LABEL_SMALL_WALL_LOOP")),
            "confirmed shaft label did not bypass the ordinary-room two-square-meter threshold");

        List<CadPrimitive> missingOpening = boundaries
            .Where(item => item.Source.Handle != "small-shaft-opening")
            .ToList();
        Assert(AnalyzePrimitives(profile, missingOpening).SemanticSnapshot.Objects.All(item => item.Type != SemanticObjectType.Shaft),
            "missing opening edge was silently filled to create a shaft");

        List<CadPrimitive> ordinaryRoom = boundaries
            .Where(item => item.Source.Handle != "small-shaft-name")
            .Append(CreateTextPrimitive("small-room-name", "A-Spac-Iden-Auto", "电气间", 1000, 300))
            .ToList();
        profile.RoomUseDictionary.Add(new RoomUseRule
        {
            UseCode = "ELECTRICAL_ROOM",
            SemanticType = SemanticObjectType.Space.ToString(),
            Keywords = new List<string> { "电气间" }
        });
        Assert(AnalyzePrimitives(profile, ordinaryRoom).SemanticSnapshot.Objects.All(item => item.Type != SemanticObjectType.Space),
            "shaft exception incorrectly lowered the ordinary-room area threshold");
    }

    private static void TestShaftSizeAndTransformInvariance()
    {
        ProjectProfile profile = CreateElectricalShaftProfile();
        var cases = new[]
        {
            new { Name = "below-two-square-metres", Width = 1800.0, Height = 500.0, X = 0.0, Y = 0.0, Angle = 0.0 },
            new { Name = "above-two-square-metres", Width = 2800.0, Height = 900.0, X = 0.0, Y = 0.0, Angle = 0.0 },
            new { Name = "translated", Width = 1800.0, Height = 500.0, X = 7300.0, Y = -4200.0, Angle = 0.0 },
            new { Name = "rotated-thirty-degrees", Width = 1800.0, Height = 500.0, X = 5000.0, Y = 7000.0, Angle = 30.0 }
        };

        foreach (var item in cases)
        {
            List<SemanticPoint> corners = RectangleCorners(item.Width, item.Height, item.X, item.Y, item.Angle);
            var primitives = new List<CadPrimitive>();
            for (int index = 0; index < 4; index++)
            {
                SemanticPoint start = corners[index];
                SemanticPoint end = corners[(index + 1) % 4];
                primitives.Add(CreateWallLinePrimitive(item.Name + "-wall-" + index, start.X, start.Y, end.X, end.Y));
            }
            SemanticPoint center = TransformPoint(item.Width / 2, item.Height / 2, item.X, item.Y, item.Angle);
            primitives.Add(CreateTextPrimitive(item.Name + "-name", "A-Spac-Iden-Auto", "电井", center.X, center.Y));

            SemanticObject shaft = SingleElectricalShaft(AnalyzePrimitives(profile, primitives), item.Name);
            double expectedArea = item.Width * item.Height;
            double actualArea = PolygonArea(shaft.Geometry);
            Console.WriteLine("SHAFT_METAMORPH case=" + item.Name
                              + " expected_area=" + expectedArea.ToString("R")
                              + " actual_area=" + actualArea.ToString("R"));
            Assert(Math.Abs(actualArea - expectedArea) <= expectedArea * 0.02,
                item.Name + " changed the shaft area beyond the 5mm snap tolerance");
        }
    }

    private static void TestLShapedShaftPromotion()
    {
        ProjectProfile profile = CreateElectricalShaftProfile();
        var loop = new List<SemanticPoint>
        {
            new SemanticPoint(0, 0),
            new SemanticPoint(2000, 0),
            new SemanticPoint(2000, 400),
            new SemanticPoint(800, 400),
            new SemanticPoint(800, 1200),
            new SemanticPoint(0, 1200),
            new SemanticPoint(0, 0)
        };
        BuildingRecognitionBundle recognized = AnalyzePrimitives(profile, new[]
        {
            CreateWallPathPrimitive("l-shaft-wall", loop),
            CreateTextPrimitive("l-shaft-name", "A-Spac-Iden-Auto", "电井", 400, 700)
        });
        SemanticObject shaft = SingleElectricalShaft(recognized, "L-shaped shaft");
        Console.WriteLine("SHAFT_METAMORPH case=l-shaped expected_area=1440000 actual_area="
                          + PolygonArea(shaft.Geometry).ToString("R"));
        Assert(shaft.Geometry.Paths.Single().Distinct().Count() >= 6,
            "L-shaped shaft was reduced to a rectangle");
        Assert(Math.Abs(PolygonArea(shaft.Geometry) - 1440000.0) < 1,
            "L-shaped shaft did not retain its 1.44 square metre geometry");
    }

    private static void TestShaftBoundarySourceGrouping()
    {
        ProjectProfile profile = CreateElectricalShaftProfile();
        List<SemanticPoint> rectangle = RectangleCorners(2000, 600, 0, 0, 0);
        rectangle.Add(rectangle[0]);
        SemanticObject singleSource = SingleElectricalShaft(AnalyzePrimitives(profile, new[]
        {
            CreateWallPathPrimitive("single-wall-path", rectangle),
            CreateTextPrimitive("single-wall-name", "A-Spac-Iden-Auto", "电井", 1000, 300)
        }), "single-source shaft");

        var segmented = new List<CadPrimitive>
        {
            CreateWallLinePrimitive("seg-bottom", 0, 0, 2000, 0),
            CreateWallLinePrimitive("seg-left", 0, 0, 0, 600),
            CreateWallLinePrimitive("seg-right", 2000, 0, 2000, 600),
            CreateWallLinePrimitive("seg-top-left", 0, 600, 200, 600),
            CreateWallLinePrimitive("seg-top-right", 1600, 600, 2000, 600),
            CreateOpeningBoundaryPrimitive("seg-opening", 200, 600, 1600, 600),
            CreateTextPrimitive("seg-name", "A-Spac-Iden-Auto", "电井", 1000, 300)
        };
        SemanticObject segmentedSource = SingleElectricalShaft(AnalyzePrimitives(profile, segmented), "segmented shaft");
        CadPrimitive groupedWall = CreateWallMultiPathPrimitive("grouped-gapped-wall", new List<List<SemanticPoint>>
        {
            new List<SemanticPoint> { new SemanticPoint(0, 0), new SemanticPoint(2000, 0) },
            new List<SemanticPoint> { new SemanticPoint(0, 0), new SemanticPoint(0, 600) },
            new List<SemanticPoint> { new SemanticPoint(2000, 0), new SemanticPoint(2000, 600) },
            new List<SemanticPoint> { new SemanticPoint(0, 600), new SemanticPoint(200, 600) },
            new List<SemanticPoint> { new SemanticPoint(1600, 600), new SemanticPoint(2000, 600) }
        });
        SemanticObject groupedWithOpening = SingleElectricalShaft(AnalyzePrimitives(profile, new[]
        {
            groupedWall,
            CreateOpeningBoundaryPrimitive("grouped-opening", 200, 600, 1600, 600),
            CreateTextPrimitive("grouped-name", "A-Spac-Iden-Auto", "电井", 1000, 300)
        }), "single-source gapped shaft");
        Console.WriteLine("SHAFT_METAMORPH case=source-grouping expected_area=1200000 single_source_area="
                          + PolygonArea(singleSource.Geometry).ToString("R")
                          + " segmented_area=" + PolygonArea(segmentedSource.Geometry).ToString("R")
                          + " grouped_opening_area=" + PolygonArea(groupedWithOpening.Geometry).ToString("R"));
        Assert(Math.Abs(PolygonArea(singleSource.Geometry) - PolygonArea(segmentedSource.Geometry)) < 1,
            "source grouping changed the shaft geometry");
        Assert(Math.Abs(PolygonArea(singleSource.Geometry) - PolygonArea(groupedWithOpening.Geometry)) < 1,
            "wallSourceCount changed the result when one TDbWall carried the same gapped wall paths");
        Assert(segmentedSource.Evidence.Any(item => item.Code == "WALL_NETWORK_BOUNDED_REGION"
                                                    && item.Value.Contains("t20_opening")),
            "segmented shaft lost its real opening-boundary evidence");
    }

    private static void TestOpeningSwingPathDoesNotSubdivideShaft()
    {
        ProjectProfile profile = CreateElectricalShaftProfile();
        CadPrimitive opening = CreateOpeningBoundaryPrimitive("swing-opening", 200, 600, 1600, 600);
        opening.RawGeometry.Paths.Add(new List<SemanticPoint>
        {
            new SemanticPoint(200, 600),
            new SemanticPoint(1000, 0)
        });
        opening.RawGeometry.Bounds = SemanticGeometryAlgorithms.CalculateBounds(opening.RawGeometry.Paths);
        var primitives = new List<CadPrimitive>
        {
            CreateWallLinePrimitive("swing-bottom", 0, 0, 2000, 0),
            CreateWallLinePrimitive("swing-left", 0, 0, 0, 600),
            CreateWallLinePrimitive("swing-right", 2000, 0, 2000, 600),
            CreateWallLinePrimitive("swing-top-left", 0, 600, 200, 600),
            CreateWallLinePrimitive("swing-top-right", 1600, 600, 2000, 600),
            opening,
            CreateTextPrimitive("swing-name", "A-Spac-Iden-Auto", "电井", 400, 300)
        };

        BuildingRecognitionBundle recognized = AnalyzePrimitives(profile, primitives);
        GeometryFact openingFact = recognized.GeometrySnapshot.Facts.Single(item =>
            item.Source.Handle == "swing-opening" && item.AdapterRoleHint == CadFactKind.Opening.ToString());
        Assert(openingFact.Geometry.Paths.Count == 2,
            "opening swing path was removed from the reusable geometry fact");
        SemanticObject shaft = SingleElectricalShaft(recognized, "opening-swing shaft");
        double actualArea = PolygonArea(shaft.Geometry);
        Assert(Math.Abs(actualArea - 1200000.0) < 1,
            "opening swing path was mistaken for a room boundary and subdivided the shaft; expected_area=1200000 actual_area="
            + actualArea.ToString("R"));

        var splitBottomPrimitives = new List<CadPrimitive>
        {
            CreateWallLinePrimitive("swing-bottom-left", 0, 0, 1000, 0),
            CreateWallLinePrimitive("swing-bottom-right", 1000, 0, 2000, 0),
            CreateWallLinePrimitive("swing-left-split", 0, 0, 0, 600),
            CreateWallLinePrimitive("swing-right-split", 2000, 0, 2000, 600),
            CreateWallLinePrimitive("swing-top-left-split", 0, 600, 200, 600),
            CreateWallLinePrimitive("swing-top-right-split", 1600, 600, 2000, 600),
            opening,
            CreateTextPrimitive("swing-name-split", "A-Spac-Iden-Auto", "电井", 400, 300)
        };
        SemanticObject splitBottomShaft = SingleElectricalShaft(
            AnalyzePrimitives(profile, splitBottomPrimitives),
            "opening-swing shaft with a split bottom wall");
        double splitBottomArea = PolygonArea(splitBottomShaft.Geometry);
        Console.WriteLine("SHAFT_METAMORPH case=opening-swing-split-wall expected_area=1200000 actual_area="
                          + splitBottomArea.ToString("R"));
        Assert(Math.Abs(splitBottomArea - 1200000.0) < 1,
            "splitting a wall at the swing-line landing point changed opening-boundary classification; expected_area=1200000 actual_area="
            + splitBottomArea.ToString("R"));
    }

    private static void TestPairedOpeningSpansRequireBothWallReturns()
    {
        ProjectProfile profile = CreateElectricalShaftProfile();
        const double left = 3100;
        const double bottom = 4200;
        const double right = 5100;
        const double lowerFace = 4800;
        const double upperFace = 4975;
        const double gapLeft = 3300;
        const double gapRight = 4700;

        CadPrimitive opening = CreateOpeningBoundaryPrimitive(
            "paired-return-opening", gapLeft, lowerFace, gapRight, lowerFace);
        opening.RawGeometry.Paths.Add(new List<SemanticPoint>
        {
            new SemanticPoint(gapLeft, upperFace),
            new SemanticPoint(gapRight, upperFace)
        });
        opening.RawGeometry.Bounds = SemanticGeometryAlgorithms.CalculateBounds(opening.RawGeometry.Paths);

        List<CadPrimitive> CompleteWalls()
        {
            return new List<CadPrimitive>
            {
                CreateWallLinePrimitive("paired-bottom", left, bottom, right, bottom),
                CreateWallLinePrimitive("paired-left", left, bottom, left, lowerFace),
                CreateWallLinePrimitive("paired-right", right, bottom, right, lowerFace),
                CreateWallLinePrimitive("paired-lower-left", left, lowerFace, gapLeft, lowerFace),
                CreateWallLinePrimitive("paired-lower-right", gapRight, lowerFace, right, lowerFace),
                CreateWallLinePrimitive("paired-left-return", gapLeft, lowerFace, gapLeft, upperFace),
                CreateWallLinePrimitive("paired-right-return", gapRight, lowerFace, gapRight, upperFace),
                CreateWallLinePrimitive("paired-upper-left", left, upperFace, gapLeft, upperFace),
                CreateWallLinePrimitive("paired-upper-right", gapRight, upperFace, right, upperFace)
            };
        }

        List<CadPrimitive> positive = CompleteWalls();
        positive.Add(opening);
        positive.Add(CreateTextPrimitive("paired-name", "A-Spac-Iden-Auto", "电井", 4100, 4500));
        SemanticObject shaft = SingleElectricalShaft(AnalyzePrimitives(profile, positive), "paired wall-return shaft");
        Assert(Math.Abs(PolygonArea(shaft.Geometry) - 1200000.0) < 1,
            "paired wall returns did not preserve the translated shaft with 175mm wall thickness");

        List<CadPrimitive> missingReturn = CompleteWalls()
            .Where(item => item.Source.Handle != "paired-right-return")
            .ToList();
        missingReturn.Add(opening);
        missingReturn.Add(CreateTextPrimitive("paired-name-missing", "A-Spac-Iden-Auto", "电井", 4100, 4500));
        BuildingRecognitionBundle rejected = AnalyzePrimitives(profile, missingReturn);
        Assert(rejected.SemanticSnapshot.Objects.All(item => item.Type != SemanticObjectType.Shaft),
            "paired opening spans were promoted despite missing one real wall return");

        List<CadPrimitive> inwardContinuation = CompleteWalls()
            .Where(item => item.Source.Handle != "paired-upper-right")
            .ToList();
        inwardContinuation.Add(CreateWallLinePrimitive(
            "paired-upper-right-inward", gapRight, upperFace, gapRight - 200, upperFace));
        inwardContinuation.Add(opening);
        inwardContinuation.Add(CreateTextPrimitive(
            "paired-name-inward", "A-Spac-Iden-Auto", "电井", 4100, 4500));
        BuildingRecognitionBundle inwardRejected = AnalyzePrimitives(profile, inwardContinuation);
        Assert(inwardRejected.SemanticSnapshot.Objects.All(item => item.Type != SemanticObjectType.Shaft),
            "paired opening spans were promoted when one wall face turned inward instead of extending outward");

        CadPrimitive collinearOpening = CreateOpeningBoundaryPrimitive(
            "collinear-opening", 200, 600, 1000, 600);
        collinearOpening.RawGeometry.Paths.Add(new List<SemanticPoint>
        {
            new SemanticPoint(1000, 600),
            new SemanticPoint(1800, 600)
        });
        collinearOpening.RawGeometry.Bounds =
            SemanticGeometryAlgorithms.CalculateBounds(collinearOpening.RawGeometry.Paths);
        BuildingRecognitionBundle collinear = AnalyzePrimitives(profile, new[]
        {
            CreateWallLinePrimitive("collinear-bottom", 0, 0, 2000, 0),
            CreateWallLinePrimitive("collinear-left", 0, 0, 0, 600),
            CreateWallLinePrimitive("collinear-right", 2000, 0, 2000, 600),
            CreateWallLinePrimitive("collinear-top-left", 0, 600, 200, 600),
            CreateWallLinePrimitive("collinear-return-left", 200, 600, 1000, 600),
            CreateWallLinePrimitive("collinear-return-right", 1000, 600, 1800, 600),
            CreateWallLinePrimitive("collinear-top-right", 1800, 600, 2000, 600),
            collinearOpening,
            CreateTextPrimitive("collinear-name", "A-Spac-Iden-Auto", "电井", 1000, 300)
        });
        Assert(collinear.GeometrySnapshot.Facts
            .Where(item => item.RawProperties.TryGetValue("derived_geometry", out string derived)
                           && derived == "wall_bounded_region")
            .All(item => !item.Evidence.Any(evidence => evidence.Code == "WALL_NETWORK_BOUNDED_REGION"
                                                        && evidence.Value.Contains("t20_opening"))),
            "collinear opening paths were mistaken for a spaced pair of wall-face spans");
    }

    private static void TestConfirmedRoomUseVocabulary()
    {
        ProjectProfile profile = CreateProfile();
        profile.RoomUseDictionary = new List<RoomUseRule>
        {
            new RoomUseRule { UseCode = "EVACUATION_CORRIDOR", SemanticType = "Space", Keywords = new List<string> { "走道", "过道" } },
            new RoomUseRule { UseCode = "ELECTRICAL_ROOM", SemanticType = "Space", Keywords = new List<string> { "进线间", "弱电机房", "信号覆盖机房", "安防控制室" } },
            new RoomUseRule { UseCode = "SPRINKLER_ALARM_VALVE_ROOM", SemanticType = "Space", Keywords = new List<string> { "报警阀间" } },
            new RoomUseRule { UseCode = "EQUIPMENT_ROOM", SemanticType = "Space", Keywords = new List<string> { "设备用房" } },
            new RoomUseRule { UseCode = "MAINTENANCE_ROOM", SemanticType = "Space", Keywords = new List<string> { "检修间" } },
            new RoomUseRule { UseCode = "ARRIVAL_LOBBY", SemanticType = "Space", Keywords = new List<string> { "光厅" } },
            new RoomUseRule { UseCode = "ELEVATOR_SHAFT", SemanticType = "Shaft", Keywords = new List<string> { "电梯井" } }
        };

        foreach ((string Label, string UseCode, SemanticObjectType Type) expected in new[]
                 {
                     ("光厅", "ARRIVAL_LOBBY", SemanticObjectType.Space),
                     ("预留设备用房", "EQUIPMENT_ROOM", SemanticObjectType.Space),
                     ("报警阀间", "SPRINKLER_ALARM_VALVE_ROOM", SemanticObjectType.Space),
                     ("疏散走道", "EVACUATION_CORRIDOR", SemanticObjectType.Space),
                     ("过道", "EVACUATION_CORRIDOR", SemanticObjectType.Space),
                     ("进线间", "ELECTRICAL_ROOM", SemanticObjectType.Space),
                     ("弱电机房", "ELECTRICAL_ROOM", SemanticObjectType.Space),
                     ("信号覆盖机房", "ELECTRICAL_ROOM", SemanticObjectType.Space),
                     ("安防控制室", "ELECTRICAL_ROOM", SemanticObjectType.Space),
                     ("检修间", "MAINTENANCE_ROOM", SemanticObjectType.Space),
                     ("电梯井", "ELEVATOR_SHAFT", SemanticObjectType.Shaft)
                 })
        {
            RoomUseMatch match = RoomUseClassifier.Match(expected.Label, profile);
            Assert(match.IsMatch && match.UseCode == expected.UseCode && match.SemanticType == expected.Type,
                "confirmed room vocabulary mismatch: " + expected.Label);
        }

        foreach (string excluded in new[] { "充电桩", "FM甲", "PD-01#", "1-E01", "填充区域详1#楼子项", "自然" })
            Assert(!RoomUseClassifier.Match(excluded, profile).IsMatch,
                "confirmed non-room text was promoted: " + excluded);
    }

    private static void TestGroundAndBasementRulePacks()
    {
        ProjectProfile profile = CreateProfile();
        profile.RoomUseDictionary = new List<RoomUseRule>
        {
            new RoomUseRule
            {
                UseCode = "PARKING_GARAGE",
                SemanticType = "Space",
                RulePack = BuildingSemanticRulePacks.Basement,
                Keywords = new List<string> { "汽车库" }
            },
            new RoomUseRule
            {
                UseCode = "LIVING_DINING_ROOM",
                SemanticType = "Space",
                RulePack = BuildingSemanticRulePacks.GroundResidential,
                Keywords = new List<string> { "客餐厅" },
                ExcludedKeywords = new List<string> { "上空" }
            },
            new RoomUseRule
            {
                UseCode = "LIVING_ROOM",
                SemanticType = "Space",
                RulePack = BuildingSemanticRulePacks.GroundResidential,
                Keywords = new List<string> { "客厅" },
                ExcludedKeywords = new List<string> { "上空" }
            },
            new RoomUseRule
            {
                UseCode = "DINING_ROOM",
                SemanticType = "Space",
                RulePack = BuildingSemanticRulePacks.GroundResidential,
                Keywords = new List<string> { "餐厅" },
                ExcludedKeywords = new List<string> { "上空" }
            },
            new RoomUseRule
            {
                UseCode = "BALCONY",
                SemanticType = "Space",
                RulePack = BuildingSemanticRulePacks.GroundResidential,
                Keywords = new List<string> { "阳台" },
                ExcludedKeywords = new List<string> { "屋面", "上空" }
            }
        };

        RoomUseMatch garage = RoomUseClassifier.Match("地下汽车库", profile);
        Assert(garage.IsMatch && garage.UseCode == "PARKING_GARAGE"
                              && garage.RulePack == BuildingSemanticRulePacks.Basement,
            "basement room rule pack was not retained");

        RoomUseMatch combined = RoomUseClassifier.Match("客餐厅", profile);
        Assert(combined.IsMatch && combined.UseCode == "LIVING_DINING_ROOM"
                               && combined.RulePack == BuildingSemanticRulePacks.GroundResidential,
            "combined living-dining room was swallowed by a broad dining rule");
        Assert(!RoomUseClassifier.Match("客厅上空", profile).IsMatch,
            "unconfirmed void label was guessed as an ordinary living room");
        Assert(!RoomUseClassifier.Match("阳台（保温上人屋面）", profile).IsMatch,
            "roof annotation was guessed as an ordinary balcony");

        CadFact livingRoom = CreateFact(CadFactKind.Space, "living-room", 0, 0, string.Empty);
        livingRoom.RawLabel = "客厅";
        SemanticObject semantic = Analyze(profile, new[] { livingRoom }).Objects.Single();
        Assert(semantic.UseCode == "LIVING_ROOM"
               && semantic.Evidence.Any(item => item.Code == "SEMANTIC_RULE_PACK"
                                                && item.Value == BuildingSemanticRulePacks.GroundResidential),
            "ground rule-pack provenance was not emitted into L3 evidence");
    }

    private static void TestFireWaterTankPromotion()
    {
        ProjectProfile profile = CreateProfile();
        profile.RoomUseDictionary.Add(new RoomUseRule
        {
            UseCode = "FIRE_WATER_TANK",
            SemanticType = SemanticObjectType.Zone.ToString(),
            Keywords = new List<string> { "消防水池" }
        });
        profile.GeometrySemanticRules.Add(CreateWallBoundedRoomRule());

        var primitives = new List<CadPrimitive>
        {
            CreateWallLinePrimitive("wall-bottom", 0, 0, 6000, 0),
            CreateWallLinePrimitive("wall-top", 0, 5000, 6000, 5000),
            CreateWallLinePrimitive("wall-left", 0, 0, 0, 5000),
            CreateWallLinePrimitive("wall-right", 6000, 0, 6000, 5000),
            CreateTextPrimitive("tank-name", "A-Spac-Iden-Auto", "消防水池一", 3000, 2500)
        };

        BuildingRecognitionBundle recognized = AnalyzePrimitives(profile, primitives);
        SemanticObject tank = recognized.SemanticSnapshot.Objects.Single(item => item.Type == SemanticObjectType.Zone);
        Assert(tank.UseCode == "FIRE_WATER_TANK" && tank.RawLabel == "消防水池一",
            "fire water tank did not retain its confirmed non-room use");
        Assert(recognized.SemanticSnapshot.Objects.All(item => item.Type != SemanticObjectType.Space),
            "fire water tank leaked into ordinary Room output");
    }

    private static void TestLayerGateIsolation()
    {
        ProjectProfile profile = CreateProfile();
        profile.RuleState = SemanticRuleState.Calibration;
        profile.ObservationRegions.Add(new ObservationRegion
        {
            Code = "B1",
            Name = "典型停车区",
            Role = ObservationRegionRole.Calibration,
            State = ObservationRegionState.AwaitingHumanCoordinates,
            DrawingHash = DrawingHash
        });
        CadFact wall = CreateFact(CadFactKind.Wall, "71", 0, 0, string.Empty);
        var provider = new FakeProvider(new CadFactSnapshot
        {
            ProviderId = "fixture:gate-isolation",
            IsSuccess = true,
            ReasonCodes = new List<string> { BuildingSemanticReasonCodes.Ok },
            Facts = new List<CadFact> { wall }
        });
        BuildingRecognitionBundle bundle = new BuildingSemanticService(provider).AnalyzeLayers(CreateRequest(profile));

        Assert(bundle.PrimitiveSnapshot.Status == AnalysisRunStatus.Accepted && bundle.PrimitiveSnapshot.Primitives.Count == 1,
            "semantic gate erased or failed the primitive layer");
        Assert(bundle.GeometrySnapshot.Status == AnalysisRunStatus.Accepted && bundle.GeometrySnapshot.Facts.Count == 1,
            "semantic gate erased or failed the geometry layer");
        Assert(bundle.SemanticSnapshot.Status == AnalysisRunStatus.Failed && bundle.SemanticSnapshot.Objects.Count == 0,
            "pending region did not remain isolated to semantic output");
        string html = BuildingSemanticHtmlReport.Build(bundle, profile);
        Assert(html.Contains("L1 图元层") && html.Contains("L2 几何层") && html.Contains("L3 语义层"),
            "HTML hides the independent layer statuses");
        Assert(html.Contains("cad-primitives.v1.json") && html.Contains("building-geometry.v1.json")
               && html.Contains(BuildingSemanticReasonCodes.ObservationRegionNotFrozen),
            "HTML does not expose the reusable layer files or preserve the semantic gate reason");
    }

    private static void TestGeometryAreaMeasurement()
    {
        ProjectProfile profile = CreateProfile();
        CadFact region = CreateFact(CadFactKind.Space, "72", 0, 0, string.Empty);
        region.Geometry.Paths[0] = new List<SemanticPoint>
        {
            new SemanticPoint(0, 0),
            new SemanticPoint(6000, 0),
            new SemanticPoint(6000, 5000),
            new SemanticPoint(0, 5000)
        };
        region.Geometry.Bounds = SemanticGeometryAlgorithms.CalculateBounds(region.Geometry.Paths);
        var provider = new FakeProvider(new CadFactSnapshot
        {
            ProviderId = "fixture:area",
            IsSuccess = true,
            ReasonCodes = new List<string> { BuildingSemanticReasonCodes.Ok },
            Facts = new List<CadFact> { region }
        });
        BuildingRecognitionBundle bundle = new BuildingSemanticService(provider).AnalyzeLayers(CreateRequest(profile));
        GeometryFact geometry = bundle.GeometrySnapshot.Facts.Single(item => item.IsSemanticCandidate);
        Assert(Math.Abs(geometry.Measurements.AreaSquareMillimeters - 30000000.0) < 0.001,
            "closed region area was not 30 square meters in square millimeters");
        Assert(geometry.FeatureKind == GeometryFeatureKind.ClosedRegion, "closed region feature kind missing");
    }

    private static void TestNoncandidateGeometryIsolation()
    {
        ProjectProfile profile = CreateProfile();
        CadFact wall = CreateFact(CadFactKind.Wall, "73", 0, 0, string.Empty);
        CadFact rawSource = CreateFact(CadFactKind.Boundary, "74", 1000, 0, string.Empty);
        CadPrimitive rawPrimitive = CadPrimitiveSnapshotBuilder.FromFact(rawSource);
        rawPrimitive.SourceFactId = string.Empty;
        rawPrimitive.AdapterRoleHint = string.Empty;
        rawPrimitive.IsSemanticCandidate = false;
        var provider = new FakeProvider(new CadFactSnapshot
        {
            ProviderId = "fixture:noncandidate",
            IsSuccess = true,
            ReasonCodes = new List<string> { BuildingSemanticReasonCodes.Ok },
            Primitives = new List<CadPrimitive> { rawPrimitive },
            Facts = new List<CadFact> { wall }
        });
        BuildingRecognitionBundle bundle = new BuildingSemanticService(provider).AnalyzeLayers(CreateRequest(profile));
        Assert(bundle.GeometrySnapshot.Facts.Count == 2, "raw geometric object was not retained in layer two");
        Assert(bundle.SemanticSnapshot.Objects.Count == 1 && bundle.SemanticSnapshot.Objects[0].Source.Handle == "73",
            "noncandidate layer-two geometry leaked into semantic objects");
    }

    private static void TestStandardRoofLinePromotion()
    {
        ProjectProfile profile = CreateProfile();
        profile.Thresholds.AcceptedConfidence = 0.90;
        CadPrimitive openRoof = CreateRawPolylinePrimitive("roof-open", "A-Roof", false);
        CadPrimitive closedRoof = CreateRawPolylinePrimitive("roof-closed", "A-Roof", true);
        CadPrimitive drawingRoof = CreateRawPolylinePrimitive("roof-drawing", "A-Roof-Drng", false);
        CadPrimitive nonPolylineRoof = CreateRawPolylinePrimitive("roof-line", "A-Roof", false);
        nonPolylineRoof.Kind = CadPrimitiveKind.Line;
        nonPolylineRoof.Source.NativeDxfName = "LINE";
        nonPolylineRoof.Source.NativeClassName = "AcDbLine";
        CadPrimitive inexactRoof = CreateRawPolylinePrimitive("roof-inexact", "A-Roof", false);
        inexactRoof.RawGeometry.IsExact = false;

        CadFact wallHole = CreateFact(CadFactKind.Wall, "wall-hole", 2000, 0, WallClassification.Unknown.ToString());
        wallHole.Source.NormalizedLayer = "A-Wall-Hole";
        wallHole.Source.RawLayer = "A-Wall-Hole";
        wallHole.Source.EffectiveLayer = "A-Wall-Hole";
        CadFact wallPattern = CreateFact(CadFactKind.Wall, "wall-pattern", 3000, 0, WallClassification.Unknown.ToString());
        wallPattern.Source.NormalizedLayer = "A-Wall-Patt";
        wallPattern.Source.RawLayer = "A-Wall-Patt";
        wallPattern.Source.EffectiveLayer = "A-Wall-Patt";

        var provider = new FakeProvider(new CadFactSnapshot
        {
            ProviderId = "fixture:roof-line",
            IsSuccess = true,
            ReasonCodes = new List<string> { BuildingSemanticReasonCodes.Ok },
            Primitives = new List<CadPrimitive> { openRoof, closedRoof, drawingRoof, nonPolylineRoof, inexactRoof },
            Facts = new List<CadFact> { wallHole, wallPattern }
        });
        BuildingRecognitionBundle bundle = new BuildingSemanticService(provider).AnalyzeLayers(CreateRequest(profile));

        List<SemanticObject> roofLines = bundle.SemanticSnapshot.Objects
            .Where(item => item.Type == SemanticObjectType.RoofLine)
            .OrderBy(item => item.Source.Handle, StringComparer.Ordinal)
            .ToList();
        Assert(roofLines.Count == 2, "A-Roof exact-layer/polyline gate did not isolate two roof lines");
        Assert(roofLines.All(item => item.Status == DecisionStatus.Review
                                     && item.Classification == "Unclassified"
                                     && item.UseCode == "ROOF_LINE"),
            "roof lines did not remain unclassified Review semantics");
        Assert(roofLines.Single(item => item.Source.Handle == "roof-open").Geometry.IsClosed == false,
            "open A-Roof path lost its open state");
        Assert(roofLines.Single(item => item.Source.Handle == "roof-closed").Geometry.IsClosed,
            "closed A-Roof path lost its closed state");
        Assert(roofLines.All(item => item.Evidence.Any(evidence => evidence.Code == "STANDARD_A_ROOF_POLYLINE")
                                     && !string.IsNullOrWhiteSpace(item.Source.StablePath)),
            "roof line traceability evidence is incomplete");
        Assert(bundle.SemanticSnapshot.Objects.Count(item => item.Type == SemanticObjectType.Wall) == 2,
            "existing A-Wall-Hole/A-Wall-Patt wall semantics changed");
        Assert(bundle.SemanticSnapshot.Objects.All(item => item.Source.Handle != "roof-drawing" && item.Source.Handle != "roof-line"),
            "A-Roof-Drng or non-polyline A-Roof leaked into roof semantics");
        Assert(bundle.SemanticSnapshot.Objects.All(item => item.Source.Handle != "roof-inexact"),
            "inexact A-Roof geometry was promoted into roof semantics");

        profile.Thresholds.AcceptedConfidence = 0.80;
        BuildingRecognitionBundle lowerThresholdBundle = new BuildingSemanticService(provider).AnalyzeLayers(CreateRequest(profile));
        Assert(lowerThresholdBundle.SemanticSnapshot.Objects
                .Where(item => item.Type == SemanticObjectType.RoofLine)
                .All(item => item.Status == DecisionStatus.Review),
            "RoofLine became Accepted below the promotion confidence");
        string roofJson = BuildingSemanticJson.SerializeSnapshot(bundle.SemanticSnapshot);
        Assert(roofJson.Contains("\"type\":\"roof_line\""), "roof line JSON enum is not snake_case");
        Assert(BuildingSemanticJson.DeserializeSnapshot(roofJson).Objects.Count(item => item.Type == SemanticObjectType.RoofLine) == 2,
            "roof line semantic JSON did not roundtrip");
    }

    private static void TestLayeredFacadeCompatibility()
    {
        ProjectProfile profile = CreateProfile();
        var source = new CadFactSnapshot
        {
            ProviderId = "fixture:compatibility",
            IsSuccess = true,
            ReasonCodes = new List<string> { BuildingSemanticReasonCodes.Ok },
            Facts = new List<CadFact> { CreateFact(CadFactKind.Wall, "75", 0, 0, string.Empty) }
        };
        BuildingSemanticSnapshot existing = new BuildingSemanticService(new FakeProvider(source)).Analyze(CreateRequest(profile));
        BuildingRecognitionBundle layered = new BuildingSemanticService(new FakeProvider(source)).AnalyzeLayers(CreateRequest(profile));
        Assert(existing.Objects.Select(item => item.SemanticId).SequenceEqual(layered.SemanticSnapshot.Objects.Select(item => item.SemanticId)),
            "AnalyzeLayers changed existing semantic ids");
        Assert(existing.DeterministicContentHash == layered.SemanticSnapshot.DeterministicContentHash,
            "AnalyzeLayers changed existing semantic payload");
    }

    private static void TestPrimitiveSnapshotImmutability()
    {
        ProjectProfile profile = CreateProfile();
        CadPrimitive primitive = CadPrimitiveSnapshotBuilder.FromFact(CreateFact(CadFactKind.Boundary, "76", 0, 0, string.Empty));
        primitive.IsSemanticCandidate = false;
        primitive.AdapterRoleHint = string.Empty;
        DrawingSnapshot frozen = DrawingSnapshot.Freeze(new CadFactSnapshot
        {
            ProviderId = "fixture:primitive-immutable",
            IsSuccess = true,
            ReasonCodes = new List<string> { BuildingSemanticReasonCodes.Ok },
            Primitives = new List<CadPrimitive> { primitive }
        });
        CadPrimitiveSnapshot beforeMutation = CadPrimitiveSnapshotBuilder.Build(frozen, CreateRequest(profile));
        primitive.Source.RawLayer = "MUTATED";
        primitive.RawGeometry.Paths[0][0].X = 999999;
        CadPrimitiveSnapshot afterMutation = CadPrimitiveSnapshotBuilder.Build(frozen, CreateRequest(profile));
        Assert(afterMutation.Primitives.Single().Source.RawLayer == "A-Test", "primitive source alias leaked into frozen snapshot");
        Assert(afterMutation.Primitives.Single().RawGeometry.Paths[0][0].X == 0, "primitive geometry alias leaked into frozen snapshot");
        Assert(beforeMutation.DeterministicContentHash == afterMutation.DeterministicContentHash,
            "external primitive mutation changed frozen content hash");
    }

    private static void TestNonfiniteGeometryQuarantine()
    {
        CadFact fact = CreateFact(CadFactKind.Wall, "80", 0, 0, string.Empty);
        fact.Geometry.Paths[0].Insert(1, new SemanticPoint(double.NaN, 50));
        BuildingRecognitionBundle bundle = AnalyzeLayers(fact);
        Assert(double.IsNaN(bundle.PrimitiveSnapshot.Primitives.Single().RawGeometry.Paths[0][1].X),
            "L1 did not retain the original invalid coordinate");
        Assert(bundle.GeometrySnapshot.Facts.Single().Geometry.Kind == GeometryKind.None,
            "bad coordinate was silently removed to invent an L2 polygon");
        Assert(bundle.GeometrySnapshot.ReasonCodes.Contains(BuildingSemanticReasonCodes.InvalidGeometry),
            "invalid L2 geometry lacks an explicit reason");
        Assert(bundle.SemanticSnapshot.Objects.Single().Status == DecisionStatus.Rejected,
            "invalid geometry reached an accepted semantic object");
        CadPrimitiveSnapshot replay = BuildingSemanticJson.DeserializePrimitiveSnapshot(
            BuildingSemanticJson.SerializePrimitiveSnapshot(bundle.PrimitiveSnapshot));
        Assert(double.IsNaN(replay.Primitives.Single().RawGeometry.Paths[0][1].X),
            "raw invalid coordinate was lost in JSON replay");
    }

    private static void TestMissingPointQuarantine()
    {
        CadFact fact = CreateFact(CadFactKind.Column, "81", 1000, 1000, string.Empty);
        fact.Geometry.Paths[0].Insert(1, null!);
        BuildingRecognitionBundle bundle = AnalyzeLayers(fact);
        Assert(bundle.PrimitiveSnapshot.Primitives.Single().RawGeometry.Paths[0][1] == null,
            "missing point was changed to a (0,0,0) vertex");
        Assert(bundle.GeometrySnapshot.Facts.Single().ReasonCodes.Contains(BuildingSemanticReasonCodes.InvalidGeometry),
            "missing point was not quarantined");
        Assert(bundle.SemanticSnapshot.Objects.All(item => item.Status != DecisionStatus.Accepted),
            "missing point was accepted");
    }

    private static void TestDegenerateRegionQuarantine()
    {
        CadFact fact = CreateFact(CadFactKind.Space, "82", 0, 0, string.Empty);
        fact.Geometry.Paths[0] = new List<SemanticPoint>
        {
            new SemanticPoint(0, 0), new SemanticPoint(1000, 0), new SemanticPoint(2000, 0)
        };
        BuildingRecognitionBundle bundle = AnalyzeLayers(fact);
        Assert(bundle.GeometrySnapshot.Facts.Single().Geometry.Kind == GeometryKind.None,
            "zero-area closed path remained a region");
        Assert(!bundle.GeometrySnapshot.Facts.Single().Measurements.AreaIsAvailable,
            "invalid region reported a usable area");
        Assert(bundle.SemanticSnapshot.Objects.Single().Status == DecisionStatus.Rejected,
            "degenerate space was not rejected");
    }

    private static void TestMultiLoopAreaUnavailable()
    {
        CadFact fact = CreateFact(CadFactKind.Space, "83", 0, 0, string.Empty);
        fact.Geometry.Paths.Add(new List<SemanticPoint>
        {
            new SemanticPoint(100, 100), new SemanticPoint(200, 100),
            new SemanticPoint(200, 200), new SemanticPoint(100, 200)
        });
        BuildingRecognitionBundle bundle = AnalyzeLayers(fact);
        GeometryFact geometry = bundle.GeometrySnapshot.Facts.Single();
        Assert(!geometry.Measurements.AreaIsAvailable && geometry.Measurements.AreaSquareMillimeters == 0,
            "unresolved loops were summed as if they were a confirmed net area");
        Assert(geometry.ReasonCodes.Contains(BuildingSemanticReasonCodes.GeometryAreaRequiresLoopTopology),
            "unresolved area lacks a reason code");
        Assert(bundle.GeometrySnapshot.Status == AnalysisRunStatus.Review,
            "unresolved loop topology returned green geometry status");
        Assert(bundle.SemanticSnapshot.Objects.Single().Status == DecisionStatus.Review,
            "multi-loop space bypassed review");
    }

    private static void TestNoncandidateInvalidGeometry()
    {
        CadPrimitive primitive = CadPrimitiveSnapshotBuilder.FromFact(
            CreateFact(CadFactKind.Boundary, "84", 0, 0, string.Empty));
        primitive.IsSemanticCandidate = false;
        primitive.AdapterRoleHint = string.Empty;
        primitive.RawGeometry.Paths[0][0].X = double.PositiveInfinity;
        DrawingSnapshot source = DrawingSnapshot.Freeze(new CadFactSnapshot
        {
            ProviderId = "fixture:invalid-noncandidate",
            IsSuccess = true,
            Primitives = new List<CadPrimitive> { primitive }
        });
        CadPrimitiveSnapshot primitives = CadPrimitiveSnapshotBuilder.Build(source, CreateRequest(CreateProfile()));
        BuildingGeometrySnapshot geometry = new BuildingGeometryService().Build(primitives);
        Assert(geometry.Facts.Count == 1 && geometry.Metrics.InvalidGeometryFactCount == 1,
            "invalid noncandidate silently disappeared from layer two");
        Assert(geometry.Status == AnalysisRunStatus.Review, "invalid noncandidate geometry returned green status");
    }

    private static void TestLayeredFacadeCollectsOnce()
    {
        var provider = new FakeProvider(new CadFactSnapshot
        {
            ProviderId = "fixture:single-collect",
            IsSuccess = true,
            Facts = new List<CadFact> { CreateFact(CadFactKind.Wall, "85", 0, 0, string.Empty) }
        }) { CollectDelayMilliseconds = 25 };
        BuildingRecognitionBundle bundle = new BuildingSemanticService(provider).AnalyzeLayers(CreateRequest(CreateProfile()));
        Assert(provider.CollectCount == 1, "AnalyzeLayers re-read the CAD database");
        Assert(bundle.SemanticSnapshot.Metrics.AnalysisElapsedMilliseconds >= 25,
            "reported layered runtime excluded CAD collection time");
    }

    private static void TestLayerJsonRoundtrip()
    {
        BuildingRecognitionBundle bundle = AnalyzeLayers(CreateFact(CadFactKind.Column, "86", 0, 0, string.Empty));
        RecognitionLayerProvenance.Apply(bundle, ProfileHash);
        string primitiveJson = BuildingSemanticJson.SerializePrimitiveSnapshot(bundle.PrimitiveSnapshot);
        string geometryJson = BuildingSemanticJson.SerializeGeometrySnapshot(bundle.GeometrySnapshot);
        Assert(!primitiveJson.Contains("\n") && !primitiveJson.Contains("\r")
               && !geometryJson.Contains("\n") && !geometryJson.Contains("\r"),
            "large layer snapshots were emitted with expensive presentation whitespace");
        CadPrimitiveSnapshot primitives = BuildingSemanticJson.DeserializePrimitiveSnapshot(
            primitiveJson);
        BuildingGeometrySnapshot geometry = BuildingSemanticJson.DeserializeGeometrySnapshot(
            geometryJson);
        Assert(primitives.DeterministicHashAlgorithm == RecognitionLayerDeterminism.CanonicalBinaryV2
               && geometry.DeterministicHashAlgorithm == RecognitionLayerDeterminism.CanonicalBinaryV2,
            "layer snapshots did not declare the canonical binary hash algorithm");
        Assert(primitives.DeterministicContentHash == geometry.SourcePrimitiveContentHash,
            "geometry JSON lost its source primitive hash");
        Assert(geometry.Facts.Single().Measurements.AreaIsAvailable, "valid area flag did not roundtrip");
        geometry.Facts.Single().Measurements.AreaSquareMillimeters += 1;
        bool rejected = false;
        try
        {
            BuildingSemanticJson.DeserializeGeometrySnapshot(BuildingSemanticJson.SerializeGeometrySnapshot(geometry));
        }
        catch (InvalidDataException)
        {
            rejected = true;
        }
        Assert(rejected, "tampered geometry measurements bypassed content-hash validation");
    }

    private static void TestLegacyLayerHashCompatibility()
    {
        BuildingRecognitionBundle bundle = AnalyzeLayers(CreateFact(CadFactKind.Column, "legacy-hash", 0, 0, string.Empty));
        RecognitionLayerProvenance.Apply(bundle, ProfileHash);
        bundle.PrimitiveSnapshot.DeterministicHashAlgorithm = string.Empty;
        bundle.PrimitiveSnapshot.DeterministicContentHash =
            RecognitionLayerDeterminism.ComputeLegacyTextV1(bundle.PrimitiveSnapshot);
        bundle.GeometrySnapshot.DeterministicHashAlgorithm = string.Empty;
        bundle.GeometrySnapshot.SourcePrimitiveContentHash = bundle.PrimitiveSnapshot.DeterministicContentHash;
        bundle.GeometrySnapshot.DeterministicContentHash =
            RecognitionLayerDeterminism.ComputeLegacyTextV1(bundle.GeometrySnapshot);

        string primitiveJson = BuildingSemanticJson.SerializePrimitiveSnapshot(bundle.PrimitiveSnapshot)
            .Replace("\"deterministic_hash_algorithm\":\"\",", string.Empty);
        string geometryJson = BuildingSemanticJson.SerializeGeometrySnapshot(bundle.GeometrySnapshot)
            .Replace("\"deterministic_hash_algorithm\":\"\",", string.Empty);
        CadPrimitiveSnapshot primitives = BuildingSemanticJson.DeserializePrimitiveSnapshot(primitiveJson);
        BuildingGeometrySnapshot geometry = BuildingSemanticJson.DeserializeGeometrySnapshot(geometryJson);
        Assert(string.IsNullOrEmpty(primitives.DeterministicHashAlgorithm)
               && string.IsNullOrEmpty(geometry.DeterministicHashAlgorithm),
            "legacy hash snapshots were silently relabeled as canonical binary v2");
        Assert(primitives.DeterministicContentHash == geometry.SourcePrimitiveContentHash,
            "legacy L1 to L2 hash chain was not preserved");
    }

    private static void TestLayerIntegrityQuarantine()
    {
        BuildingRecognitionBundle bundle = AnalyzeLayers(CreateFact(CadFactKind.Wall, "87", 0, 0, string.Empty));
        RecognitionLayerIntegrityPolicy.Apply(bundle, DrawingHash, ProfileHash, 5, 5, ScanInputMode.DiskSideDatabase, true);
        Assert(bundle.PrimitiveSnapshot.Status == AnalysisRunStatus.Failed
               && bundle.GeometrySnapshot.Status == AnalysisRunStatus.Failed, "source mutation did not quarantine L1/L2");
        Assert(bundle.PrimitiveSnapshot.Primitives.Count == 1 && bundle.GeometrySnapshot.Facts.Count == 1,
            "failed run erased evidence needed for diagnosis");
        Assert(!bundle.PrimitiveSnapshot.ReasonCodes.Contains(BuildingSemanticReasonCodes.Ok)
               && !bundle.GeometrySnapshot.ReasonCodes.Contains(BuildingSemanticReasonCodes.Ok),
            "failed layers retained an OK reason");
        Assert(bundle.PrimitiveSnapshot.DeterministicContentHash == bundle.GeometrySnapshot.SourcePrimitiveContentHash,
            "integrity update broke layer hash chaining");
    }

    private static void TestProducerVersionAlignment()
    {
        BuildingRecognitionBundle bundle = AnalyzeLayers(CreateFact(CadFactKind.Column, "version", 0, 0, string.Empty));
        Assert(BuildingSemanticSchema.ProducerVersion == "0.3.0-dev", "candidate producer version is not 0.3.0-dev");
        Assert(bundle.PrimitiveSnapshot.ProducerVersion == BuildingSemanticSchema.ProducerVersion,
            "primitive producer version drifted");
        Assert(bundle.GeometrySnapshot.ProducerVersion == BuildingSemanticSchema.ProducerVersion,
            "geometry producer version drifted");
        Assert(bundle.SemanticSnapshot.ProducerVersion == BuildingSemanticSchema.ProducerVersion,
            "semantic producer version drifted");
    }

    private static void TestApprovedSemanticOverride()
    {
        CadFact roomFact = CreateFact(CadFactKind.Space, "override-room", 0, 0, string.Empty);
        roomFact.RawLabel = "配电房";
        BuildingSemanticSnapshot raw = Analyze(CreateProfile(), new[] { roomFact });
        raw.ProducerBinarySha256 = new string('C', 64);
        raw.DeterministicContentHash = BuildingSemanticDeterminism.Compute(raw);
        string rawJson = BuildingSemanticJson.SerializeSnapshot(raw);
        SemanticObject target = raw.Objects.Single();
        BuildingSemanticOverrideDocument document = CreateOverride(raw, target);

        SemanticOverrideApplicationResult result = BuildingSemanticOverrideResolver.Apply(raw, document);
        SemanticObject resolved = result.Snapshot.Objects.Single();
        Assert(result.Applied && result.AppliedChangeCount == 1, "approved override was not applied exactly once");
        Assert(BuildingSemanticJson.SerializeSnapshot(raw) == rawJson, "raw L3 snapshot was mutated");
        Assert(resolved.Classification == "ElectricalRoom" && resolved.UseCode == "ELECTRICAL_ROOM",
            "resolved classification/use code mismatch");
        Assert(resolved.Status == DecisionStatus.Review && result.Snapshot.Status == AnalysisRunStatus.Review,
            "human correction must remain Review during pilot");
        Assert(resolved.Evidence.Any(item => item.Code == BuildingSemanticReasonCodes.SemanticOverrideApplied),
            "override provenance was not recorded");
        BuildingSemanticJson.DeserializeSnapshot(BuildingSemanticJson.SerializeSnapshot(result.Snapshot));
    }

    private static void TestSemanticOverrideMismatch()
    {
        BuildingSemanticSnapshot raw = Analyze(CreateProfile(), new[]
        {
            CreateFact(CadFactKind.Wall, "override-mismatch", 0, 0, "Ordinary")
        });
        raw.ProducerBinarySha256 = new string('C', 64);
        raw.DeterministicContentHash = BuildingSemanticDeterminism.Compute(raw);
        BuildingSemanticOverrideDocument document = CreateOverride(raw, raw.Objects.Single());
        document.SourceSemanticsHash = new string('D', 64);
        AssertThrows<InvalidDataException>(() => BuildingSemanticOverrideResolver.Apply(raw, document),
            "stale source semantics hash was accepted");
    }

    private static void TestSemanticOverrideFailClosed()
    {
        BuildingSemanticSnapshot raw = Analyze(CreateProfile(), new[]
        {
            CreateFact(CadFactKind.Wall, "override-failed", 0, 0, "Ordinary")
        });
        Assert(raw.Objects.Single().Status == DecisionStatus.Accepted, "fixture must start Accepted");
        raw.ProducerBinarySha256 = new string('C', 64);
        raw.DeterministicContentHash = BuildingSemanticDeterminism.Compute(raw);
        string rawJson = BuildingSemanticJson.SerializeSnapshot(raw);

        BuildingSemanticSnapshot failed = BuildingSemanticOverrideResolver.FailClosed(raw, "fixture mismatch");
        Assert(failed.Status == AnalysisRunStatus.Failed, "invalid override did not fail closed");
        Assert(failed.Objects.All(item => item.Status != DecisionStatus.Accepted),
            "invalid override retained an Accepted object");
        Assert(failed.Relations.All(item => item.Status != DecisionStatus.Accepted),
            "invalid override retained an Accepted relation");
        Assert(failed.ReasonCodes.Contains(BuildingSemanticReasonCodes.SemanticOverrideInvalid),
            "invalid override reason missing");
        Assert(BuildingSemanticJson.SerializeSnapshot(raw) == rawJson, "fail-closed path mutated raw L3");
        BuildingSemanticJson.DeserializeSnapshot(BuildingSemanticJson.SerializeSnapshot(failed));
    }

    private static BuildingSemanticOverrideDocument CreateOverride(
        BuildingSemanticSnapshot snapshot,
        SemanticObject target)
    {
        return new BuildingSemanticOverrideDocument
        {
            OverrideId = "override-fixture-001",
            Status = "approved",
            DrawingSha256 = snapshot.Drawing.Sha256,
            SourceSemanticsHash = snapshot.DeterministicContentHash,
            SourceProducerVersion = snapshot.ProducerVersion,
            SourceProducerBinarySha256 = snapshot.ProducerBinarySha256,
            ProjectId = snapshot.Profile.ProjectId,
            CreatedAtUtc = "2026-09-14T00:00:00Z",
            CreatedBy = "fixture-author",
            ReviewedAtUtc = "2026-09-14T01:00:00Z",
            ReviewedBy = "fixture-reviewer",
            Reason = "fixture approved correction",
            Changes = new List<BuildingSemanticOverrideChange>
            {
                new BuildingSemanticOverrideChange
                {
                    ChangeId = "change-fixture-001",
                    SemanticId = target.SemanticId,
                    SourceHandle = target.Source.Handle,
                    ExpectedClassification = target.Classification,
                    ExpectedUseCode = target.UseCode,
                    ReplacementClassification = "ElectricalRoom",
                    ReplacementUseCode = "ELECTRICAL_ROOM",
                    Reason = "fixture correction"
                }
            }
        };
    }

    private static BuildingRecognitionBundle AnalyzeLayers(CadFact fact)
    {
        var provider = new FakeProvider(new CadFactSnapshot
        {
            ProviderId = "fixture:layer-validation",
            IsSuccess = true,
            Facts = new List<CadFact> { fact }
        });
        return new BuildingSemanticService(provider).AnalyzeLayers(CreateRequest(CreateProfile()));
    }

    private static BuildingRecognitionBundle AnalyzePrimitives(ProjectProfile profile, IEnumerable<CadPrimitive> primitives)
    {
        var provider = new FakeProvider(new CadFactSnapshot
        {
            ProviderId = "fixture:profile-geometry-semantics",
            IsSuccess = true,
            ReasonCodes = new List<string> { BuildingSemanticReasonCodes.Ok },
            Primitives = primitives.ToList()
        });
        return new BuildingSemanticService(provider).AnalyzeLayers(CreateRequest(profile));
    }

    private static BuildingSemanticSnapshot Analyze(ProjectProfile profile, IEnumerable<CadFact> facts)
    {
        var provider = new FakeProvider(new CadFactSnapshot
        {
            ProviderId = "fixture:readonly",
            IsSuccess = true,
            ReasonCodes = new List<string> { BuildingSemanticReasonCodes.Ok },
            Facts = facts.ToList()
        });
        return new BuildingSemanticService(provider).Analyze(CreateRequest(profile));
    }

    private static AnalysisRequest CreateRequest(ProjectProfile profile)
    {
        return new AnalysisRequest
        {
            Profile = profile,
            ProfileHash = ProfileHash,
            DrawingHash = DrawingHash,
            DrawingId = "fixture",
            DrawingPath = "fixture.dwg",
            SourceFileLength = 1,
            SourceLastWriteUtc = new DateTime(2026, 1, 1, 0, 0, 0, DateTimeKind.Utc)
        };
    }

    private static ProjectProfile CreateProfile()
    {
        return new ProjectProfile
        {
            ProjectId = "fixture",
            ProfileVersion = "1.0.0",
            Units = "mm",
            UnitScaleToMillimeters = 1.0,
            RuleState = SemanticRuleState.Frozen,
            AdapterPriority = new List<string> { "T20", "StandardCad" },
            Drawings = new List<DrawingProfileRule>
            {
                new DrawingProfileRule { DrawingId = "fixture", FileName = "fixture.dwg", Sha256 = DrawingHash }
            },
            Thresholds = new SemanticThresholds()
        };
    }

    private static ObservationRegion FrozenRegion(
        string code,
        ObservationRegionRole role,
        double minX,
        double minY,
        double maxX,
        double maxY)
    {
        return new ObservationRegion
        {
            Code = code,
            Name = code,
            Role = role,
            State = ObservationRegionState.Frozen,
            DrawingHash = DrawingHash,
            PolygonWcsMillimeters = new List<SemanticPoint>
            {
                new SemanticPoint(minX, minY),
                new SemanticPoint(maxX, minY),
                new SemanticPoint(maxX, maxY),
                new SemanticPoint(minX, maxY)
            },
            FrozenBy = "fixture-user",
            FrozenAtUtc = "2026-01-01T00:00:00Z"
        };
    }

    private static CadFact CreateFact(CadFactKind kind, string handle, double x, double y, string classification)
    {
        var geometry = new SemanticGeometry
        {
            Kind = GeometryKind.Polygon,
            IsClosed = true,
            IsExact = true,
            ExtractionMethod = "fixture_exact",
            Paths = new List<List<SemanticPoint>>
            {
                new List<SemanticPoint>
                {
                    new SemanticPoint(x, y),
                    new SemanticPoint(x + 500, y),
                    new SemanticPoint(x + 500, y + 500),
                    new SemanticPoint(x, y + 500)
                }
            }
        };
        geometry.Bounds = SemanticGeometryAlgorithms.CalculateBounds(geometry.Paths);
        var fact = new CadFact
        {
            Kind = kind,
            FactId = "fact_" + handle,
            Confidence = 0.99,
            Source = new SourceReference
            {
                DrawingHash = DrawingHash,
                Handle = handle,
                StablePath = handle,
                RawLayer = "A-Test",
                EffectiveLayer = "A-Test",
                NormalizedLayer = "A-Test",
                NativeDxfName = "FIXTURE",
                NativeClassName = "FixtureEntity"
            },
            Geometry = geometry,
            Evidence = new List<SemanticEvidence>
            {
                new SemanticEvidence
                {
                    Code = "FIXTURE_SOURCE",
                    Kind = "fixture",
                    Value = handle,
                    SourceHandle = handle,
                    Weight = 0.99
                }
            }
        };
        if (kind == CadFactKind.Wall)
            fact.Properties["wall_class"] = classification;
        return fact;
    }

    private static CadPrimitive CreateRawPolylinePrimitive(string handle, string normalizedLayer, bool closed)
    {
        var geometry = new SemanticGeometry
        {
            Kind = closed ? GeometryKind.Polygon : GeometryKind.Polyline,
            IsClosed = closed,
            IsExact = true,
            ExtractionMethod = "fixture_native_polyline",
            Paths = new List<List<SemanticPoint>>
            {
                closed
                    ? new List<SemanticPoint>
                    {
                        new SemanticPoint(0, 0),
                        new SemanticPoint(500, 0),
                        new SemanticPoint(500, 500),
                        new SemanticPoint(0, 500)
                    }
                    : new List<SemanticPoint>
                    {
                        new SemanticPoint(0, 0),
                        new SemanticPoint(500, 250),
                        new SemanticPoint(1000, 0)
                    }
            }
        };
        geometry.Bounds = SemanticGeometryAlgorithms.CalculateBounds(geometry.Paths);
        return new CadPrimitive
        {
            PrimitiveId = "primitive_" + handle,
            Kind = CadPrimitiveKind.Polyline,
            IsSemanticCandidate = false,
            Source = new SourceReference
            {
                DrawingHash = DrawingHash,
                Handle = handle,
                StablePath = "block/" + handle,
                RawLayer = normalizedLayer,
                EffectiveLayer = normalizedLayer,
                NormalizedLayer = normalizedLayer,
                NativeDxfName = "LWPOLYLINE",
                NativeClassName = "AcDbPolyline"
            },
            RawGeometry = geometry,
            ExtractionConfidence = 1.0,
            Evidence = new List<SemanticEvidence>
            {
                new SemanticEvidence
                {
                    Code = "FIXTURE_NATIVE_POLYLINE",
                    Kind = "fixture",
                    Value = normalizedLayer,
                    SourceHandle = handle,
                    Weight = 1.0
                }
            }
        };
    }

    private static GeometrySemanticRule CreateColumnRule()
    {
        return new GeometrySemanticRule
        {
            Id = "fixture-column",
            SemanticType = SemanticObjectType.Column.ToString(),
            NormalizedLayers = new List<string> { "S-COLU" },
            NativeClassNames = new List<string> { "AcDbPolyline" },
            FeatureKinds = new List<GeometryFeatureKind> { GeometryFeatureKind.ClosedRegion },
            RequireClosed = true,
            RequireExact = true,
            MinimumAreaSquareMillimeters = 20000,
            MaximumAreaSquareMillimeters = 2000000,
            Confidence = 0.96,
            LabelMode = GeometrySemanticLabelMode.None
        };
    }

    private static GeometrySemanticRule CreateRoomRule()
    {
        return new GeometrySemanticRule
        {
            Id = "fixture-room",
            SemanticType = SemanticObjectType.Space.ToString(),
            NormalizedLayers = new List<string> { "X-Asst" },
            NativeClassNames = new List<string> { "AcDbPolyline" },
            FeatureKinds = new List<GeometryFeatureKind> { GeometryFeatureKind.ClosedRegion },
            RequireClosed = true,
            RequireExact = true,
            MinimumAreaSquareMillimeters = 2000000,
            MaximumAreaSquareMillimeters = 500000000,
            Confidence = 0.96,
            LabelMode = GeometrySemanticLabelMode.UniqueContainedRoomUseAndArea,
            LabelLayers = new List<string> { "A-Spac-Iden-Auto" },
            AreaLabelLayers = new List<string> { "A-Spac-Area-Auto" },
            MaximumAreaLabelRelativeDifference = 0.03
        };
    }

    private static GeometrySemanticRule CreateWallBoundedRoomRule()
    {
        return new GeometrySemanticRule
        {
            Id = "fixture-wall-bounded-room",
            SemanticType = SemanticObjectType.Space.ToString(),
            NormalizedLayers = new List<string> { "DERIVED-WALL-LOOP" },
            NativeClassNames = new List<string> { "WallBoundedRegion" },
            FeatureKinds = new List<GeometryFeatureKind> { GeometryFeatureKind.ClosedRegion },
            RequiredProperties = new Dictionary<string, string>(StringComparer.Ordinal)
            {
                ["derived_geometry"] = "wall_bounded_region"
            },
            RequireClosed = true,
            RequireExact = false,
            MinimumAreaSquareMillimeters = 2000000,
            MaximumAreaSquareMillimeters = 500000000,
            Confidence = 0.90,
            LabelMode = GeometrySemanticLabelMode.UniqueContainedRoomUse,
            LabelLayers = new List<string> { "A-Spac-Iden-Auto" }
        };
    }

    private static GeometrySemanticRule CreateShearWallRule()
    {
        return new GeometrySemanticRule
        {
            Id = "fixture-shear-wall",
            SemanticType = SemanticObjectType.Wall.ToString(),
            Classification = WallClassification.Shear.ToString(),
            NormalizedLayers = new List<string> { "S-PATT-WALL" },
            NativeClassNames = new List<string> { "AcDbHatch" },
            FeatureKinds = new List<GeometryFeatureKind> { GeometryFeatureKind.ClosedRegion },
            RequiredProperties = new Dictionary<string, string>(StringComparer.Ordinal)
            {
                ["hatch_pattern_name"] = "钢筋混凝土"
            },
            RequireClosed = true,
            RequireExact = true,
            MinimumAreaSquareMillimeters = 10000,
            MaximumAreaSquareMillimeters = 200000000,
            Confidence = 0.96,
            LabelMode = GeometrySemanticLabelMode.None
        };
    }

    private static CadPrimitive CreateNoncandidateRegionPrimitive(
        string handle,
        string layer,
        double width,
        double height)
    {
        CadFact source = CreateFact(CadFactKind.Boundary, handle, 0, 0, string.Empty);
        source.Source.RawLayer = layer;
        source.Source.EffectiveLayer = layer;
        source.Source.NormalizedLayer = layer;
        source.Source.NativeDxfName = "LWPOLYLINE";
        source.Source.NativeClassName = "AcDbPolyline";
        ResizeRectangle(source, width, height);
        CadPrimitive primitive = CadPrimitiveSnapshotBuilder.FromFact(source);
        primitive.SourceFactId = string.Empty;
        primitive.AdapterRoleHint = string.Empty;
        primitive.IsSemanticCandidate = false;
        return primitive;
    }

    private static CadPrimitive CreateTextPrimitive(
        string handle,
        string layer,
        string value,
        double x,
        double y)
    {
        CadFact source = CreateFact(CadFactKind.Text, handle, x, y, string.Empty);
        source.Source.RawLayer = layer;
        source.Source.EffectiveLayer = layer;
        source.Source.NormalizedLayer = layer;
        source.Source.NativeDxfName = "TEXT";
        source.Source.NativeClassName = "AcDbText";
        source.RawLabel = value;
        source.Geometry.Kind = GeometryKind.Point;
        source.Geometry.IsClosed = false;
        source.Geometry.Paths = new List<List<SemanticPoint>>
        {
            new List<SemanticPoint> { new SemanticPoint(x, y) }
        };
        source.Geometry.Bounds = SemanticGeometryAlgorithms.CalculateBounds(source.Geometry.Paths);
        return CadPrimitiveSnapshotBuilder.FromFact(source);
    }

    private static ProjectProfile CreateElectricalShaftProfile()
    {
        ProjectProfile profile = CreateProfile();
        profile.RoomUseDictionary.Add(new RoomUseRule
        {
            UseCode = "ELECTRICAL_SHAFT",
            SemanticType = SemanticObjectType.Shaft.ToString(),
            Keywords = new List<string> { "电井" }
        });
        profile.GeometrySemanticRules.Add(CreateWallBoundedRoomRule());
        return profile;
    }

    private static SemanticObject SingleElectricalShaft(BuildingRecognitionBundle recognized, string caseName)
    {
        List<SemanticObject> shafts = recognized.SemanticSnapshot.Objects
            .Where(item => item.Type == SemanticObjectType.Shaft && item.UseCode == "ELECTRICAL_SHAFT")
            .ToList();
        Assert(shafts.Count == 1, caseName + " expected one electrical shaft but found " + shafts.Count);
        Assert(shafts[0].Status == DecisionStatus.Review,
            caseName + " bypassed the Review gate");
        return shafts[0];
    }

    private static List<SemanticPoint> RectangleCorners(
        double width,
        double height,
        double translateX,
        double translateY,
        double angleDegrees)
    {
        return new List<SemanticPoint>
        {
            TransformPoint(0, 0, translateX, translateY, angleDegrees),
            TransformPoint(width, 0, translateX, translateY, angleDegrees),
            TransformPoint(width, height, translateX, translateY, angleDegrees),
            TransformPoint(0, height, translateX, translateY, angleDegrees)
        };
    }

    private static SemanticPoint TransformPoint(
        double x,
        double y,
        double translateX,
        double translateY,
        double angleDegrees)
    {
        double radians = angleDegrees * Math.PI / 180.0;
        double cosine = Math.Cos(radians);
        double sine = Math.Sin(radians);
        return new SemanticPoint(
            translateX + x * cosine - y * sine,
            translateY + x * sine + y * cosine);
    }

    private static double PolygonArea(SemanticGeometry geometry)
    {
        List<SemanticPoint> path = geometry.Paths.Single();
        double twiceArea = 0;
        for (int index = 0; index < path.Count; index++)
        {
            SemanticPoint current = path[index];
            SemanticPoint next = path[(index + 1) % path.Count];
            twiceArea += current.X * next.Y - next.X * current.Y;
        }
        return Math.Abs(twiceArea) / 2.0;
    }

    private static CadPrimitive CreateWallPathPrimitive(string handle, List<SemanticPoint> path)
    {
        var geometry = new SemanticGeometry
        {
            Kind = GeometryKind.Polygon,
            IsClosed = true,
            IsExact = true,
            ExtractionMethod = "fixture_t20_wall_closed_path",
            Paths = new List<List<SemanticPoint>> { path }
        };
        geometry.Bounds = SemanticGeometryAlgorithms.CalculateBounds(geometry.Paths);
        return new CadPrimitive
        {
            PrimitiveId = "primitive_" + handle,
            Kind = CadPrimitiveKind.NativeObject,
            AdapterRoleHint = CadFactKind.Wall.ToString(),
            IsSemanticCandidate = true,
            Source = new SourceReference
            {
                DrawingHash = DrawingHash,
                Handle = handle,
                StablePath = handle,
                RawLayer = "A-Wall",
                EffectiveLayer = "A-Wall",
                NormalizedLayer = "A-Wall",
                NativeDxfName = "TDbWall",
                NativeClassName = "TDbWall"
            },
            RawGeometry = geometry,
            ExtractionConfidence = 0.99
        };
    }

    private static CadPrimitive CreateWallMultiPathPrimitive(string handle, List<List<SemanticPoint>> paths)
    {
        CadPrimitive primitive = CreateWallPathPrimitive(handle, paths[0]);
        primitive.RawGeometry.Kind = GeometryKind.MultiPath;
        primitive.RawGeometry.IsClosed = false;
        primitive.RawGeometry.Paths = paths;
        primitive.RawGeometry.Bounds = SemanticGeometryAlgorithms.CalculateBounds(paths);
        primitive.RawGeometry.ExtractionMethod = "fixture_t20_wall_multi_path";
        return primitive;
    }

    private static CadPrimitive CreateWallLinePrimitive(
        string handle,
        double startX,
        double startY,
        double endX,
        double endY)
    {
        var geometry = new SemanticGeometry
        {
            Kind = GeometryKind.Polyline,
            IsClosed = false,
            IsExact = true,
            ExtractionMethod = "fixture_t20_wall_edge",
            Paths = new List<List<SemanticPoint>>
            {
                new List<SemanticPoint>
                {
                    new SemanticPoint(startX, startY),
                    new SemanticPoint(endX, endY)
                }
            }
        };
        geometry.Bounds = SemanticGeometryAlgorithms.CalculateBounds(geometry.Paths);
        return new CadPrimitive
        {
            PrimitiveId = "primitive_" + handle,
            Kind = CadPrimitiveKind.NativeObject,
            AdapterRoleHint = CadFactKind.Wall.ToString(),
            IsSemanticCandidate = true,
            Source = new SourceReference
            {
                DrawingHash = DrawingHash,
                Handle = handle,
                StablePath = handle,
                RawLayer = "A-Wall",
                EffectiveLayer = "A-Wall",
                NormalizedLayer = "A-Wall",
                NativeDxfName = "TDbWall",
                NativeClassName = "TDbWall"
            },
            RawGeometry = geometry,
            ExtractionConfidence = 0.99
        };
    }

    private static CadPrimitive CreateConcreteWallBoundaryPrimitive(
        string handle,
        double x,
        double y,
        double width,
        double height)
    {
        CadPrimitive primitive = CreateNoncandidateRegionPrimitive(handle, "S-PATT-WALL", width, height);
        primitive.Source.RawLayer = "S-PATT-WALL";
        primitive.Source.EffectiveLayer = "S-PATT-WALL";
        primitive.Source.NormalizedLayer = "S-PATT-WALL";
        primitive.Source.NativeDxfName = "HATCH";
        primitive.Source.NativeClassName = "AcDbHatch";
        foreach (List<SemanticPoint> path in primitive.RawGeometry.Paths)
        {
            foreach (SemanticPoint point in path)
            {
                point.X += x;
                point.Y += y;
            }
        }
        primitive.RawGeometry.Bounds = SemanticGeometryAlgorithms.CalculateBounds(primitive.RawGeometry.Paths);
        primitive.RawProperties["hatch_pattern_name"] = "钢筋混凝土";
        return primitive;
    }

    private static CadPrimitive CreateOpeningBoundaryPrimitive(
        string handle,
        double startX,
        double startY,
        double endX,
        double endY)
    {
        CadPrimitive primitive = CreateWallLinePrimitive(handle, startX, startY, endX, endY);
        primitive.AdapterRoleHint = CadFactKind.Opening.ToString();
        primitive.Source.RawLayer = "A-Wind";
        primitive.Source.EffectiveLayer = "A-Wind";
        primitive.Source.NormalizedLayer = "A-Wind";
        primitive.Source.NativeDxfName = "TCH_OPENING";
        primitive.Source.NativeClassName = "TDbOpening";
        primitive.RawGeometry.ExtractionMethod = "fixture_t20_opening_exact_edge";
        return primitive;
    }

    private static void ResizeRectangle(CadFact source, double width, double height)
    {
        SemanticPoint origin = source.Geometry.Paths[0][0];
        source.Geometry.Paths[0] = new List<SemanticPoint>
        {
            new SemanticPoint(origin.X, origin.Y),
            new SemanticPoint(origin.X + width, origin.Y),
            new SemanticPoint(origin.X + width, origin.Y + height),
            new SemanticPoint(origin.X, origin.Y + height)
        };
        source.Geometry.Bounds = SemanticGeometryAlgorithms.CalculateBounds(source.Geometry.Paths);
    }

    private static void Assert(bool condition, string message)
    {
        if (!condition)
            throw new InvalidOperationException(message);
    }

    private static void AssertThrows<TException>(Action action, string message)
        where TException : Exception
    {
        try
        {
            action();
        }
        catch (TException)
        {
            return;
        }
        throw new InvalidOperationException(message);
    }

    private sealed class FakeProvider : ICadFactProvider
    {
        private readonly CadFactSnapshot _snapshot;

        public FakeProvider(CadFactSnapshot snapshot)
        {
            _snapshot = snapshot;
        }

        public string ProviderId => _snapshot.ProviderId;

        public int CollectCount { get; private set; }
        public int CollectDelayMilliseconds { get; set; }

        public DrawingSnapshot Collect(CadFactRequest request)
        {
            CollectCount++;
            if (CollectDelayMilliseconds > 0)
                System.Threading.Thread.Sleep(CollectDelayMilliseconds);
            return DrawingSnapshot.Freeze(_snapshot);
        }
    }

    private sealed class FrozenProvider : ICadFactProvider
    {
        private readonly DrawingSnapshot _snapshot;

        public FrozenProvider(DrawingSnapshot snapshot)
        {
            _snapshot = snapshot;
        }

        public string ProviderId => _snapshot.ProviderId;

        public DrawingSnapshot Collect(CadFactRequest request)
        {
            return _snapshot;
        }
    }
}
