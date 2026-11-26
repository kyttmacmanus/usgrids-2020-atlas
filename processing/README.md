# USGRIDS 2020: geography and national scientific processing

This scientific-code candidate creates the 2020 USGRIDS products **for one jurisdiction at a time**: 29 single-band modeled count GeoTIFFs, two area GeoTIFFs, and a NetCDF4 file containing all 31 variables. A single state configuration selects a jurisdiction from the 50 states, the District of Columbia, or Puerto Rico. Coordinates are longitude and latitude in WGS84. Counts are fractional estimates on this grid, not Census-published counts at grid-cell level.

The **national workflow** takes the 52 component sets in FIPS order and constructs
31 national GeoTIFFs and one national NetCDF. See [NATIONAL.md](NATIONAL.md) for
the ArcGIS aligned-grid SUM, NoData, overlap and Alaska longitude treatments and
storage requirements. Neither workflow builds or deploys the
[Scientific Atlas](https://github.com/kyttmacmanus/usgrids-2020-atlas). The
[Harvard Dataverse CIESIN collection](https://dataverse.harvard.edu/dataverse/CIESIN)
is the intended data archive, not a verified download link to the 2020 dataset.
Do not assume public access to the exact geometry until a record is identified.

To reproduce a jurisdiction, you need its **actual block geometry, water treatment and grid**, not just a published state total or a chosen bounding box. See [INPUTS.md](INPUTS.md) for acquisition and grid requirements, [SOURCE_PREPARATION.md](SOURCE_PREPARATION.md) for Census tables, and [ALASKA.md](ALASKA.md) for the distinct dateline route. The example paths in `example.delaware.json` are placeholders, not downloads or a preassembled project. Scientific data are not embedded in the source tree.

## Start here

1. Prepare the 2020 DHC raw tables for the selected geography, using the source preparation instructions. Select the block polygon feature class with the correct historical WGS84 coordinates and a text GEOID field. Supply the PIXELID grid and the correctly prepared area water.
2. Copy `example.delaware.json` to your own configuration directory and edit its paths and FIPS. Paths are relative to the configuration file unless absolute. The output directory must **not exist** and must be separate from the inputs. Its parent directory must exist. Choose a local disk with sufficient space for temporary and saved geometries, rasters and NetCDF. Use `--stage check` to check the configuration syntax. It does not open the inputs or test your GIS license.
3. Start the workflow in a licensed ArcGIS Pro Python environment (release reference: ArcGIS Pro 3.7.1, Advanced). Source preparation uses the Python standard library. NetCDF output needs `numpy`, `rasterio` and `netCDF4`. If these are installed in a separate Python environment, set `netcdf_python` to **that interpreter's executable path** in the JSON. No interpreter search, sign-in, dependency installation or download is performed by the orchestration command.

```text
python usgrids.py my_state.json --stage check
python usgrids.py my_state.json --stage all
python usgrids.py example.national.json --stage check
python usgrids.py example.national.json --stage spatial --variable TOTALPOP
```

The last command produces **one full-extent national TOTALPOP GeoTIFF**; it does
not create a national NetCDF. Use a separately configured fresh output directory
and `--stage all` only when you intend to build the complete national product.
For a geography, `all` is the default. Alternatively, run each stage separately,
keeping the same configuration:

```text
python usgrids.py my_state.json --stage counts
python usgrids.py my_state.json --stage spatial
python usgrids.py my_state.json --stage netcdf
```

Only `spatial` requires ArcPy. Use a normal command-line Python process with no inherited map-session environment overrides. The standard allocator uses ArcGIS tools for geometry, geodesic area measurement, tabular `Statistics`, and rasterization; many apparently equivalent overlay substitutions change small coastal or border contributions. Alaska additionally needs the specialized grid-domain inputs named in its guide. Never process Alaska by selecting a neighboring state's ordinary settings.

## Configuration and outputs

| Key | Meaning |
| --- | --- |
| `state` | Two-character Census state FIPS, e.g. `"10"`, `"11"`, `"72"`. The keys, expected number of blocks and fingerprints are in `geographies.csv`. |
| `source` | Local official DHC data in an accepted layout; see `SOURCE_PREPARATION.md`. This must be the complete block universe, not just populated blocks. |
| `blocks`, `geoid_field` | Polygon feature class and its original block ID field. Preserve leading zeros. Plain 15 digits, `USA_` + 15 digits, and `1000000US` + 15 digits are recognized for geometry joins. Counts must have one exact match per polygon. |
| `fishnet` | Authoritative PIXELID polygon grid; for Alaska only, see the supported domain alternatives in `ALASKA.md`. A generic 15-arc-second grid does not establish matching extent, cell centers or IDs. |
| `water` | Object with `mode` and `sources`. `prepared`: one exact, historical state-clipped polygon layer; `nationwide`: one historically ordered merged TIGER 2022 area-water polygon source; `ordered_components`: ordered list of nationwide **extracted** TIGER 2022 polygon layers. For `ordered_components` follow the full nationwide order in `INPUTS.md`, including water across state boundaries. Do not pass a state-only list or substitute a current water service. |
| `county_field` | Optional field for within-state partitioning. In standard processing, Minnesota, Oklahoma and South Carolina default to `COUNTYFP20` because their products require the county overlay route. If the same code is named differently on the source, name it explicitly. Do not partition a different state merely to speed up a run without first testing grid equivalence. |
| `alaska` | Alaska only: specify its actual reference lattice and source type, or its paired historical area masks, as documented in `ALASKA.md`. |
| `outdir`, `netcdf_python` | New output folder and optional separate interpreter for the NetCDF stage. |

`counts` writes `canonical_counts.csv` and a state/config receipt. `spatial` writes 31 TIFFs within `geotiff/`, retains its working geodatabase(s), and writes `tiffs.json`. The TIFF **mapping keys**, not filenames, define scientific variables. `netcdf` writes `usa{postal_abbreviation}_31vars.nc`. Finished stages write JSON completion receipts. Content hashes of the generated canonical table, TIFF mapping and individual TIFFs are checked at the stage boundaries. The final NetCDF is closed before publication to its output name via a create-new hard link (use local storage supporting hard links, e.g. NTFS). A failed stage never means a full state succeeded. Prior products are not overwritten. For an interrupted spatial build, use a fresh run and retain the previous folder for inspection; this candidate is not an automated checkpoint-recovery service. Do not change the external GIS source files between stages: the configuration fingerprints their paths, not every file inside a geodatabase.

## What is calculated

For every block, obtain 29 nonnegative integer counts from the specified 2020 DHC fields. [variable_definitions.csv](variable_definitions.csv) gives the formulas, universes, units and source tables. For example, `TOTALPOP` and `OCC` have different universes; an occupied housing unit is not a person.

On the standard spatial path a `Clip(blocks, nationwide_water)` in WGS84 supplies the state water when not already supplied. For each block and each unranked block–fishnet piece:

1. Measure geodesic areas in square kilometres; intersect with state water and subtract the measured water area. Block water is stored in a single-precision field; piece water is double precision. Missing joined water is zero; negative residual land is clamped to zero.
2. For a block with `block_land > 0` and a piece with `round(piece_land, 5) > 0`, allocate `(block_count / block_land) * piece_land`. Rounding is an eligibility test only. Do not normalize residual area to the census total; not every geometry can receive a count. A zero count on eligible land remains numeric zero. NoData means the raster has no value there; it is not a count of zero.
3. Sum the pieces by `PIXELID`, join to the fishnet, and rasterize at cell centers with a `0.00416666665`-degree cell size. `PIXEL_LAND` and `PIXEL_WATER` are separate sums of square kilometres; they are not independently rounded counts and are not substitutes for the geometry used to allocate counts. For the county route select whole blocks and intersecting whole grid/water features, and aggregate pieces across county boundaries before rasterization.
4. Preserve all 31 grids on the common lattice in NetCDF4. The converter checks dimensions, orientation, CRS and four-corner alignment (maximum drift `1e-7` pixel), respects the distinct source mask of each variable, and keeps numeric zeros and Float64 values without resampling. `x` and `y` are pixel centers, `y` decreases southward, and each scientific variable links to `spatial_ref`. NetCDF uses shuffle and lossless zlib compression at level 4; the source TIFF compressor need not match the NetCDF compressor.

## How to check a result

The NetCDF mapping variable explicitly names `latitude_longitude` as well as
storing the WGS84 WKT. This metadata on newly written files is descriptive; it
does not transform the grid or change counts, areas, or NoData. A conventions
declaration alone is not a full CF compliance test.

In the NetCDF environment run `python -m unittest discover -v`. The small tests exercise parsing, count arithmetic, allocation eligibility, NoData/zero distinction and format conversion without a licensed ArcGIS session. They are not an end-to-end GIS acceptance test. For a licensed geography run compare a new directory against an independently retained product: CRS, extent/transform, dimensions, full NoData mask, valid zero positions, per-cell differences by variable, state totals, and summary error. Compare each NetCDF variable's mask and exact values with its **own** input TIFF. Never certify a grid from totals, thumbnails or matching units alone.

The portable NetCDF fixtures were exercised with Python 3.11.9, NumPy 2.4.6, Rasterio 1.4.4 and netCDF4 1.7.4. For a separate, clean Python 3.11 environment, `python -m pip install -r requirements-netcdf.txt` installs those tested versions; do not replace packages in the licensed spatial environment merely to run the NetCDF step. The national component-order catalog and count preparation use only the standard library.

Historical products can contain retained and newly allocated surfaces, and GIS overlay/rasterization can differ with input geometry, processing environment or ArcGIS version. Do not claim byte identity for a complete rerun solely because the methods and source tables agree. The processing command does not deploy the Atlas or publish data. See [ATTRIBUTION.md](ATTRIBUTION.md) for source and rights status.
