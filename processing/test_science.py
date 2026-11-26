"""Small public examples with invented numbers; no production, network or ArcGIS."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import csv
import json

import numpy as np
import netCDF4
import rasterio
from rasterio.transform import from_origin
from land_allocation import COUNTS, block_id, contribution, land_area, read_counts
from grid_netcdf import FILL, VARIABLES, write_netcdf
from run_geography import file_sha256, read_config, run


class ScientificFixtures(unittest.TestCase):
    def test_state_routing(self):
        # No ArcPy import: verify every published geography reaches its intended
        # configuration parser and that relative paths cannot escape into inputs.
        folder=Path(__file__).resolve().parent
        with (folder/"geographies.csv").open(encoding="utf8",newline="") as source:
            states=list(csv.DictReader(source))
        self.assertEqual(len(states),52)
        with TemporaryDirectory() as tmp:
            tmp=Path(tmp); cfg=tmp/"cfg.json"
            defaults=json.loads((folder/"example.delaware.json").read_text("utf8"))
            for s in states:
                raw={**defaults,"state":s["state_fips"]}
                if raw["state"]=="02":
                    raw["alaska"]={"grid_reference":"inputs/ak_lattice.tif"}
                cfg.write_text(json.dumps(raw),encoding="utf8")
                c,abbr=read_config(cfg)
                self.assertEqual(abbr,s["abbr"])
                self.assertEqual(Path(c["outdir"]).parent,tmp)
                self.assertEqual(c.get("county_field"),"COUNTYFP20" if c["state"] in {"27","40","45"} else None)
                if c["state"]=="02":
                    self.assertEqual(Path(c["alaska"]["grid_reference"]),tmp/"inputs/ak_lattice.tif")
            for patch in ({"state":"02"},{"state":"99"},{"outdir":"inputs"},
                          {"alaska":{"grid_reference":"bad.tif"}},{"geoid_field":""},
                          {"water":{"mode":"nationwide","sources":["a","b"]}}):
                cfg.write_text(json.dumps({**defaults,**patch}),encoding="utf8")
                with self.assertRaises(ValueError):
                    read_config(cfg)

    def test_changed_stage_inputs(self):
        with TemporaryDirectory() as tmp:
            tmp=Path(tmp); cfg=tmp/"cfg.json"
            cfg.write_text(Path(__file__).with_name("example.delaware.json").read_text("utf8"),encoding="utf8")
            c,_=read_config(cfg); out=Path(c["outdir"]); out.mkdir()
            import hashlib
            sig=hashlib.sha256(json.dumps(c,sort_keys=True).encode("utf8")).hexdigest()
            canonical=out/"canonical_counts.csv"; canonical.write_text("original",encoding="utf8")
            (out/"counts_complete.json").write_text(json.dumps({"state":"10","config_sha256":sig,
                    "canonical_sha256":file_sha256(canonical)}),encoding="utf8")
            canonical.write_text("changed",encoding="utf8")
            with self.assertRaisesRegex(ValueError,"Canonical table changed"):
                run(cfg,"spatial")  # refuses before importing ArcPy
            (out/"tiffs.json").write_text("{}",encoding="utf8")
            (out/"spatial_complete.json").write_text(json.dumps({"state":"10","config_sha256":sig,
                    "mapping_sha256":"not-the-digest"}),encoding="utf8")
            with self.assertRaisesRegex(ValueError,"mapping changed"):
                run(cfg,"netcdf")

    def test_weighting(self):
        # Four km² block, of which one is water: a 12-person count contributes
        # four and eight to its 1 km² and 2 km² pieces. No area normalization.
        basis = land_area(4., 1.)
        self.assertEqual([contribution(12, basis, x) for x in [1, 2]], [4, 8])
        self.assertEqual(land_area(1, None), 1)
        self.assertEqual(land_area(1, 1.00001), 0)
        self.assertEqual(contribution(0, 1, .01), 0)
        self.assertIsNone(contribution(4, 0, 1))
        self.assertIsNone(contribution(4, 1, .000004))
        self.assertEqual(contribution(4, 1, .000006), .000024)

    def test_join_contract(self):
        self.assertEqual(block_id("USA_010010201001001", "01"), "010010201001001")
        for invalid in ["10010201001001", "1000000US100010201001001", "01x0010201001001"]:
            with self.assertRaises(ValueError):
                block_id(invalid, "01")
        with TemporaryDirectory() as tmp:
            table = Path(tmp)/"counts.csv"
            table.write_text("GEOID,TOTALPOP\n010010201001001,0\n", encoding="utf8")
            self.assertEqual(read_counts(table, "01", "TOTALPOP"), {"010010201001001": 0})
            with table.open("a") as f:
                f.write("010010201001001,7\n")
            with self.assertRaises(ValueError):
                read_counts(table, "01", "TOTALPOP")

    def test_netcdf(self):
        with TemporaryDirectory() as tmp:
            d, files = Path(tmp), {}
            for i, var in enumerate(VARIABLES):
                path = d / f"{var}.tif"
                files[var] = path
                # Distinct masks for count and area; deliberately vary declared
                # sentinels as in geographic releases (positive or negative).
                nodata = -float("inf") if i%2 else 1.79e308
                data = np.array([[0., i+.125], [i+.5, i+1.]], dtype="float64")
                data[1, 0 if var in COUNTS else 1] = nodata
                with rasterio.open(path, "w", driver="GTiff", width=2, height=2,
                                   count=1, dtype="float64", nodata=nodata, crs="EPSG:4326",
                                   transform=from_origin(-75, 39, 1/240, 1/240)) as ds:
                    ds.write(data,1)
            out = write_netcdf("synthetic", files, d/"example.nc")
            with netCDF4.Dataset(out) as nc:
                self.assertEqual(set(nc.variables), set(VARIABLES) | {"x","y","spatial_ref"})
                self.assertEqual(nc["x"][0], -75+0.5/240)
                self.assertEqual(nc["y"][0], 39-0.5/240)
                for var in VARIABLES:
                    with rasterio.open(files[var]) as tif:
                        expected = tif.read(1, masked=True)
                    actual = nc[var][:]
                    np.testing.assert_array_equal(np.ma.getmaskarray(actual), np.ma.getmaskarray(expected))
                    np.testing.assert_array_equal(actual.compressed(), expected.compressed())
                    self.assertEqual(nc[var]._FillValue, FILL)
                    self.assertEqual(nc[var].units, "count" if var in COUNTS else "square_kilometres")
            with self.assertRaises(FileExistsError):
                write_netcdf("synthetic", files, out)
            with rasterio.open(files["AUND1"],"r+") as tif:
                tif.transform = from_origin(-75+.5/240,39,1/240,1/240)
            with self.assertRaisesRegex(ValueError, "drift"):
                write_netcdf("synthetic", files, d/"bad.nc")
            self.assertFalse((d/"bad.nc").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
