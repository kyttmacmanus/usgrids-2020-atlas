"""Construct the 2020 national USGRIDS composite from 52 completed geographic components.

This is the ArcGIS CellStatistics/SUM method, not a generic command for
mosaicking rasters. Eligible values in overlapping states are added; a cell
outside all component masks is NoData. The independent NetCDF stage never
resamples or recomputes these values. See NATIONAL.md for geometry and cost.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid

from land_allocation import CELL_DEGREES, COUNTS

VARIABLES = (*COUNTS, "PIXEL_LAND", "PIXEL_WATER")
RESERVE = 15 * 2**30                 # Never spend the production operating margin.
REFERENCE_TIFF_BYTES = 9811553149
REFERENCE_NETCDF_BYTES = 5046576081
TOTALPOP_REFERENCE_BYTES = 419212225
# Dedicated one-variable validation: separate budgets for a single compressed
# destination and additional native work files on the scratch filesystem.
TOTALPOP_OUTPUT_BUDGET = 512 * 2**20
TOTALPOP_SCRATCH_BUDGET = 2 * 2**30
TOTALPOP_NATIVE_EXTRA = 2**30
SCRATCH_RESERVE = 5 * 2**30
SHAPE = (12863, 86195)               # Full WGS84 MAXOF rectangle (rows, columns).
# Registration from the released national lattice. This is a postcondition,
# not an instruction to shift, warp or manufacture the national extent.
WEST, NORTH = -179.25833333351645, 71.45833311895305


def unique(pairs):
    """Duplicate JSON keys make a geography/variable ambiguous; reject them."""
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("Duplicate key in national or component configuration")
    return result


def read_json(path):
    """Load an explicit UTF-8 input map, preserving case and preventing key shadowing."""
    return json.loads(Path(path).read_text("utf-8-sig"), object_pairs_hook=unique)


def write_new(path, data):
    """Create a new stage receipt. Do not silently adopt products of a failed run."""
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write("\n")


def sha256(path):
    """Fingerprint closed files in bounded memory for subsequent-stage verification."""
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for buf in iter(lambda: stream.read(4 * 2**20), b""):
            h.update(buf)
    return h.hexdigest()


def registry():
    """Supply all 50 states, DC and PR in ascending two-digit FIPS order."""
    with Path(__file__).with_name("geographies.csv").open(encoding="utf-8-sig", newline="") as f:
        states = [(r["state_fips"], r["abbr"]) for r in csv.DictReader(f)]
    if len(states) != 52 or states != sorted(states) or len({f for f, _ in states}) != 52:
        raise ValueError("Expected the 52 ordered 2020 USGRIDS geography identifiers")
    return states


def name_for(variable):
    """Counts use the CNT suffix; physical areas (square kilometres) do not."""
    return variable + ("_CNT" if variable in COUNTS else "")


def configuration(path, *, needed=VARIABLES):
    """Resolve a new output location and a complete set of component inputs.

    Component maps are the tiffs.json files from individual runs. Alternatively
    the archive layout addresses explicitly named, extracted geography TIFFs.
    No filesystem-wide search, latest-file selection or missing-state fallback.
    """
    path = Path(path).resolve(strict=True)
    cfg = read_json(path)
    required = {"kind", "layout", "component_root", "outdir"}
    if not isinstance(cfg, dict) or required-set(cfg) or set(cfg)-required-{"netcdf_python"}:
        raise ValueError("National config needs kind, layout, component_root and outdir")
    if cfg["kind"] != "national" or cfg["layout"] not in ("component_maps", "archive_tiffs"):
        raise ValueError("Select kind=national and layout=component_maps or archive_tiffs")
    if any(not isinstance(cfg[k], str) or not cfg[k].strip() for k in cfg):
        raise ValueError("National config values must be nonempty strings")
    source = (path.parent/cfg["component_root"]).resolve(strict=True)
    out = (path.parent/cfg["outdir"]).resolve()
    if not source.is_dir() or out == source or source in out.parents or out in source.parents:
        raise ValueError("Output must be outside the input tree")
    if path == out or out in path.parents or not out.parent.is_dir():
        raise ValueError("Use a separate output under an existing parent directory")
    grouped = {}
    for fips, abbr in registry():
        base = source/fips
        if cfg["layout"] == "archive_tiffs":
            mapping = {v:base/f"usa{abbr}_{name_for(v)}.tif" for v in needed}
        else:
            index = base/"tiffs.json"
            record = read_json(base/"spatial_complete.json")
            if record.get("state") != fips or record.get("mapping_sha256") != sha256(index):
                raise ValueError(f"State or TIFF-map identity mismatch: {fips}")
            m = read_json(index)
            if not isinstance(m, dict) or set(m) != set(VARIABLES):
                raise ValueError(f"Incomplete 31-variable mapping: {fips}")
            mapping = {v:base/m[v] for v in needed}
        entries = {v:p.resolve(strict=True) for v,p in mapping.items()}
        if any(not p.is_file() or p.suffix.lower() != ".tif" or base.resolve() not in p.parents
               for p in entries.values()):
            raise ValueError(f"Expected only TIFFs inside state directory {fips}")
        grouped[fips] = entries
    if len({p for m in grouped.values() for p in m.values()}) != 52*len(needed):
        raise ValueError("Component aliases point multiple variables/states to one file")
    interp = str((path.parent/cfg["netcdf_python"]).resolve(strict=True)) if "netcdf_python" in cfg else sys.executable
    return cfg, grouped, out, interp


def space_needed(phase):
    """Conservative planning floor in bytes; includes scratch and a 15-GiB margin."""
    if phase == "netcdf":
        return RESERVE + REFERENCE_NETCDF_BYTES
    return RESERVE + REFERENCE_TIFF_BYTES + REFERENCE_NETCDF_BYTES + SHAPE[0]*SHAPE[1]*8


def disk_gate(location, minimum):
    """Avoid even starting an expensive write if it would consume the working margin."""
    available = shutil.disk_usage(location).free
    if available < minimum:
        raise OSError(f"Insufficient storage: {available:,} bytes free; {minimum:,} required here")


def array_stats(values):
    """Return a Float64 valid count, sum, and minimum; only NaN represents NoData."""
    import numpy as np
    arr = np.asarray(values, dtype="float64")
    if np.isinf(arr).any():
        raise ValueError("Infinite valid values in scientific raster")
    vals = arr[~np.isnan(arr)]
    return (int(vals.size), float(np.sum(vals, dtype="float64")), float(vals.min()) if vals.size else None)


def raster_stats(arcpy, path):
    """Reproduce the 32-row south-to-north reducer in count or km² units.

    ArcGIS maps each source's own NoData sentinel to NaN. The order of each
    Float64 sum and of the final math.fsum is deliberately not interchangeable
    with a single full-raster sum. Negative valid cells are not silently zeroed.
    """
    import numpy as np
    raster = arcpy.Raster(str(path))
    count, subtotals, low = 0, [], math.inf
    for bottom in range(0, raster.height, 32):
        height = min(32, raster.height-bottom)
        ll = arcpy.Point(raster.extent.XMin, raster.extent.YMin+bottom*raster.meanCellHeight)
        data = arcpy.RasterToNumPyArray(raster,ll,raster.width,height,nodata_to_value=np.nan)
        n, total, minimum = array_stats(data)
        if n:
            count += n
            subtotals.append(total)
            low = min(low, minimum)
    if not count or low < -1e-9:
        raise ValueError(f"Empty or materially negative scientific surface: {path}")
    return count, math.fsum(subtotals)


def grid(arcpy, path, *, national=False):
    """Require native Float64, one WGS84 band and 15-arc-second lattice, no warping.

    Geographic crops carry small (<0.001 cell) differences in serialized origin;
    that tolerance is an input rejection limit, not an instruction to resample.
    The expected national output is a single two-domain rectangle including PR.
    """
    r = arcpy.Raster(str(path))
    if (r.bandCount != 1 or r.spatialReference.factoryCode != 4326 or
            str(r.pixelType).upper() not in ("F64","64_BIT","DOUBLE") or
            max(abs(r.meanCellWidth-CELL_DEGREES), abs(r.meanCellHeight-CELL_DEGREES)) > CELL_DEGREES*1e-7):
        raise ValueError(f"Expected single-band Float64 WGS84 on the 2020 cell spacing: {path}")
    offsets = ((r.extent.XMin-WEST)/CELL_DEGREES,(NORTH-r.extent.YMax)/CELL_DEGREES)
    col,row=map(round,offsets)
    east,south=(r.extent.XMax-WEST)/CELL_DEGREES,(NORTH-r.extent.YMin)/CELL_DEGREES
    if (any(abs(v-round(v))>0.001 for v in offsets) or abs(east-col-r.width)>0.001
            or abs(south-row-r.height)>0.001 or min(col,row)<0 or col+r.width>SHAPE[1] or row+r.height>SHAPE[0]):
        raise ValueError(f"Unexpected component lattice alignment or envelope: {path}")
    if national and ((r.height, r.width) != SHAPE or max(abs(v) for v in offsets) > 0.001):
        raise ValueError(f"Unexpected national extent: {path}")


def reconcile(national, components):
    """Return the count/km² total residual only inside the production absolute+relative bound."""
    if len(components) != 52:
        raise ValueError("National reconciliation needs exactly 52 component totals")
    total = math.fsum(components)
    delta = national-total
    tolerance = 1e-9 + 1e-12*abs(total)
    if not math.isfinite(delta) or abs(delta) > tolerance:
        raise ValueError(f"National sum differs from components by {delta}, outside {tolerance}")
    return {"component_total":total,"national_total":national,"residual":delta,"tolerance":tolerance}


def geographic_sum(arcpy, sources, temporary):
    """Save the production single-band SUM: ignore missing contributors, not numeric zeros.

    The caller establishes the union extent and WGS84 environment. A list in
    FIPS order is intentional; the unused percentile options mirror the exact
    native call. In particular FIRST, mean, mosaics with replacement, and
    projecting the Alaska component are not mathematically interchangeable.
    """
    if len(sources)!=52 or len(set(sources))!=52:
        raise ValueError("The native operation needs 52 distinct geography sources")
    mosaic = arcpy.ia.CellStatistics([str(p) for p in sources],"SUM","DATA","SINGLE_BAND",90,"AUTO_DETECT")
    mosaic.save(str(temporary))


def single_space(out_parent, scratch_parent):
    """Preflight a TOTALPOP-only run under the frozen 15 GiB output reserve.

    The initial native TIFF save can consume far more working space than its
    419-MB closed LZW product. Budget a full 8.87-GB Float64 plane *above*
    the 15-GiB operating margin, plus one GiB native-work allowance and half
    a GiB for a compressed copy. The second volume keeps its own 5-GiB
    reserve plus 2 GiB headroom. No test validates these as exact peaks.
    """
    first = RESERVE + SHAPE[0]*SHAPE[1]*8 + TOTALPOP_NATIVE_EXTRA + TOTALPOP_OUTPUT_BUDGET
    if Path(out_parent).stat().st_dev == Path(scratch_parent).stat().st_dev:
        disk_gate(out_parent, first + TOTALPOP_SCRATCH_BUDGET)
    else:
        disk_gate(out_parent, first)
        disk_gate(scratch_parent, SCRATCH_RESERVE + TOTALPOP_SCRATCH_BUDGET)


def verified_tiff_relocation(arcpy, original, scratch):
    """Move only a new intermediate TIFF family across volumes without resampling.

    Some TIFF writers preflight the uncompressed 8.87-GB plane even when the
    LZW file is about 419 MB. Save natively on the output volume, preserve the
    closed bytes (including any TIFF sidecars) on scratch, verify size + SHA-256
    and native grid there, then retire only the owned first copy. The same final
    ArcGIS CopyRaster is still executed on a volume that fits its preflight.
    """
    relocated=scratch/original.name
    if original.parent.parent.name!="working_native" or relocated.exists():
        raise ValueError("Unexpected staging location or existing scratch data")
    files=[p for p in original.parent.glob(original.stem+".*") if p.is_file() and p.suffix.lower()!=".lock"]
    if original not in files: raise FileNotFoundError(original)
    disk_gate(scratch,SCRATCH_RESERVE+sum(p.stat().st_size for p in files))
    for p in files:
        dest=scratch/p.name
        if dest.exists(): raise FileExistsError(dest)
        shutil.copyfile(p,dest)
        if dest.stat().st_size!=p.stat().st_size or sha256(dest)!=sha256(p):
            raise IOError("Scratch preservation failed; owned original is retained")
    grid(arcpy,relocated,national=True)
    arcpy.management.Delete(str(original))
    return relocated


def spatial(grouped, out, cfg, config_signature, *, single=False):
    """Apply SUM/DATA per variable, require complete support and reconcile to 52 inputs."""
    # Enforce the storage floor *before* importing or licensing GIS.
    scratch_parent=Path(tempfile.gettempdir()).resolve() if single else out.parent
    if single:
        single_space(out.parent,scratch_parent)
    else:
        disk_gate(out.parent, space_needed("spatial"))
    if out.exists():
        raise FileExistsError(out)
    import arcpy
    if arcpy.GetInstallInfo().get("Version") != "3.7.1" or arcpy.ProductInfo() != "ArcInfo":
        raise RuntimeError("The verified 2020 implementation uses ArcGIS Pro 3.7.1 Advanced")
    initial = arcpy.CheckExtension("Spatial")
    if initial not in ("Available","CheckedOut"):
        raise RuntimeError("Run in a licensed ArcGIS Pro environment with Spatial Analyst")
    if initial == "Available" and arcpy.CheckOutExtension("Spatial") != "CheckedOut":
        raise RuntimeError("Spatial Analyst could not be checked out")
    try:
        # All user inputs are read-only; never overwrite previous/partial products.
        out.mkdir(exist_ok=False)
        tifs = out/"geotiff"
        tifs.mkdir()
        scratch = Path(tempfile.mkdtemp(prefix="usgrids_totalpop_",dir=scratch_parent)) if single else out/"working"
        if not single: scratch.mkdir()
        if single:
            native_parent=out/"working_native"
            native_parent.mkdir()
            native_dir=Path(tempfile.mkdtemp(prefix="cellstats_",dir=native_parent))
        else:
            native_dir=scratch
        events=out/"single_variable_events.jsonl"
        def progress(event, **detail):
            """Preserve small diagnostic markers without writing a second science product."""
            if single:
                from datetime import datetime,timezone
                with events.open("a",encoding="utf-8") as f:
                    f.write(json.dumps(dict(event=event,utc=datetime.now(timezone.utc).isoformat(),**detail))+"\n")
        progress("START", scratch=str(scratch), initial_output_free=shutil.disk_usage(out).free,
                 initial_scratch_free=shutil.disk_usage(scratch).free)
        relative, hashes, totals = {}, {}, {}
        for variable in (("TOTALPOP",) if single else VARIABLES):
            disk_gate(out, RESERVE)
            sources = [m[variable] for m in grouped.values()]
            for state, path in zip(grouped,sources):
                if cfg["layout"] == "component_maps":
                    proof = read_json(Path(cfg["component_root"])/state/"spatial_complete.json")
                    if proof.get("tiff_sha256",{}).get(variable) != sha256(path):
                        raise ValueError(f"TIFF changed since state scientific processing: {state} {variable}")
                grid(arcpy,path)
            tmp = native_dir/(("TOTALPOP_stage" if single else uuid.uuid4().hex)+".tif")
            final = tifs/(name_for(variable)+"_national.tif")
            # Pin default GIS session state: do not inherit a map's display mask,
            # snap grid, analysis cell size or non-default parallel factor.
            with arcpy.EnvManager(outputCoordinateSystem=arcpy.SpatialReference(4326),extent="MAXOF",
                                  workspace=str(scratch),scratchWorkspace=str(scratch),compression="LZW",
                                  cellSize=None,snapRaster=None,mask=None,parallelProcessingFactor=None,
                                  geographicTransformations=None,overwriteOutput=False):
                progress("CELL_STATISTICS",variable=variable,native_target=str(tmp))
                try:
                    geographic_sum(arcpy,sources,tmp)
                except Exception:
                    progress("NATIVE_ERROR",messages=arcpy.GetMessages())
                    raise
                progress("CALCULATE_STATISTICS",temporary_bytes=tmp.stat().st_size)
                arcpy.management.CalculateStatistics(str(tmp))
                grid(arcpy,tmp,national=True)
                if single:
                    progress("PRESERVE_COMPRESSED_TEMP",source=str(tmp),target=str(scratch/tmp.name),bytes=tmp.stat().st_size)
                    tmp=verified_tiff_relocation(arcpy,tmp,scratch)
                    progress("PRESERVED_VERIFIED",sha256=sha256(tmp),current_native=str(tmp))
                progress("REDUCE_NATIONAL")
                n, national_total = raster_stats(arcpy,tmp)
                component_totals=[]
                for state,source in zip(grouped,sources):
                    component_totals.append(raster_stats(arcpy,source)[1])
                    progress("COMPONENT_SUM",state=state,total=component_totals[-1])
                measured = reconcile(national_total,component_totals)
                if single: disk_gate(out,RESERVE+tmp.stat().st_size)
                progress("COPY_TO_FINAL",output=str(final))
                arcpy.management.CopyRaster(str(tmp),str(final))
                grid(arcpy,final,national=True)
                arcpy.management.Delete(str(tmp))  # only our new run's UUID-scoped scratch TIFF
            relative[variable] = final.relative_to(out).as_posix()
            hashes[variable] = sha256(final)
            totals[variable] = {"valid_cells":n,**measured}
        if single:
            write_new(out/"TOTALPOP_only_complete.json",{"scope":"ONE_FULL_EXTENT_TIFF","variable":"TOTALPOP",
                      "components":52,"netcdf_created":False,"config_sha256":config_signature,
                      "output":relative["TOTALPOP"],"bytes":(out/relative["TOTALPOP"]).stat().st_size,
                      "sha256":hashes["TOTALPOP"],"reconciliation":totals["TOTALPOP"]})
            progress("COMPLETE",geotiffs=1,netcdf=0)
            return
        write_new(out/"tiffs.json",relative)
        write_new(out/"spatial_complete.json",{"geography":"NATIONAL","components":52,
                  "config_sha256":config_signature,"mapping_sha256":sha256(out/"tiffs.json"),
                  "tiff_sha256":hashes,"reconciliation":totals})
    finally:
        if initial == "Available":
            arcpy.CheckInExtension("Spatial")


def run(config_path, stage="all", *, variable=None):
    """Run input checks, native ArcGIS spatial generation, NetCDF conversion, or both."""
    if variable is not None and (variable!="TOTALPOP" or stage not in ("check","spatial")):
        raise ValueError("The one-product validation mode accepts only TOTALPOP and check/spatial. No NetCDF is generated.")
    cfg, components, out, interp = configuration(config_path,needed=("TOTALPOP",) if variable is not None else VARIABLES)
    cfg["component_root"] = str((Path(config_path).resolve().parent/cfg["component_root"]).resolve())
    config_signature = hashlib.sha256(json.dumps({**cfg,"outdir":str(out)},sort_keys=True).encode()).hexdigest()
    if variable is not None:
        if stage=="check":
            single_space(out.parent,Path(tempfile.gettempdir()))
            print("Full-extent TOTALPOP only: 52 inputs; storage check passed. No scientific run performed.")
            return
        spatial(components,out,cfg,config_signature,single=True)
        return
    if stage == "check":
        print(f"National inputs: {len(components)} jurisdictions, {sum(map(len,components.values()))} TIFFs. "
              f"Storage: {shutil.disk_usage(out.parent).free:,} bytes free; "
              f"spatial start floor {space_needed('spatial'):,}. No scientific run performed.")
        return
    if stage not in ("all","spatial","netcdf"):
        raise ValueError("Use check, spatial, netcdf or all for national processing")
    if stage in ("all","spatial"):
        spatial(components, out, cfg, config_signature)
    if stage in ("all","netcdf"):
        disk_gate(out,space_needed("netcdf"))
        mapping = read_json(out/"tiffs.json")
        proof = read_json(out/"spatial_complete.json")
        if (set(mapping) != set(VARIABLES) or proof["geography"] != "NATIONAL" or proof["components"] != 52
                or proof.get("config_sha256") != config_signature
                or set(proof["reconciliation"]) != set(VARIABLES) or proof["mapping_sha256"] != sha256(out/"tiffs.json")
                or any((out/"geotiff").resolve() not in (out/p).resolve().parents for p in mapping.values())
                or {v:sha256(out/p) for v,p in mapping.items()} != proof["tiff_sha256"]):
            raise ValueError("National TIFFs no longer match the 31-variable reconciled result")
        nc = out/"USGRIDS_2020_NATIONAL_31vars.nc"
        subprocess.run([interp,str(Path(__file__).with_name("grid_netcdf.py")),"--geography","NATIONAL",
                        "--mapping",str(out/"tiffs.json"),"--output",str(nc)],check=True)
        write_new(out/"netcdf_complete.json",{"geography":"NATIONAL","file":nc.name,"sha256":sha256(nc)})
