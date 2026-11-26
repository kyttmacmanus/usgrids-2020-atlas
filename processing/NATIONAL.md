# Building the USGRIDS 2020 national composite

This workflow adds finished geography rasters on their original WGS84
15-arc-second lattice. It does not repeat block allocation. It requires
all **50 states, Washington DC, and Puerto Rico** (52 geographic components,
1,612 input TIFFs). The result contains 29 gridded counts in count units and
two physical areas (`PIXEL_LAND`, `PIXEL_WATER`) in square kilometres.
It does not inset Alaska or Hawaii, exclude territories by default, or
construct the national product from CONUS alone.

## Prepare inputs

The configuration in `example.national.json` expects each complete state
run under `completed_geographies/<two-digit FIPS>/`, with its `tiffs.json`,
`spatial_complete.json` and 31 GeoTIFFs. To produce components in this form,
set each state configuration's `outdir` to the appropriate FIPS directory
*before* running its workflow. National processing verifies state identity,
the map and hashes of the state outputs. Do not mix different years or
generations of scientifically incompatible components.

If using independently obtained USGRIDS **scientific TIFF archives** instead,
set `"layout": "archive_tiffs"`. Extract each jurisdiction's 31 TIFFs into
`component_root/<FIPS>/`, immediately beneath that directory. Preserve names:
e.g. `10/usaDE_TOTALPOP_CNT.tif`, `10/usaDE_PIXEL_LAND.tif`. Do not add a
second copy of a state or a national TIFF as an additional component.
The filename identifies the variable; the input grid and values must be the
corresponding, independently verified scientific products. No reference
national raster is used to create the new national composite.

## Run

Use the public CLI from this directory. Start with a new output directory
(its parent must exist). Use ArcGIS Pro 3.7.1 Advanced with Spatial Analyst
for the spatial stage and the documented NumPy/Rasterio/netCDF4 environment
for the format step; `netcdf_python` may name that interpreter in the JSON.

```text
python usgrids.py example.national.json --stage check
python usgrids.py example.national.json --stage all
```

The `check` stage validates the input roster/paths, reports available space
and the starting floor, and writes nothing. Split long work into `--stage
spatial` and `--stage netcdf` when needed. A complete spatial run writes the
31 national TIFFs under `outdir/geotiff` and their reconciliation receipt.
The final file is `USGRIDS_2020_NATIONAL_31vars.nc`. A different or incomplete
output directory is not reused; rerun a failed spatial stage in a new one.

### One full-extent TOTALPOP GeoTIFF

To validate the complete national extent without building the other 30 rasters
or a national NetCDF, use a new output directory and the following commands:

```text
python usgrids.py example.national.json --stage check --variable TOTALPOP
python usgrids.py example.national.json --stage spatial --variable TOTALPOP
```

Only the 52 TOTALPOP inputs are opened. The same native SUM/DATA, lossless
TIFF, component totals and final CopyRaster apply. Expect one
`geotiff/TOTALPOP_CNT_national.tif` and a `TOTALPOP_only_complete.json`
receipt, **not** a complete-national or NetCDF stage receipt. The two
commands do not read or generate a national NetCDF. For stored state TIFFs
in archive layout, other variables need not even be present.

The historical national TOTALPOP TIFF is 419,212,225 bytes (the 52 inputs
sum to 353,267,581 bytes); the uncompressed plane is about 8.87 GB. The
one-product mode requires 26,586,550,376 bytes (26.59 GB) initially free on
the output filesystem: a 15-GiB operating reserve, one full native Float64
plane, 1 GiB of additional native-working allowance and 512 MiB for a
compressed file. A separate system temp volume needs 7 GiB (7,516,192,768
bytes), including a 5-GiB reserve. If both locations are the same filesystem,
require 28,734,034,024 bytes there. These are conservative starting floors,
not measured peak usage or a guarantee against external disk pressure. Native
TIFF saves can use far more than their final size. The native result is first saved and LZW-compressed
on the output volume. Checksummed, closed intermediate bytes and sidecars are
preserved under a new system-temp directory before final CopyRaster, so two
compressed copies do not both need to occupy the output volume. Set your
system temporary directory to a suitable local volume before starting Python.
Keep scratch free throughout: additional parallel GIS workers or other
processes can change the actual available space.

Allow **at least 39.84 GB free** for starting the spatial stage (prefer more,
including separate room for the 1,612 source TIFFs and GIS scratch). At the
reference sizes 31 lossless national TIFFs occupy 9.81 GB and the National
NetCDF another 5.05 GB; one uncompressed Float64 plane is 8.87 GB. The
operating reserve alone is 15 GiB. Allow longer than a single state: each
variable is read and summed across 52 components and a very wide sparse
national grid, and the NetCDF writer visits all 31 arrays. No benchmark for a
new full run on the reader's computer is implied.

## Scientific operation and verification

For a cell with at least one valid source, the national value is the sum of
the valid geographic values in that cell. If no geography contributes a
valid value, the result is NoData. A valid numeric zero is **not** absent.
At boundaries this adds overlapping source contributions; it neither takes
the first nor averages them. No normalization to state totals is applied.
Geography TIFFs are passed in two-digit FIPS order through Puerto Rico (72).

The native operation is `arcpy.ia.CellStatistics(inputs, "SUM", "DATA",
"SINGLE_BAND", 90, "AUTO_DETECT")` in WGS84 with `extent="MAXOF"`. The
last two native arguments are retained from the original call and do not
request a percentile instead of a SUM. The original grid registration is
left to this *same native operation*: there is no explicit reproject, snap,
warp, interpolate, shift-to-integer, mosaic blend or substitute sampling step.
Because serialized component origins differ slightly, exact binary
coincidence of every corner is not assumed. Misregistered input fails closed.

Alaska enters this step as **one final geography file per variable**, already
assembled across its two longitude domains. Never add eastern/western
county parts to the national sources as well. PR remains at its native
position, establishing the southern edge of the `MAXOF` extent. The 2020
national rectangle is 86,195 columns by 12,863 rows, with NoData between
observed regions. Each output is Float64; GeoTIFF compression is lossless LZW.

For each variable the spatial stage independently totals the 52 geographic
inputs and the national result. It reads 32-row windows from south to north,
ignores native NoData, uses a NumPy Float64 sum inside each window, and
combines window totals (then component totals) using `math.fsum`. Unknown
or infinite values do not silently become valid zero. The accepted difference
is `abs(national - component_sum) <= 1e-9 + 1e-12 * abs(component_sum)`
in the variable's own units. Passing totals alone cannot detect spatial
errors. Compare alignment, all cell masks, zeros and values to a reference
when validating a new installation. Converting all 31 reconciled TIFFs to
NetCDF preserves their own masks and native values without resampling.
