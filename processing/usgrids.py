"""One command for the USGRIDS 2020 geography and national production workflows.

State configurations select raw DHC input, matching geometry and water. A
national configuration instead consumes the 52 completed component GeoTIFF sets.
The national method is not a substitute for block-to-grid allocation.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from run_geography import unique


def dispatch(path, stage, variable=None):
    """Dispatch explicit scope only; do not infer a missing geography or build missing states."""
    path=Path(path).resolve(strict=True)
    obj=json.loads(path.read_text(encoding="utf-8-sig"),object_pairs_hook=unique)
    if not isinstance(obj,dict):
        raise ValueError("A geography or national configuration must be one JSON object")
    if obj.get("kind")=="national":
        if "state" in obj or stage=="counts":
            raise ValueError("National assembly takes component rasters, not one state's census counts")
        from national import run
        if variable is not None:
            return run(path,stage,variable=variable)
    else:
        if variable is not None:
            raise ValueError("--variable is restricted to national single-product validation")
        if 'kind' in obj or 'state' not in obj:
            raise ValueError("Specify a two-digit state FIPS or kind=national")
        from run_geography import run
    return run(path,stage)


def main():
    """Select a single explicit scientific stage or execute the dependency chain."""
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("config",type=Path)
    cli.add_argument("--stage",choices=("check","counts","spatial","netcdf","all"),default="all")
    cli.add_argument("--variable",choices=("TOTALPOP",),help="National only: one full-extent TIFF; no NetCDF")
    args=cli.parse_args()
    dispatch(args.config,args.stage,args.variable)


if __name__=="__main__":
    main()
