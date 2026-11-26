# Obtaining the matched analysis geometry

The source code does not contain Census blocks or fishnet polygons. A fishnet
is an indexed collection of analysis cells, not a state's boundary rectangle.
The ordinary grids, the Alaska sparse grid and the 52 prepared block layers
are distinct scientific inputs. Inputs must not be substituted based only on
place name, nominal cell size, a matching FIPS, or a bounding box.

**Access status:** the matching geometry is prepared or being verified for a
separate scientific data deposit. No approved public deposit or persistent
file link has been verified for those packages. The files are not in GitHub;
do not interpret this guide as an already accessible public download.
Release metadata must provide the version-specific Dataverse DOI/file links,
byte sizes and trusted digests before independent public acquisition is claimed.
The U.S. Census [2022 AREAWATER archive](https://www2.census.gov/geo/tiger/TIGER2022/AREAWATER/)
and [2020 Census DHC](https://api.census.gov/data/2020/dec/dhc.html) are separate,
public inputs. They do not supply the CIESIN prepared analysis fishnet.

## Once the geometry deposit is available

1. Follow the deposited geography inventory to the original data files. For an
   ordinary state, DC or Puerto Rico obtain the corresponding compact exact grid
   ZIP and common empty native fishnet template. Keep both as ZIP files.
   For Alaska obtain the single signed Int32 PIXELID TIFF instead. For blocks,
   use the original complete block Shapefile family from either matching
   USGRIDS scientific ZIP and its geography-specific ordered-block specification.
   For states other than Puerto Rico also obtain the empty native block template.
   Never treat an operational file, URL supplied by an untrusted party, or a
   different input edition as equivalent.
2. If the repository supplies direct HTTPS original-file links, the optional
   `obtain_geometry.py URL NEW_FILE --bytes EXPECTED_BYTES --sha256 EXPECTED_HASH`
   streams and verifies a single file. Use the exact published numbers, not the
   size or hash calculated from an untrusted download. It does not need an
   account, accepts only HTTPS redirects and refuses to replace existing files.
3. In an environment with Python 3.11, NumPy, pyogrio (tested 0.13.0 with
   GDAL 3.12.4) and its pandas/GeoPandas dependencies, run:

   ```text
   python reference_geometry.py USGRIDS_2020_DE_exact_fishnet.zip --native-template USGRIDS_2020_native_fishnet_template.zip --new-gdb de_grid.gdb
   python reference_blocks.py blocks_state_10.shp DE.json --native-template USGRIDS_2020_native_block_template.zip --new-gdb de_blocks.gdb
   ```

   Use `de_grid.gdb/cells` and `de_blocks.gdb/blocks` in the state processing
   config, with `geoid_field=GEOID20`. These are brand-new outputs. Include the
   matching `.shx`, `.dbf`, `.prj` and `.cpg` next to the input Shapefile.
   The names in these examples are local names for exact inputs, not remote URLs.
   You may pass the original geography-specific scientific ZIP instead of the
   `.shp`: the reader uses only the uniquely named five block components in
   its `Shapefile/` folder and does not unpack the accompanying rasters.
   For PR use `reference_blocks.py blocks_state_72.shp PR.json` to verify, then
   supply the Shapefile directly: that was the actual PR input.
4. Alaska uses a sparse grid, including two longitude domains: use
   `fishnet_kind=pixelid_raster` and supply the **same signed-ID TIFF** as both
   the top-level `fishnet` and `alaska.grid_reference` in the config. This is
   an existing geometry input, not a land/water or population count surface.
   See [ALASKA.md](ALASKA.md).
5. A nonzero status, changed SHA, differing geometry/ID, precision mismatch or
   missing sidecar is a failed acquisition. Quarantine any partially restored
   data, verify the input versions, and start with new output paths. Do not
   continue allocation with an unverified geometry.

## Why these formats

Ordinary grid packages preserve each polygon's actual ordered WKB vertex bits,
native OID and signed PIXELID. The binary differences in the ZIP reduce file size;
they are reversed as integer arithmetic, not interpolated coordinates. The
reader verifies three independent source digests and reopens the restored
FileGDB. The two tiny native schema templates contain no original feature rows.
The templates preserve the exact XY storage domain and tolerance, quantities a
generic GIS export can round even when the displayed EPSG code is unchanged.
Only geometries and scientific identifiers are supplied, not historical
demographic attributes. The count processing step uses the authoritative DHC
table, not block attributes from another edition.

The nominal global lattice uses 86,400 columns; signed IDs relate to the global
row and column by `(row - 18720) * 86400 + column`. This relationship is for
validation and Alaska placement. It is **not** an instruction to synthesize
ordinary polygons. Verify the actual footprint, object order, and saved vertices.
The 17-digit-scale native precision check is deliberately strict. The companion
products store separate valid/NoData masks; a valid zero count is not an
outside-grid cell. The geodatabase import operation consumes more local disk
space than the compact transfer file.

These data are separate from any software license. Attribute the prepared
analysis geometry to its documented producers and retain the Census and other
upstream attributions and source conditions from the approved dataset record.
