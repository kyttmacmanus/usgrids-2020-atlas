"""Package one geography's complete 31 single-band USGRIDS rasters as NetCDF4.

This is a format conversion, not a resampling or a second allocation. The input
JSON is an explicit mapping of canonical variable names to GeoTIFF paths. Paths
may be relative to the mapping file. There is no workspace discovery.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import netCDF4
import numpy as np
import rasterio
from land_allocation import CELL_DEGREES, COUNTS

AREAS = ("PIXEL_LAND", "PIXEL_WATER")
VARIABLES = COUNTS + AREAS
FILL = -np.finfo(np.float64).max


def check_grid(reference, source):
    """Require matching dimensions and orientation; tolerate serialization noise only.

    ArcGIS can serialize the same lattice with slightly different last bits of
    the affine. Four-corner drift in pixels detects an origin offset *and* a
    scale error that accumulates across a wide grid.
    """
    a, b = reference.transform, source.transform
    if (reference.shape != source.shape or reference.crs != source.crs or
            source.crs is None or source.crs.to_epsg() != 4326 or
            source.count != 1 or source.dtypes != ("float64",)):
        raise ValueError("Expected matched, single-band Float64 WGS84 grids")
    if any(t.b != 0 or t.d != 0 or t.a <= 0 or t.e >= 0 for t in (a, b)):
        raise ValueError("Expected north-up raster with longitude increasing eastwards")
    if not np.allclose([a.a,-a.e,b.a,-b.e],CELL_DEGREES,rtol=1e-7,atol=0.):
        raise ValueError("Expected the nominal USGRIDS 15-arc-second spacing")
    scale = max(abs(v) for v in (a.a, a.e, b.a, b.e))
    for col in [0, source.width]:
        for row in [0, source.height]:
            drift_xy = np.abs(np.subtract(a * (col, row), b * (col, row))) / scale
            if not np.all(drift_xy <= 1e-7):
                raise ValueError("GeoTIFF lattice drift exceeds 1e-7 pixel; refusing to resample")


def write_netcdf(geography, mapping, output):
    """Write to a new output; refuse both incomplete inputs and overwrites."""
    if not geography.strip() or set(mapping) != set(VARIABLES):
        raise ValueError("Name one geography and explicitly map all 29 counts plus both areas")
    paths = {k: Path(mapping[k]).resolve(strict=True) for k in VARIABLES}
    if len(set(paths.values())) != len(VARIABLES):
        raise ValueError("Each variable needs a distinct source file")
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    with ExitStack() as stack:
        grids = {k: stack.enter_context(rasterio.open(v)) for k, v in paths.items()}
        ref = grids["TOTALPOP"]
        for grid in grids.values():
            check_grid(ref, grid)
        t = ref.transform
        with TemporaryDirectory(prefix="usgrids_nc_", dir=output.parent) as temporary:
            staging = Path(temporary) / "data.nc"
            with netCDF4.Dataset(staging, "w", format="NETCDF4") as ds:
                ds.Conventions = "CF-1.8"
                ds.title = f"USGRIDS 2020: {geography}"
                ds.createDimension("y", ref.height)
                ds.createDimension("x", ref.width)
                # The affine describes pixel corners. NetCDF coordinates are
                # centers of the same pixels, with the TIFF's row order intact.
                for name, length, origin, step, standard, units in (
                    ("x", ref.width, t.c, t.a, "longitude", "degrees_east"),
                    ("y", ref.height, t.f, t.e, "latitude", "degrees_north"),
                ):
                    coord = ds.createVariable(name, "f8", (name,))
                    coord[:] = origin + step * (np.arange(length) + 0.5)
                    coord.standard_name, coord.units = standard, units
                crs = ds.createVariable("spatial_ref", "i4")
                crs.assignValue(0)
                # CF 1.8 section 5.6: WKT supplements, but does not replace,
                # the mapping name. This describes the existing WGS84 grid;
                # it does not transform coordinates or modify a scientific value.
                crs.grid_mapping_name = "latitude_longitude"
                crs.spatial_ref = crs.crs_wkt = ref.crs.to_wkt()
                crs.GeoTransform = " ".join(str(v) for v in t.to_gdal())
                for name, grid in grids.items():
                    v = ds.createVariable(name, "f8", ("y", "x"), fill_value=FILL,
                                          zlib=True, complevel=4, shuffle=True,
                                          chunksizes=(min(512, ref.height), min(512, ref.width)))
                    v.grid_mapping, v.coordinates, v.long_name = "spatial_ref", "y x", name
                    v.units = "square_kilometres" if name in AREAS else "count"
                    for _, win in grid.block_windows(1):
                        a = grid.read(1, window=win, masked=True)
                        # Decode the mask separately for every band. For example,
                        # Alaska uses a positive sentinel; zero is never NoData.
                        vals = a.compressed()
                        if not np.isfinite(vals).all() or np.any(vals < 0):
                            raise ValueError(f"{name}: unexpected valid-cell value")
                        rs, cs = win.toslices()
                        v[rs, cs] = a.filled(FILL)
            # Hard-link a completely closed file into place. Unlike replace(),
            # this fails safely if another writer created the target meanwhile.
            os.link(staging, output)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geography", required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    def unique_keys(items):
        """Refuse duplicate variables that a normal JSON parser would silently discard."""
        if len(dict(items)) != len(items):
            raise ValueError("Duplicate variable in mapping JSON")
        return dict(items)
    raw = json.loads(args.mapping.read_text("utf-8"), object_pairs_hook=unique_keys)
    mapping = {k: args.mapping.parent / v for k, v in raw.items()}
    print(write_netcdf(args.geography, mapping, args.output))
