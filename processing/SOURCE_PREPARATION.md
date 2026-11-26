# Preparing the 2020 Census count inputs

Use the **2020 Decennial Census Demographic and Housing Characteristics File (DHC)**, at **Census block** geography (summary level 100), not ACS estimates, redistricting tables, tract aggregates or a later-year geography. One accepted block key is 15 ASCII digits: state (2), county (3), tract (6) and block (4), concatenated in that order. The counts table retains leading zeroes. A row with a missing count is not a block with zero residents.

The source, geographic hierarchy and source-column descriptions are available from the Census Bureau:

- [2020 DHC API documentation](https://api.census.gov/data/2020/dec/dhc.html)
- [Block query examples, including all tracts within a county](https://api.census.gov/data/2020/dec/dhc/examples.html)
- [DHC groups and source-variable definitions](https://api.census.gov/data/2020/dec/dhc/groups.html)
- [Census API key signup](https://api.census.gov/data/key_signup.html)

## Start with a complete official block table

From this directory, on Python 3.11:

```console
python prepare_counts.py --geography DE --fetch-to dhc_DE.csv
python prepare_counts.py --geography DE --input dhc_DE.csv --output counts_DE.csv
```

If you already have the source table, run only the second command. Substitute any of the 52 FIPS codes, postal abbreviations or full names listed in `geographies.csv`. DC and Puerto Rico are components; "national" is not a state source table. Each output path must be new, its parent directory must exist, and the filesystem must support hard links. The code stages the file on the same volume and reveals it only after validation succeeds.

Only online retrieval needs the personal `CENSUS_API_KEY` environment variable supplied by your session or secret manager. Do not put a key in a script, command-line argument, public archive or log. The fetcher uses the official HTTPS endpoint, first enumerates counties, then queries blocks within each county, requesting the necessary source fields in batches of up to 45. Field batches can arrive in different row orders. The code joins the responses by GEOID and rejects mismatched or duplicate keys before writing the county. Exhausted transient retries stop the operation. Re-run a failed acquisition; use the validated saved CSV for subsequent calculations. A representative county response/field-batch join is covered by offline tests; no live acquisition is implied by those tests.

`--input` takes a UTF-8 comma-delimited **wide block count table**, or a ZIP containing exactly one such CSV. It is **not** a reader for the Census segmented summary-file ZIP format. Required columns are the 95 DHC inputs obtained by expanding the 29 count expressions in `variable_definitions.csv`, plus at least one supported key representation: `GEOID` (15 digits), `GEO_ID` (1000000US plus 15 digits), or **all four** Census API component columns (`state, county, tract, block`). If multiple representations are supplied they must agree. Inputs are nonnegative integer counts. Empty, suppressed, negative or fractional counts, undocumented substitute columns, and absent blocks are not filled or estimated.

## Verify the block universe

`geographies.csv` enumerates the **public 2020 DHC block geography**, not scientific output checksums. The block count and `sorted_geoid_sha256` can be reproduced from the IDs of the direct-official DHC input tables or independently by querying only block geography and NAME:

```console
python prepare_counts.py --geography DE --verify-geography
```

The verification enumerates counties with `get=NAME&for=county:*&in=state:10`, then requests `get=NAME&for=block:*&in=state:10&in=county:<county>&in=tract:*` for each county. The digest is SHA-256 of **distinct, lexicographically sorted 15-digit GEOIDs**, each encoded as ASCII followed by one byte LF, including the last. It contains no names, counts, source filenames, paths or file checksums. Delaware has 20,198 such block IDs. Verifying both the exact key set and the length rejects an accidental substitution even if the number of rows is correct. If a different Census vintage or extract fails, investigate rather than bypassing this check. Identical coverage does not establish correct count values or spatial allocation.

## Variables and downstream joins

The output has `GEOID` followed by 29 integer count columns in dictionary order. Input row order is retained; join on `GEOID`, never on row position. Use the geography-specific block geometries and compatible keys for the spatial stage. The `variable` column in `variable_definitions.csv` identifies each canonical count; `artifact_variable` identifies the raster naming convention. `SUM(Pxx_aaaN:Pxx_bbbN)` means the inclusive sum of all source fields in one table between those two endpoints. Overlapping age and race/ethnicity variables are not mutually exclusive. For example, `WOMCHILD` means female persons aged 15–49; it does not count mothers or households with children. `VACANT` uses H3_003N; if H5_001N is supplied as an additional column it must agree, not be added. Separate exact age/race/ethnicity partitions, occupancy identities and relevant subset relationships are checked at block level.

`PIXEL_LAND` and `PIXEL_WATER` appear in the dictionary for completeness but never in the block count output. They are geodesic areas in km² per grid cell and require processing the grid–block intersections and water geometry. Census block ALAND20 and AWATER20 are distinct source measures, in m² per block; they cannot substitute for gridded areas.

Run the offline examples with `python -m unittest -v test_prepare_counts`. Import `prepare_counts(state, source, output)` to prepare an existing DHC extract without network access, or `fetch_dhc(state, output)` for acquisition. These source-data steps alone do not generate spatial products or the national composite.
