"""Single-geography allocation using the USGRIDS land basis.

Input geometry must be the intended historical block geometry, PIXELID fishnet,
and already-prepared state water layer. See README for prerequisites and limits.
ArcPy is imported only by the spatial entry point: unit tests can exercise the
canonical-count join and eligibility arithmetic without starting ArcGIS.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import math
import re
from pathlib import Path
from uuid import uuid4


COUNTS = tuple(("TOTALPOP AUND1 A1TO4 A5TO17 A18TO24 AUND25 A25OV A25TO64 "
                "A65TO79 A80OV WOMCHILD WHITE BLACK AMIND ASIAN HAWPI OTHER "
                "TWOMORE NHISP HISP NHISPWHITE NHISPBLACK HOUSEHOLD HHPOP "
                "HHUNIT OCC OWN VACANT HU1P").split())
CELL_DEGREES = 0.00416666665


def block_id(value, state):
    """Recognize known ID forms; preserve leading zeroes, never guess missing digits."""
    m = re.fullmatch(r"(?:USA_|1000000US)?([0-9]{15})", str(value))
    if not m or m[1][:2] != state:
        raise ValueError(f"Not a Census block in FIPS {state}: {value!r}")
    return m[1]


def read_counts(path, state, variable):
    """Canonical master supplies integer counts, not a density or a floating raster."""
    if variable not in COUNTS:
        raise ValueError("An explicit canonical count variable is required")
    counts = {}
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not {"GEOID", variable}.issubset(reader.fieldnames or []):
            raise ValueError(f"CSV must contain GEOID and {variable}")
        for row in reader:
            key = block_id(row["GEOID"], state)
            if key in counts or not re.fullmatch(r"[0-9]+", row[variable] or ""):
                raise ValueError(f"Duplicate ID or non-integer count: {key}")
            counts[key] = int(row[variable])
    if not counts:
        raise ValueError("Empty canonical count file")
    return counts


def land_area(area, water):
    """Areas are geodesic km²; absence of a clipped water polygon means no water."""
    if not math.isfinite(area) or area < 0 or (
        water is not None and (not math.isfinite(water) or water < 0)
    ):
        raise ValueError("Invalid area")
    # Overlay/precision differences can leave a very small negative residual.
    return max(area - (0.0 if water is None else water), 0.0)


def contribution(count, block_land, intersection_land):
    """Return count allocated to one eligible block–cell piece, or None (NoData)."""
    if count < 0 or not all(math.isfinite(x) and x >= 0 for x in [count, block_land, intersection_land]):
        raise ValueError("Invalid count or land basis")
    # Round only to decide eligibility, not to calculate mass. A valid zero count
    # stays numeric zero. Never redistribute excluded mass to another pixel.
    if block_land <= 0 or round(intersection_land, 5) <= 0:
        return None
    return (count / block_land) * intersection_land


def calculate_area(arcpy, feature, field, precision):
    """Materialize geodesic square kilometres in the requested ArcGIS field type."""
    arcpy.management.AddField(feature, field, precision)
    with arcpy.da.UpdateCursor(feature, ["SHAPE@", field]) as cursor:
        for row in cursor:
            row[1] = row[0].getArea("GEODESIC", "SquareKilometers")
            cursor.updateRow(row)


def subtract_water(arcpy, feature, water, clipped, idfield, total, wet, dry, wet_precision):
    """Clip the source polygons by the water layer; carry clipped area back by ID.

    The original calculation joined on a temporary polygon identifier. Refuse
    a non-unique join rather than silently picking an arbitrary water fragment.
    Dissolving or independently recomputing a substitute water layer is not
    equivalent to supplying the required upstream input.
    """
    arcpy.management.AddField(feature, idfield, "LONG")
    oid = arcpy.Describe(feature).OIDFieldName
    arcpy.management.CalculateField(feature, idfield, f"!{oid}!", "PYTHON3")
    calculate_area(arcpy, feature, total, "DOUBLE")
    arcpy.analysis.Clip(feature, water, clipped)
    calculate_area(arcpy, clipped, wet, wet_precision)
    seen = set()
    with arcpy.da.SearchCursor(clipped, [idfield]) as cursor:
        for (ident,) in cursor:
            if ident is None or ident in seen:
                raise ValueError(f"Nonunique/missing water-overlay ID in {idfield}")
            seen.add(ident)
    arcpy.management.JoinField(feature, idfield, clipped, idfield, [wet])
    arcpy.management.AddField(feature, dry, "DOUBLE")
    with arcpy.da.UpdateCursor(feature, [total, wet, dry]) as cursor:
        for row in cursor:
            # The released area surfaces distinguish zero water on a valid
            # intersection from NoData outside overlay coverage.
            row[1] = 0.0 if row[1] is None else row[1]
            row[2] = land_area(row[0], row[1])
            cursor.updateRow(row)


def prepare_water(arcpy, blocks, mode, sources, folder, *, state=None):
    """Turn a supplied TIGER 2022 area-water source into state-clipped geometry.

    Input order is material to the nationwide Merge. A state-only assembly
    can omit water crossing state boundaries; do not infer inputs from filenames.
    """
    if mode not in {"prepared", "nationwide", "ordered_components"}:
        raise ValueError(f"Unknown water input mode: {mode}")
    if not sources or (mode != "ordered_components" and len(sources) != 1):
        raise ValueError("Expected one prepared/nationwide layer or an ordered list of component layers")
    for src in sources:
        if arcpy.Describe(src).shapeType != "Polygon":
            raise ValueError("Area water must be polygon geometry")
    if mode == "prepared":
        if state == "10" and int(arcpy.management.GetCount(sources[0])[0]) != 1473:
            raise ValueError("Historical Delaware state water must contain 1,473 features")
        return str(sources[0])
    folder.mkdir(exist_ok=False)
    merged = sources[0]
    if mode == "ordered_components":
        # Production materialized the merged nationwide Shapefile before Clip.
        validate_water_order(sources)
        merged = str(folder / "nationwide.shp")
        building = str(folder / "water_merged.shp")
        arcpy.management.Merge(sources, building)
        arcpy.management.CopyFeatures(building, merged)
    # This target is the 2022 nationwide input, even when allocating a single
    # jurisdiction. A state-only subset would miss water across its borders.
    if int(arcpy.management.GetCount(merged)[0]) != 2256266:
        raise ValueError("Nationwide 2022 water layer must have 2,256,266 source features")
    statewater = str(folder / "state_water.shp")
    with arcpy.EnvManager(outputCoordinateSystem=arcpy.SpatialReference(4326)):
        # The INPUT is the block features; the water features provide the clip.
        # Delaware's source was clipped straight to its Shapefile; the other
        # states copied a memory Clip to Shapefile. Keep that storage boundary.
        if state == "10":
            arcpy.analysis.Clip(blocks, merged, statewater)
        else:
            temporary = "memory\\ugsw_" + uuid4().hex
            try:
                arcpy.analysis.Clip(blocks, merged, temporary)
                arcpy.management.CopyFeatures(temporary, statewater)
            finally:
                if arcpy.Exists(temporary):
                    arcpy.management.Delete(temporary)
    water_features=int(arcpy.management.GetCount(statewater)[0])
    if water_features == 0 or state == "10" and water_features != 1473:
        raise ValueError(f"Unexpected state-block water clip feature count: {water_features}")
    return statewater


def validate_water_order(sources):
    """Require the original order as well as the complete national water footprint."""
    from water_catalog import COUNTY, ID_SET
    matches=[COUNTY.fullmatch(Path(p).name) for p in sources]
    ids=[m[1] for m in matches if m]
    fingerprint=hashlib.sha256(("\n".join(ids)+"\n").encode("ascii")).hexdigest()
    if len(ids)!=3222 or len(matches)!=len(ids) or fingerprint!=ID_SET:
        raise ValueError("Supply the exact 3,222 nationwide components in order; see water_catalog.py")


def make_pieces(arcpy, blocks, fishnet, water, geoid_field, fc, tag):
    """Build one original-method overlay in memory; persist the finished pieces to GDB."""
    prefix = "memory\\ug_" + uuid4().hex + "_"
    b, wet, wc, pieces, iw = [prefix + key for key in ("b", "w", "wc", "p", "iw")]
    result = fc("pieces_" + tag)
    try:
        arcpy.management.CopyFeatures(blocks, b)
        arcpy.management.CopyFeatures(water, wet)
        # Block water uses single precision when materialized; intersection water
        # uses double. Do not replace these two measurements with TIGER ALAND.
        subtract_water(arcpy, b, wet, wc, "UG_ID", "UG_AREA", "UG_WATER", "UG_LAND", "FLOAT")
        arcpy.management.DeleteField(b, [geoid_field, "UG_LAND"], "KEEP_FIELDS")
        arcpy.analysis.Intersect([b, fishnet], pieces, "NO_FID")  # no input rank overrides
        subtract_water(arcpy, pieces, wet, iw, "UG_IID", "UG_PAREA", "UG_PWATER", "UG_PLAND", "DOUBLE")
        arcpy.management.DeleteField(pieces, [geoid_field,"PIXELID","UG_LAND","UG_PLAND","UG_PWATER"], "KEEP_FIELDS")
        arcpy.management.CopyFeatures(pieces, result)
        return result
    finally:
        # Never use Delete('memory'): an embedding process may own other layers.
        for created in (iw, pieces, wc, wet, b):
            if arcpy.Exists(created):
                arcpy.management.Delete(created)


def geometry_basis(arcpy, blocks, fishnet, water, geoid_field, fc, county_field):
    """Partition by original county when configured, then aggregate by common PIXELID.

    A county slice selects whole polygons without cutting the fishnet at the
    county boundary. Appending the pieces before Statistics keeps contributions
    from neighboring counties in the same pixel.
    """
    if not county_field:
        return make_pieces(arcpy, blocks, fishnet, water, geoid_field, fc, "state")
    with arcpy.da.SearchCursor(blocks,[county_field]) as cur:
        counties = sorted({v for (v,) in cur})
    if not counties or any(not re.fullmatch(r"[0-9]{1,3}", str(v)) for v in counties):
        raise ValueError("Expected nonmissing numeric county codes")
    parts = []
    part_count = 0
    for n, county in enumerate(counties):
        tag = f"p{n:03}"
        field = arcpy.AddFieldDelimiters(blocks,county_field)
        literal = f"'{county}'" if isinstance(county,str) else str(county)
        suffix=uuid4().hex
        handles=[]
        try:
            layer = arcpy.management.MakeFeatureLayer(blocks, "bl_"+suffix, f"{field} = {literal}")[0]; handles.append(layer)
            fish = arcpy.management.MakeFeatureLayer(fishnet, "fi_"+suffix)[0]; handles.append(fish)
            wet = arcpy.management.MakeFeatureLayer(water, "wt_"+suffix)[0]; handles.append(wet)
            arcpy.management.SelectLayerByLocation(fish,"INTERSECT",layer)
            arcpy.management.SelectLayerByLocation(wet,"INTERSECT",layer)
            if int(arcpy.management.GetCount(layer)[0]) < 1 or int(arcpy.management.GetCount(fish)[0]) < 1:
                raise ValueError(f"County {county}: empty blocks or fishnet selection")
            part = make_pieces(arcpy,layer,fish,wet,geoid_field,fc,tag)
            part_count += int(arcpy.management.GetCount(part)[0])
            parts.append(part)
        finally:
            # Release only the handles created above, not their sources.
            for ref in reversed(handles):
                arcpy.management.Delete(ref)
    assembled = fc("state_pieces")
    arcpy.management.CopyFeatures(parts[0], assembled)
    if len(parts)>1:
        arcpy.management.Append(parts[1:], assembled,"NO_TEST")
    if part_count != int(arcpy.management.GetCount(assembled)[0]):
        raise RuntimeError("County append lost or duplicated intersections")
    return assembled


def rasterize_surface(arcpy, state, variable, counts_csv, blocks_pieces, fishnet, geoid_field, target):
    """Sum intersections and rasterize their joined fishnet in the original ArcPy workspace.

    Using a disk table for this join is not an interchangeable implementation
    assumption: in particular, missing joins and a valid sum of zero must keep
    their separate meanings when PolygonToRaster reads the field.
    """
    prefix="memory\\ugvar_"+uuid4().hex+"_"
    inter, fish, stats = [prefix+name for name in ("i","f","s")]
    try:
        if variable in COUNTS:
            arcpy.management.CopyFeatures(blocks_pieces,inter)
            arcpy.management.AddField(inter,"UG_CNT","DOUBLE")
            counts=read_counts(counts_csv,state,variable)
            with arcpy.da.UpdateCursor(inter,[geoid_field,"UG_LAND","UG_PLAND","UG_CNT"]) as cur:
                for row in cur:
                    row[3]=contribution(counts[block_id(row[0],state)],row[1],row[2])
                    cur.updateRow(row)
            del counts
            table,value = inter,"UG_CNT"
        else:
            # Historical area statistics operate directly on cached pieces, not
            # on eligible count rows. Valid zero-area intersections are retained.
            table,value = blocks_pieces,("UG_PLAND" if variable=="PIXEL_LAND" else "UG_PWATER")
        arcpy.management.CopyFeatures(fishnet,fish)
        arcpy.analysis.Statistics(table,stats,[[value,"SUM"]],"PIXELID")
        summed="SUM_"+value
        arcpy.management.JoinField(fish,"PIXELID",stats,"PIXELID",[summed])
        arcpy.management.AddField(fish,value,"DOUBLE")
        with arcpy.da.UpdateCursor(fish,[summed,value]) as cur:
            for row in cur:
                row[1]=row[0]  # Do not replace a missing fishnet join with zero.
                cur.updateRow(row)
        arcpy.conversion.PolygonToRaster(fish,value,target,"CELL_CENTER","",CELL_DEGREES)
        if arcpy.Raster(target).pixelType != "F64":
            raise ValueError(f"{variable}: ArcPy rasterization did not preserve Float64 values")
    finally:
        for item in (stats,fish,inter):
            if arcpy.Exists(item):
                arcpy.management.Delete(item)


def allocate_geography(state, counts_csv, blocks, water, fishnet, geoid_field, outdir,
                       *, county_field=None, variables=COUNTS+("PIXEL_LAND","PIXEL_WATER")):
    """Produce new TIFFs on one common land overlay. All intermediates are run-owned."""
    if not re.fullmatch(r"[0-9]{2}", state) or state == "02":
        raise ValueError("This standard branch needs a two-digit non-Alaska FIPS; route Alaska through run_geography.py")
    if not variables or len(set(variables)) != len(variables) or set(variables)-set(COUNTS+("PIXEL_LAND","PIXEL_WATER")):
        raise ValueError("Expected a unique selection of canonical variables")
    first_count = next((v for v in variables if v in COUNTS), "TOTALPOP")
    counts = read_counts(counts_csv, state, first_count)
    import arcpy  # Requires the licensed ArcGIS Pro environment for this stage only.

    for source in (blocks, water, fishnet):
        d = arcpy.Describe(source)
        if d.shapeType != "Polygon" or d.spatialReference.factoryCode != 4326:
            raise ValueError(f"Expected a WGS84 polygon source: {source}")
    outdir = Path(outdir).resolve()
    # Requiring a new directory is deliberate: even a partial previous run is
    # retained, and a user cannot accidentally write to a source geodatabase.
    outdir.mkdir(parents=False, exist_ok=False)
    db = str(arcpy.management.CreateFileGDB(str(outdir), "intermediates.gdb")[0])
    fc = lambda name: str(Path(db) / name)
    outputs={}
    # Do not inherit a map-session mask, extent or snap raster. No reprojection,
    # forced origin, or arbitrary XY tolerance is introduced for the overlay.
    with arcpy.EnvManager(workspace=db, scratchWorkspace=db, overwriteOutput=False,
                          extent=None, mask=None, snapRaster=None, outputCoordinateSystem=None,
                          XYTolerance=None, XYResolution=None, cellSize=None,
                          parallelProcessingFactor=None, compression="LZW"):
        with arcpy.da.SearchCursor(blocks, [geoid_field]) as cur:
            keys = [block_id(v, state) for (v,) in cur]
        if len(keys) != len(set(keys)) or set(keys) != set(counts):
            raise ValueError("Block geometry and canonical table do not join exactly one-to-one")
        with arcpy.da.SearchCursor(fishnet, ["PIXELID"]) as cur:
            ids = [v for (v,) in cur]
        if None in ids or len(ids) != len(set(ids)):
            raise ValueError("Each fishnet polygon must carry a distinct PIXELID")

        del keys, ids, counts
        pieces = geometry_basis(arcpy,blocks,fishnet,water,geoid_field,fc,county_field)
        for variable in variables:
            suffix = "_CNT" if variable in COUNTS else ""
            tif = str(outdir / f"state_{state}_{variable}{suffix}.tif")
            rasterize_surface(arcpy,state,variable,counts_csv,pieces,fishnet,geoid_field,tif)
            outputs[variable]=tif
    return outputs


def allocate(state, variable, counts_csv, blocks, water, fishnet, geoid_field, outdir):
    """Convenience wrapper for a single-count experiment."""
    return allocate_geography(state, counts_csv, blocks, water, fishnet, geoid_field, outdir,
                              variables=(variable,))[variable]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["state", "variable", "counts_csv", "blocks", "water", "fishnet", "geoid_field", "outdir"]:
        parser.add_argument("--" + name.replace("_", "-"), required=True, dest=name)
    print(allocate(**vars(parser.parse_args())))
