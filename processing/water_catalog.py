"""Prepare the ordered 2022 U.S. Census area-water input specification for a state run.

No GIS package or network access is required. Read extracted official Shapefiles
and write only a new configuration. Geometry is not reprojected, simplified, or
merged by this utility; the processing workflow does the ArcPy Merge and Clip.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re

COUNTY = re.compile(r"tl_2022_([0-9]{5})_areawater[.]shp")
# Fingerprint of sorted five-digit *public county identifiers*, one per line
# including a terminal LF. This does not fingerprint any private or science file.
ID_SET = "ff7a213d519a6cd96ada33ab90837f5ef561c2bf2c4e6a7f136c4551143030a9"


def ordered_water_sources(root):
    """Return 3,222 unique complete Shapefiles, in five-digit county FIPS order.

    The target is the 50 states, DC and PR; other island areas in the Census
    distribution are not inputs. Equal counts alone do not prove the same set.
    This is a membership/sidecar check, not a check of geometry content.
    """
    root=Path(root).resolve(strict=True)
    with Path(__file__).with_name("geographies.csv").open(newline="",encoding="utf-8") as f:
        states={r["state_fips"] for r in csv.DictReader(f)}
    files={}
    for shp in root.rglob("tl_2022_*_areawater.shp"):
        match=COUNTY.fullmatch(shp.name)
        if not match or match[1][:2] not in states:
            continue
        if match[1] in files:
            raise ValueError(f"Duplicate county component: {match[1]}")
        for suffix in (".shp",".shx",".dbf",".prj"):
            p=shp.with_suffix(suffix)
            if not p.is_file() or p.stat().st_size==0:
                raise ValueError(f"Incomplete Shapefile: {p}")
        files[match[1]]=str(shp)
    ids=sorted(files)
    if len(ids)!=3222 or hashlib.sha256(("\n".join(ids)+"\n").encode("ascii")).hexdigest()!=ID_SET:
        raise ValueError(f"Expected the 3,222 official 2022 counties in the 52 jurisdictions; found {len(ids)}")
    return [files[k] for k in ids]


def main():
    """Replace the water stanza in a *new* sibling config; keep relative paths valid."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("extracted_root",type=Path)
    parser.add_argument("base_config",type=Path)
    parser.add_argument("new_config",type=Path)
    args=parser.parse_args()
    if args.base_config.resolve().parent!=args.new_config.resolve().parent:
        parser.error("Keep both configs in the same directory so relative paths retain their meaning")
    with args.base_config.open(encoding="utf-8-sig") as f:
        config=json.load(f)
    config["water"]={"mode":"ordered_components","sources":ordered_water_sources(args.extracted_root)}
    with args.new_config.open("x",encoding="utf-8") as f:
        json.dump(config,f,indent=2)
        f.write("\n")


if __name__=="__main__":
    main()
