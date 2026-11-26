"""Run the scientific workflow for one explicitly configured jurisdiction.

All stages write below a newly allocated run directory. Separately invocable
stages let the operator use ArcGIS Pro's licensed Python for spatial processing
and an open-source Python for the final TIFF-to-NetCDF conversion.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from land_allocation import COUNTS, allocate_geography as standard_allocate, prepare_water, validate_water_order

ALL = (*COUNTS,"PIXEL_LAND","PIXEL_WATER")
SCHEMA = {"state", "source", "blocks", "geoid_field", "fishnet", "water", "outdir",
          "county_field", "alaska", "netcdf_python"}


def unique(pairs):
    """Reject ambiguous duplicate keys while decoding scientific JSON inputs."""
    d={}
    for key,value in pairs:
        if key in d:
            raise ValueError(f"Duplicate config key: {key}")
        d[key]=value
    return d


def read_config(path):
    """Validate state, water and lattice options and resolve paths relative to the config."""
    c=json.loads(path.read_text("utf-8-sig"),object_pairs_hook=unique)
    wanted=SCHEMA-{"alaska","netcdf_python","county_field"}
    if wanted-set(c) or set(c)-SCHEMA:
        raise ValueError(f"Missing keys {wanted-set(c)}; unsupported keys {set(c)-SCHEMA}")
    with Path(__file__).with_name("geographies.csv").open(newline="",encoding="utf-8-sig") as stream:
        states={r["state_fips"]:r["abbr"] for r in csv.DictReader(stream)}
    if len(states)!=52 or c["state"] not in states:
        raise ValueError("State must be one of the 52 two-digit FIPS identifiers")
    if not isinstance(c["water"],dict) or set(c["water"])!={"mode","sources"}:
        raise ValueError("Water needs mode and sources; do not guess the water source")
    mode=c["water"]["mode"]; sources=c["water"]["sources"]
    if (mode not in {"prepared","nationwide","ordered_components"} or not isinstance(sources,list)
            or not sources or (mode!="ordered_components" and len(sources)!=1)):
        raise ValueError("Invalid water mode or source count")

    def resolve(s):
        """Resolve one explicit dataset name; do not infer or search for it."""
        if not isinstance(s,str) or not s.strip():
            raise ValueError("Supply a nonempty file/feature class path")
        return str((path.parent/s).resolve())
    for key in ["source","blocks","fishnet","outdir"]:
        c[key]=resolve(c[key])
    c["water"]["sources"]=[resolve(p) for p in sources]
    if len(set(c["water"]["sources"]))!=len(sources):
        raise ValueError("Duplicate water input")
    if mode=="ordered_components":
        validate_water_order(c["water"]["sources"])
    if c.get("netcdf_python"):
        c["netcdf_python"]=resolve(c["netcdf_python"])
    # The other states use an ordinary statewide overlay unless the science
    # configuration calls for a county partition. A dateline state is never
    # silently routed through this ordinary fishnet rasterization branch.
    if c["state"] in {"27","40","45"}:
        c.setdefault("county_field","COUNTYFP20")
    if c["state"]!="02" and "alaska" in c:
        raise ValueError("Alaska-only options on non-Alaska state")
    for field in (c["geoid_field"], c.get("county_field", "COUNTYFP20")):
        if not isinstance(field,str) or not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]*",field):
            raise ValueError("Expected a simple unqualified GIS field name")
    extra_inputs=[]
    if c["state"]=="02":
        ak=c.get("alaska")
        if not isinstance(ak,dict) or set(ak)-{"grid_reference","fishnet_kind","water_mask","county_field"}:
            raise ValueError("Supply alaska input settings (see ALASKA.md)")
        kind=ak.get("fishnet_kind","polygons")
        if kind not in {"polygons","pixelid_raster","paired_area_masks"}:
            raise ValueError("Unknown Alaska grid source kind")
        if kind!="paired_area_masks" and (not ak.get("grid_reference") or "water_mask" in ak):
            raise ValueError("Alaska polygons/PIXELID raster require grid_reference, not water_mask")
        if kind=="paired_area_masks" and not ak.get("water_mask"):
            raise ValueError("The paired-area grid source requires water_mask")
        if "county_field" in c:
            if ak.get("county_field",c["county_field"])!=c["county_field"]:
                raise ValueError("Conflicting Alaska county_field values")
            ak["county_field"]=c["county_field"]
        if not isinstance(ak.get("county_field","COUNTYFP20"),str) or not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]*",ak.get("county_field","COUNTYFP20")):
            raise ValueError("Invalid Alaska county field name")
        for key in ("grid_reference","water_mask"):
            if key in ak:
                ak[key]=resolve(ak[key]); extra_inputs.append(ak[key])
    output=Path(c["outdir"])
    for p in [Path(i) for i in (c["blocks"],c["fishnet"],c["source"],*c["water"]["sources"],*extra_inputs)]:
        if output==p or output in p.parents or p in output.parents:
            raise ValueError("Output must be separate from input datasets")
    return c,states[c["state"]]


def write_once(path, obj):
    """Create a readable receipt without overwriting an earlier stage record."""
    with path.open("x",encoding="utf8") as f:
        json.dump(obj,f,indent=2,allow_nan=False)
        f.write("\n")


def file_sha256(path):
    """Bounded-memory receipt for files crossing a process/interpreter boundary."""
    digest=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for buf in iter(lambda: stream.read(1<<20),b""):
            digest.update(buf)
    return digest.hexdigest()


def run(path, stage):
    """Execute one or all state stages and bind their output files to this configuration."""
    c,abbr=read_config(path)
    # Reusing a completed stage with a different configuration can silently mix
    # geographies. Bind all stages to the resolved config in this run directory.
    signature=hashlib.sha256(json.dumps(c,sort_keys=True).encode("utf8")).hexdigest()
    base=Path(c["outdir"]); state=c["state"]; table=base/"canonical_counts.csv"
    if stage=="check":
        print(f"Config shape PASS ({state}/{abbr}); GIS inputs and licensing not exercised.")
        return
    if stage in {"counts","all"}:
        from prepare_counts import prepare_counts
        base.mkdir(parents=False,exist_ok=False)
        receipt=prepare_counts(state,Path(c["source"]),table)
        write_once(base/"counts_complete.json",{"config_sha256":signature,"state":state,"source":receipt,
                                               "canonical_sha256":file_sha256(table)})
    def require_receipt(name):
        """Reject a prior stage receipt belonging to another state or configuration."""
        previous=json.loads((base/name).read_text("utf-8"))
        if previous.get("config_sha256")!=signature or previous.get("state")!=state:
            raise ValueError("Previous stage completed under a different configuration/state")
        return previous
    if stage in {"spatial","all"}:
        if require_receipt("counts_complete.json")["canonical_sha256"]!=file_sha256(table):
            raise ValueError("Canonical table changed since source preparation")
        if (base/"geotiff").exists() or (base/"spatial_complete.json").exists():
            raise FileExistsError("The spatial output or receipt already exists; use a fresh run")
        import arcpy
        # Nationwide Merge uses its native geographic CRS; only the block Clip
        # inside prepare_water explicitly asks for WGS84. An inherited ArcGIS
        # map extent or transform must not silently change the state's water.
        with arcpy.EnvManager(overwriteOutput=False, extent=None, mask=None, snapRaster=None,
                              cellSize=None, outputCoordinateSystem=None, geographicTransformations=None,
                              XYTolerance=None, XYResolution=None, parallelProcessingFactor=None):
            water=prepare_water(arcpy,c["blocks"],c["water"]["mode"],c["water"]["sources"],base/"water_preparation",state=state)
        if state=="02":
            from alaska import allocate_geography
            options=c.get("alaska",{})
        else:
            allocate_geography=standard_allocate
            options={"county_field":c.get("county_field")}
        tifs=allocate_geography(state,table,c["blocks"],water,c["fishnet"],c["geoid_field"],base/"geotiff",**options)
        if set(tifs)!=set(ALL):
            raise ValueError("Spatial stage did not return exactly the 31 scientific variables")
        # Store relative filenames, not machine-specific absolute paths, in the
        # cross-interpreter handoff. Refuse an adapter that returns an input TIFF.
        mapping={}
        for var in ALL:
            p=Path(tifs[var]).resolve(strict=True)
            if (base/"geotiff") not in p.parents or p.suffix.lower()!=".tif":
                raise ValueError(f"{var}: not a TIFF inside this run's new geotiff directory")
            mapping[var]=p.relative_to(base).as_posix()
        write_once(base/"tiffs.json",mapping)
        write_once(base/"spatial_complete.json",{"config_sha256":signature,"state":state,"variables":31,
                   "mapping_sha256":file_sha256(base/"tiffs.json"),
                   "tiff_sha256":{var:file_sha256(base/p) for var,p in mapping.items()}})
    if stage in {"netcdf","all"}:
        spatial=require_receipt("spatial_complete.json")
        if spatial["mapping_sha256"]!=file_sha256(base/"tiffs.json"):
            raise ValueError("GeoTIFF mapping changed since allocation")
        mapping=json.loads((base/"tiffs.json").read_text("utf8"),object_pairs_hook=unique)
        if set(mapping)!=set(ALL) or {var:file_sha256(base/p) for var,p in mapping.items()}!=spatial["tiff_sha256"]:
            raise ValueError("GeoTIFF changed since allocation")
        target=base/f"usa{abbr}_31vars.nc"
        subprocess.run([c.get("netcdf_python") or sys.executable,
                        str(Path(__file__).with_name("grid_netcdf.py")),
                        "--geography",abbr,"--mapping",str(base/"tiffs.json"),
                        "--output",str(target)],check=True)
        write_once(base/"netcdf_complete.json",{"config_sha256":signature,"state":state,"file":target.name,
                                                "sha256":file_sha256(target)})


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config",type=Path)
    parser.add_argument("--stage",choices=("check","counts","spatial","netcdf","all"),default="all")
    args=parser.parse_args()
    run(args.config.resolve(),args.stage)
