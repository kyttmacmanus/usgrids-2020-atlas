"""USGRIDS 2020 Alaska allocation on a discontinuous WGS84 lattice.

The two Aleutian longitude domains are not neighboring columns in a cropped
array. Process whole county/side polygons, accumulate same-side overlaps,
and *place* the nonoverlapping halves. Never join the statewide fishnet.
"""
from __future__ import annotations

import csv
import hashlib
import itertools
import re
from pathlib import Path

import numpy as np

from land_allocation import CELL_DEGREES as CELL, COUNTS, block_id, make_pieces

TOP, LEFT, HEIGHT, WIDTH = 4450, 178, 4872, 86195
GLOBAL_COLS, ROW_OFFSET = 86400, 18720
XMIN, YMAX = -179.2583333335165, 71.45833325213334
SPARSE_CELLS = 18129391
# Scientific footprint fingerprint: little-endian packed presence bits, padded
# at the end of each row, from the historical paired area masks in raster order.
FOOTPRINT = "856b9933cf9134b4ff6edc85f640c09c0dc0aa66a40f4919e246d3eab62595f1"
ABSENT = -9.0e99       # temporary count arrays only; not a valid count
AREAS = ("PIXEL_LAND", "PIXEL_WATER")


def coordinates(pixelids):
    """Decode signed *global* IDs; Python floor division handles negative IDs."""
    ids = np.asarray(pixelids)
    if ids.dtype.kind not in "iu":
        raise ValueError("PIXELID must be integral")
    rows, cols = np.divmod(ids.astype(np.int64), GLOBAL_COLS)
    rows += ROW_OFFSET
    if np.any((rows < TOP) | (rows >= TOP + HEIGHT) | (cols < LEFT) | (cols >= LEFT + WIDTH)):
        raise ValueError("PIXELID outside Alaska crop")
    return rows, cols


def _side(county, xmin, xmax):
    """Assign a whole county block to one side of the longitude representation."""
    if not (-180.0000001 <= xmin <= xmax <= 180.0000001) or xmax-xmin > 180 or xmin < 0 < xmax:
        raise ValueError("A whole block spans the longitude discontinuity")
    if county == "016":
        return "W" if xmax <= 0 else "E"
    if xmax > 0:
        raise ValueError("Unexpected east-domain county outside 016")
    return "ALL"


def _read_canonical(path):
    """Load the official-source 29-column table; preserve 15-digit string IDs."""
    mapping, values = {}, []
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) != ("GEOID", *COUNTS):
            raise ValueError("Expected canonical GEOID plus the 29 ordered count columns")
        for row in reader:
            key = block_id(row["GEOID"], "02")
            if key in mapping or any(not re.fullmatch(r"[0-9]+", row[v] or "") for v in COUNTS):
                raise ValueError("Duplicate GEOID or noninteger canonical count")
            nums = [int(row[v]) for v in COUNTS]
            if max(nums) > 2**53:
                raise ValueError("Canonical count not reliably representable as Float64")
            mapping[key] = len(values)
            values.append(nums)
    if not values:
        raise ValueError("Empty Alaska canonical table")
    return mapping, np.asarray(values, dtype="float64")


def reduction_order(ids):
    """Within each PIXELID keep the stated input order, not a value-based sort."""
    ids = np.asarray(ids, dtype=np.int64)
    if not len(ids):
        return ids.copy(), ids.copy(), ids.copy()
    order = np.argsort(ids, kind="stable")
    sorted_ids = ids[order]
    starts = np.r_[0, np.flatnonzero(np.diff(sorted_ids)) + 1]
    return sorted_ids[starts], order, starts


def weight_plan(pid, block_index, block_land, piece_land):
    """Apply the five-decimal *eligibility* rule; do not round the actual weight."""
    idx = np.asarray(block_index)
    land, piece = np.asarray(block_land, dtype="float64"), np.asarray(piece_land, dtype="float64")
    pid = np.asarray(pid)
    if len({a.shape for a in (pid, idx, land, piece)}) != 1 or idx.ndim != 1 or idx.dtype.kind not in "iu" or np.any(idx < 0):
        raise ValueError("Misaligned inputs or unmatched block")
    coordinates(pid)
    valid = np.isfinite(land) & (land > 0) & np.isfinite(piece) & (np.round(piece, 5) > 0)
    pixels, order, starts = reduction_order(pid[valid])
    return pixels, idx[valid][order], (piece[valid] / land[valid])[order], starts


def sum_counts(plan, canonical, left, right):
    """Count times Float64 weight, then Float64 SUM in stable source-row order."""
    _, idx, weight, starts = plan
    if not len(starts):
        return np.empty((0, right-left), dtype="float64")
    return np.add.reduceat(canonical[idx, left:right] * weight[:, None], starts, axis=0)


def _check_spatial_grid(w, h, west, north, dx, dy, epsg):
    """Reject a changed crop, datum, spacing or corner; allow serialization noise."""
    if (w, h, epsg) != (WIDTH, HEIGHT, 4326) or not np.allclose(
        [west, north, dx, dy], [XMIN, YMAX, CELL, CELL], atol=[1e-9, 1e-9, 2e-14, 2e-14], rtol=0
    ):
        raise ValueError("Input does not match the frozen single-band Alaska WGS84 lattice")


def _check_raster(a, src):
    """Open and validate the reference lattice using ArcGIS raster metadata."""
    r = a.Raster(str(src))
    _check_spatial_grid(r.width, r.height, r.extent.XMin, r.extent.YMax,
                        r.meanCellWidth, r.meanCellHeight, r.spatialReference.factoryCode)
    if r.bandCount != 1:
        raise ValueError("Expected one band")
    return r


def _check_product(a, dst):
    """Require a native Float64 product with the published NoData convention."""
    raster = _check_raster(a, dst)
    if raster.pixelType != "F64" or raster.noDataValue is None or float(raster.noDataValue) != 1.79e308:
        raise ValueError("Unexpected Alaska output precision or NoData value")


def _mask_grid(land_mask, water_mask, dst):
    """Generate ID geometry input, never copy the scientific reference values."""
    import rasterio
    from rasterio.windows import Window

    digest, cells = hashlib.sha256(), 0
    sentinel = np.iinfo(np.int32).min
    with rasterio.open(land_mask) as land, rasterio.open(water_mask) as water:
        t = land.transform
        _check_spatial_grid(land.width, land.height, t.c, t.f, t.a, -t.e, land.crs.to_epsg())
        if (t.b or t.d or land.count != 1 or water.count != 1 or water.crs != land.crs or
                water.shape != land.shape or water.transform != t):
            raise ValueError("Alaska area-mask lattices disagree")
        with rasterio.open(dst, "w", driver="GTiff", width=WIDTH, height=HEIGHT, count=1,
                           crs=land.crs, transform=t, dtype="int32", nodata=sentinel,
                           compress="deflate", predictor=2, tiled=True, blockxsize=256,
                           blockysize=128, BIGTIFF="YES") as out:
            cols = np.arange(LEFT, LEFT+WIDTH, dtype=np.int64)
            for start in range(0, HEIGHT, 32):
                n = min(32, HEIGHT-start)
                win = Window(0, start, WIDTH, n)
                keep = land.read_masks(1, window=win) != 0
                if not np.array_equal(keep, water.read_masks(1, window=win) != 0):
                    raise ValueError("Historical land and water footprints differ")
                digest.update(np.packbits(keep, axis=1, bitorder="little").tobytes())
                cells += int(keep.sum())
                rows = np.arange(TOP+start, TOP+start+n, dtype=np.int64)
                p = (rows[:, None] - ROW_OFFSET) * GLOBAL_COLS + cols
                out.write(np.where(keep, p, sentinel).astype(np.int32), 1, window=win)
    if cells != SPARSE_CELLS or digest.hexdigest() != FOOTPRINT:
        raise ValueError("Unexpected Alaska sparse footprint; do not substitute a different area mask")


def _record_cells(bits, ids):
    """Record possibly overlapping cells without losing writes to the same byte."""
    rows, cols = coordinates(ids)
    r, c = rows-TOP, cols-LEFT
    np.bitwise_or.at(bits, (r, c//8), (1 << (c % 8)).astype("uint8"))


def _sparse_fish(a, src, kind, water_mask, db, work):
    """Accept or build sparse polygons, then validate every cell's identity."""
    if kind == "polygons":
        fish = str(src)
    else:
        ids = str(src)
        if kind == "paired_area_masks":
            ids = str(work/"signed_cells.tif")
            _mask_grid(src, water_mask, ids)
        r = _check_raster(a, ids)
        if r.pixelType != "S32":
            raise ValueError("Signed PIXELID raster must be Int32")
        fish = str(db/"sparse_fish")
        a.conversion.RasterToPolygon(ids, fish, "NO_SIMPLIFY", "VALUE", "SINGLE_OUTER_PART")
        fields = {f.name.upper(): f.name for f in a.ListFields(fish)}
        value = next((fields[k] for k in ("GRIDCODE","GRID_CODE","VALUE") if k in fields), None)
        if value is None:
            raise ValueError("No source ID on raster-derived fishnet")
        a.management.AddField(fish, "PIXELID", "LONG")
        a.management.CalculateField(fish, "PIXELID", f"!{value}!", "PYTHON3")
        a.management.DeleteField(fish, ["PIXELID"], "KEEP_FIELDS")
        a.management.AddIndex(fish, "PIXELID", "ix_ak_id")
    if a.Describe(fish).shapeType != "Polygon" or a.Describe(fish).spatialReference.factoryCode != 4326:
        raise ValueError("Expected a WGS84 sparse polygon fishnet")
    if int(a.management.GetCount(fish)[0]) != SPARSE_CELLS:
        raise ValueError("Unexpected number of Alaska fishnet cells")
    # 53 MB bitset checks the exact footprint without sorting millions of
    # geometries; count plus coverage also rejects duplicated IDs.
    bits = np.zeros((HEIGHT, (WIDTH+7)//8), dtype=np.uint8)
    with a.da.SearchCursor(fish, ["PIXELID", "SHAPE@XY", "SHAPE@AREA", "SHAPE@LENGTH"]) as cursor:
        while batch := list(itertools.islice(cursor, 32768)):
            ids, centers, areas, lengths = zip(*batch)
            rows, cols = coordinates(ids)
            xy = np.asarray(centers, dtype="float64")
            if not (np.allclose(xy[:, 0], XMIN+(cols-LEFT+.5)*CELL, atol=CELL*1e-4, rtol=0) and
                    np.allclose(xy[:, 1], YMAX-(rows-TOP+.5)*CELL, atol=CELL*1e-4, rtol=0) and
                    np.allclose(areas, CELL*CELL, atol=0, rtol=1e-5) and
                    np.allclose(lengths, 4*CELL, atol=0, rtol=1e-5)):
                raise ValueError("Geometry center or cell size disagrees with its signed global PIXELID")
            _record_cells(bits, ids)
    if hashlib.sha256(bits).hexdigest() != FOOTPRINT:
        raise ValueError("Alaska fishnet does not match the historical sparse footprint")
    return fish


def _part(a, part, block_fc, water, fishnet, geoid_field, mapping, counts, work, reference, seen):
    """All destructive operations below target only this invocation's new scratch data."""
    folder = work/part
    folder.mkdir()
    db = Path(str(a.management.CreateFileGDB(str(folder), "part.gdb")[0]))
    fc = lambda name: str(db/name)
    fish = fc("fish")
    layer = a.management.MakeFeatureLayer(fishnet, "local_fish_"+part)[0]
    a.management.SelectLayerByLocation(layer, "INTERSECT", block_fc)
    if any(code in a.GetMessages() for code in ("000594", "000595")):
        raise ValueError("An omitted geometry invalidated the county fishnet selection")
    a.management.CopyFeatures(layer, fish)
    a.management.Delete(layer)
    a.management.DeleteField(fish, ["PIXELID"], "KEEP_FIELDS")
    pieces = make_pieces(a, block_fc, fish, water, geoid_field, fc, "ak")
    stats = fc("area_stats")
    a.analysis.Statistics(pieces, stats, [["UG_PLAND", "SUM"], ["UG_PWATER", "SUM"]], "PIXELID")
    fields = ["SUM_UG_PLAND", "SUM_UG_PWATER"]
    areaids = a.da.TableToNumPyArray(stats, ["PIXELID"])["PIXELID"]
    _, cols = coordinates(areaids)
    if not len(cols) or np.any((cols >= GLOBAL_COLS//2) != (part == "016_E")):
        raise ValueError("Unexpected area PIXELID longitude domain")
    _record_cells(seen, areaids)
    a.management.JoinField(fish, "PIXELID", stats, "PIXELID", fields)
    for var, field in zip(AREAS, fields):
        raw = str(folder/(var+"_raw.tif"))
        with a.EnvManager(snapRaster=str(reference), extent=fish, cellSize=CELL):
            a.conversion.PolygonToRaster(fish, field, raw, "CELL_CENTER", "", CELL)
        a.management.CopyRaster(raw, str(folder/(var+".tif")), pixel_type="64_BIT")
        a.management.Delete(raw)
    # ArcGIS table storage order (= ObjectID order for this derived feature
    # class) is preserved explicitly before the stable per-PIXELID SUM.
    oid = a.Describe(pieces).OIDFieldName
    cols = [oid, geoid_field, "PIXELID", "UG_LAND", "UG_PLAND"]
    tab = a.da.TableToNumPyArray(pieces, cols)
    tab = tab[np.argsort(tab[oid], kind="stable")]
    index = np.fromiter((mapping[block_id(v, "02")] for v in tab[geoid_field]), dtype=np.int32, count=len(tab))
    plan = weight_plan(tab["PIXELID"], index, tab["UG_LAND"], tab["UG_PLAND"])
    np.save(folder/"pixels.npy", plan[0], allow_pickle=False)
    for j in range(0, len(COUNTS), 6):
        # Bound the working set. Each persistent vector is one variable in one
        # county/side. No rasterized area value is used as a count weight.
        chunk = sum_counts(plan, counts, j, min(j+6, len(COUNTS)))
        for k in range(chunk.shape[1]):
            np.save(folder/(COUNTS[j+k]+".npy"), chunk[:, k], allow_pickle=False)
    a.management.Delete(str(db))
    return folder


def _array_raster(a, arr, west, south, width, height, dst, missing):
    """Write Float64 values on their explicit lower-left corner, without snapping."""
    with a.EnvManager(snapRaster=None, extent=None, cellSize=None):
        a.NumPyArrayToRaster(arr, a.Point(west, south), width, height, missing).save(str(dst))
        a.management.DefineProjection(str(dst), a.SpatialReference(4326))


def _orientation(a, work):
    """Verify row orientation and the distinction between zero and missing."""
    p = work/"order_fixture.tif"
    original = np.array([[1.25, 0.0, ABSENT], [2.5, -0.0, 7.75]], dtype=np.float64)
    _array_raster(a, original, -10, 60, CELL, CELL, p, ABSENT)
    result = a.RasterToNumPyArray(str(p), nodata_to_value=ABSENT)
    if np.array_equal(result, original):
        return False
    if np.array_equal(result, np.flipud(original)):
        return True
    raise ValueError("Count array row orientation or valid-zero encoding could not be established")


def _mosaic(a, rasters, dst, method, reference):
    """SUM only within a longitude domain; FIRST only between disjoint domains."""
    with a.EnvManager(snapRaster=str(reference), cellSize=CELL, resamplingMethod="NEAREST"):
        a.management.MosaicToNewRaster([str(p) for p in rasters], str(dst.parent), dst.name,
                                       a.SpatialReference(4326), "64_BIT", CELL, 1, method, "FIRST")


def _anchors(a, ref, work):
    """Pin the corners of the geographic crop without introducing observations."""
    dx, dy = ref.meanCellWidth, ref.meanCellHeight
    pads = []
    for name, x, y in (("NW", ref.extent.XMin, ref.extent.YMax-3*dy),
                       ("SE", ref.extent.XMax-3*dx, ref.extent.YMin)):
        p = work/(name+"_pad.tif")
        _array_raster(a, np.full((3, 3), ABSENT, dtype=np.float64), x, y, dx, dy, p, ABSENT)
        pads.append(p)
    return pads


def _domain_plan(files, east):
    """Compute one reusable pixel grouping and minimal rectangle for a hemisphere."""
    segments = [np.load(f/"pixels.npy", mmap_mode="r", allow_pickle=False) for f in files]
    pixels, order, starts = reduction_order(np.concatenate(segments))
    if not len(pixels):
        raise ValueError("Missing count domain")
    rows, cols = coordinates(pixels)
    if np.any((cols >= GLOBAL_COLS//2) != east):
        raise ValueError("Overlapping or swapped longitude domains")
    t, l = int(rows.min()), int(cols.min())
    shape = (int(rows.max())-t+1, int(cols.max())-l+1)
    return (files, order, starts, rows-t, cols-l, t, l, shape)


def _count_raster(a, plan, var, ref, flip, path):
    """Accumulate a single count within one domain and place it on the native lattice."""
    files, order, starts, rr, cc, t, l, shape = plan
    # The second SUM reduces shared PIXELIDs in fixed county order. Numeric
    # zeros participate; absent cells from another part are not zero-filled.
    vals = np.concatenate([np.load(f/(var+".npy"), mmap_mode="r", allow_pickle=False) for f in files])
    values = np.add.reduceat(vals[order], starts)
    if not np.isfinite(values).all() or np.any(values < 0):
        raise ValueError("Nonfinite or negative allocated counts")
    arr = np.full(shape, ABSENT, dtype="float64")
    arr[shape[0]-1-rr if flip else rr, cc] = values
    # The historical affine differs in its last digits from the ideal world
    # lattice. Use the actual affine for placement, the signed ID for indexing.
    dx, dy = ref.meanCellWidth, ref.meanCellHeight
    west = ref.extent.XMin+(l-LEFT)*dx
    south = ref.extent.YMax-(t-TOP+shape[0])*dy
    _array_raster(a, arr, west, south, dx, dy, path, ABSENT)


def _assemble(a, parts, reference, out, work):
    """Combine area partitions and count vectors without summing across the dateline."""
    ref = _check_raster(a, reference)
    pads = _anchors(a, ref, work)
    east = [p for p in parts if p.name == "016_E"]
    west = [p for p in parts if p.name != "016_E"]
    if len(east) != 1 or len(west) != 30:
        raise ValueError("Two-domain Alaska representation requires 31 county/side partitions")
    products = {}
    for var in AREAS:
        first = west[0]/(var+".tif")
        acc = first
        for i, part in enumerate(west[1:], 1):
            nxt = work/(var+"_sum_"+str(i)+".tif")
            _mosaic(a, [acc, part/(var+".tif")], nxt, "SUM", reference)
            if acc != first:
                a.management.Delete(str(acc))  # only a superseded, run-owned sum
            acc = nxt
        dst = out/("usaAK_"+var+".tif")
        _mosaic(a, [acc, east[0]/(var+".tif"), *pads], dst, "FIRST", reference)
        _check_product(a, dst)
        products[var] = str(dst)
        a.management.Delete(str(acc))
    flip = _orientation(a, work)
    domains = [("W", _domain_plan(west, False)), ("E", _domain_plan(east, True))]
    for var in COUNTS:
        local = []
        for name, plan in domains:
            p = work/(name+"_"+var+".tif")
            _count_raster(a, plan, var, ref, flip, p)
            local.append(p)
        dst = out/("usaAK_"+var+"_CNT.tif")
        _mosaic(a, [*local, *pads], dst, "FIRST", reference)
        _check_product(a, dst)
        products[var] = str(dst)
        for p in local:
            a.management.Delete(str(p))
    return products


def allocate_geography(state, counts_csv, blocks, water, fishnet, geoid_field, outdir, *,
                       county_field="COUNTYFP20", fishnet_kind="polygons", grid_reference=None,
                       water_mask=None):
    """Produce the 29 Alaska count and two area TIFFs in a *new* directory.

    grid_reference supplies a coordinate lattice, not allocation values. See
    ALASKA.md for three supported ways of specifying the sparse support. Crash
    intermediates remain available; a later invocation never overwrites them.
    """
    if state != "02" or fishnet_kind not in ("polygons", "pixelid_raster", "paired_area_masks"):
        raise ValueError("Expected the Alaska state FIPS and an explicit supported fishnet type")
    if bool(water_mask) != (fishnet_kind == "paired_area_masks"):
        raise ValueError("Exactly the paired area-mask mode requires water_mask")
    reference = grid_reference or (fishnet if fishnet_kind == "paired_area_masks" else None)
    if not reference:
        raise ValueError("Supply a historical Alaska snap grid")
    import arcpy as a    # Pure allocation and lattice helpers do not require ArcGIS.
    from tempfile import mkdtemp
    import shutil

    mapping, counts = _read_canonical(counts_csv)
    for source in (blocks, water):
        desc = a.Describe(str(source))
        if desc.shapeType != "Polygon" or desc.spatialReference.factoryCode != 4326:
            raise ValueError("Expected WGS84 Alaska block geometry and prepared state water polygons")
    _check_raster(a, reference)
    field = next((f for f in a.ListFields(str(blocks)) if f.name.casefold()==county_field.casefold()), None)
    if not field:
        raise ValueError("Missing Census county field")
    county_field = field.name
    # Verify the actual selected block set, geometry side and county mapping
    # before starting any statewide raster work. Preserve ID leading zeros.
    sides, seen_ids, literals = set(), set(), {}
    with a.da.SearchCursor(str(blocks), [county_field, geoid_field, "SHAPE@"]) as cur:
        for code, val, geom in cur:
            key = block_id(val, state)
            if code is None or not re.fullmatch(r"[0-9]{1,3}", str(code)):
                raise ValueError("Missing or malformed county")
            county = str(code).zfill(3)
            if key in seen_ids or county != key[2:5] or key not in mapping or geom is None:
                raise ValueError("Block identity, county, or geometry does not match canonical counts")
            if county in literals and code != literals[county]:
                raise ValueError("Inconsistent representation of county codes")
            seen_ids.add(key)
            literals[county] = code
            sides.add((county, _side(county, geom.extent.XMin, geom.extent.XMax)))
    if set(mapping) != seen_ids or len(sides)!=31 or len(literals)!=30 or not {("016","E"),("016","W")} <= sides:
        raise ValueError("Alaska canonical and partition coverage requirements were not met")
    out = Path(outdir).resolve()
    for name in (counts_csv, blocks, water, fishnet, reference, water_mask):
        if name is None:
            continue
        src = Path(name).resolve()
        if out == src or out in src.parents or src in out.parents or any(
            p.suffix.casefold() == ".gdb" for p in (out, *out.parents)
        ):
            raise ValueError("Output must be separate from scientific inputs and geodatabases")
    out.mkdir(parents=False, exist_ok=False)
    work = Path(mkdtemp(dir=out, prefix="ak_intermediate_"))
    db = Path(str(a.management.CreateFileGDB(str(work), "geometry.gdb")[0]))
    parts = []
    coverage = np.zeros((HEIGHT, (WIDTH+7)//8), dtype=np.uint8)
    with a.EnvManager(workspace=str(db), scratchWorkspace=str(db), overwriteOutput=False,
                      extent=None, mask=None, snapRaster=None, outputCoordinateSystem=a.SpatialReference(4326),
                      XYTolerance=None, XYResolution=None, cellSize=None,
                      parallelProcessingFactor="0", compression="LZW"):
        fish = _sparse_fish(a, fishnet, fishnet_kind, water_mask, db, work)
        for county, side in sorted(sides):
            part = county+"_"+side
            county_fc = str(db/("county_"+part))
            col = a.AddFieldDelimiters(str(blocks), county_field)
            raw = literals[county]
            literal = f"'{raw}'" if field.type == "String" else str(int(raw))
            a.analysis.Select(str(blocks), county_fc, f"{col} = {literal}")
            local = county_fc
            if side != "ALL":
                a.management.AddField(county_fc, "UG_SIDE", "TEXT", field_length=1)
                with a.da.UpdateCursor(county_fc, ["SHAPE@", "UG_SIDE"]) as cur:
                    for row in cur:
                        row[1] = _side(county, row[0].extent.XMin, row[0].extent.XMax)
                        cur.updateRow(row)
                local = str(db/("side_"+part))
                col = a.AddFieldDelimiters(county_fc, "UG_SIDE")
                a.analysis.Select(county_fc, local, f"{col} = '{side}'")
            parts.append(_part(a, part, local, str(water), fish, geoid_field, mapping,
                               counts, work, reference, coverage))
            if local != county_fc:
                a.management.Delete(local)
            a.management.Delete(county_fc)
        if hashlib.sha256(coverage).hexdigest() != FOOTPRINT:
            raise ValueError("Area intersection coverage does not equal the sparse fishnet")
        products = _assemble(a, parts, reference, out, work)
    # All spatial/table inputs are outside this invocation's unique temporary
    # directory. Refuse any recursive cleanup unless that ownership is intact.
    a.management.ClearWorkspaceCache(str(db))
    if work.resolve().parent != out or not work.name.startswith("ak_intermediate_"):
        raise RuntimeError("Unexpected intermediate directory")
    shutil.rmtree(work)
    return products
