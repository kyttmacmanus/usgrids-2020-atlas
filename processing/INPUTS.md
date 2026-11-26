# Obtaining inputs for a geography

Use a separate directory for inputs and a fresh directory for each run. The
examples are templates, not invitations to infer a grid from a place name. A
geography selects a set of Census records and a GIS processing route; it does
not set the geodetic precision of a feature class.

| Input | Obtain or prepare | Required characteristics |
|---|---|---|
| Counts | [2020 Census DHC API](https://api.census.gov/data/2020/dec/dhc.html). Use the supplied `prepare_counts.py --geography DE --fetch-to de_dhc_blocks.csv`, or supply the matching wide block CSV. | Exact 2020 tabulation-block keys; all fields used in `variable_definitions.csv`. Keep leading zeroes. Neither ACS estimates nor the 2010 Census are substitutes. |
| Block polygons | Use the prepared geography-specific USGRIDS block features from the input data provider. [2020 Census TIGER/Line](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.2020.html) documents the underlying tabulation geography. The USGRIDS geography archive also includes a block Shapefile. | WGS84 polygon, one row per 15-digit GEOID, county code available for county processing. Feature class spatial reference, XY resolution/tolerance, geometry, multipart representation and feature order matter. A generic 2020 Census download or an export to a new format is **not proved interchangeable** with the prepared production features. For PR the scientific workflow used the prepared Puerto Rico block Shapefile. |
| Area water | [2022 TIGER/Line AREAWATER archives](https://www2.census.gov/geo/tiger/TIGER2022/AREAWATER/). Download and extract the county Shapefile families; keep their names/sidecars. No newer water vintage. | All 3,222 components of the 52 included jurisdictions, in increasing five-digit county FIPS order. In the production inputs they contain 2,256,266 features. A merge of only the selected state's water can omit water across a state boundary. |
| Analysis fishnet | Obtain the supplied USGRIDS fishnet for the selected geography from the input data provider, including its CRS/precision and numeric `PIXELID`. The ordinary historical input is a feature class, not a TIFF of demographic values. | WGS84 polygon grid, one unique ID per cell, exact cell geometry and offset. The nominal `0.00416666665`-degree size does **not** determine grid origin, mask or IDs. Do not build a replacement from a rounded bounding box. Alaska has its own signed-ID grid and sparse coverage; see its configuration/guide. |

Starting from extracted water files, build a configuration next to your template:

```text
python water_catalog.py inputs/tiger2022 example.delaware.json delaware.full_water.json
python run_geography.py delaware.full_water.json --stage check
```

The first command reads existing files and writes a new JSON. It checks county
membership and sidecars, not archive authenticity. Obtain archives directly from
Census. ArcPy, not this script, merges the component polygons. A prepared
nationwide layer or a known-compatible state water clip can be reused through the
other documented water modes. A reference grid, ALAND/AWATER attribute, or a
published PIXEL_WATER value cannot stand in for water geometry.

For other input configurations see `example.puerto_rico.json` (block Shapefile),
`example.minnesota.json` (county processing) and `example.alaska.json` (sparse
signed-ID grid). In these examples the nationwide water input is the complete
merged layer, not the water for one geography.

**Reproducibility boundary:** this software package does not distribute the
prepared block geodatabases or the matched analysis fishnets. No public download
for the complete matching ordinary fishnet collection has been verified. Until
the provider deposits or identifies those inputs, the exact spatial workflow is
runnable by researchers who possess them, not yet from public Census downloads
alone. If you use a different geometry, label the result accordingly and
validate it independently before treating it as the USGRIDS grid.

See [the matched geometry input guide](GEOMETRY.md) for the lossless ordinary
fishnet packages, the original Alaska signed-ID grid, and how to verify and
recover the native-precision block geometry from the scientific Shapefile.
