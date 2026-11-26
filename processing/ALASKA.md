# Alaska: one state on two longitude domains

Set `"state": "02"` in the geography configuration. The driver selects
`alaska.allocate_geography`. Use the same official source-count preparation
and the same historical block and prepared TIGER 2022 water inputs described
in the main guide. Use a fresh output directory on a volume with room for
county overlays, sparse arrays, domain rasters and 31 final TIFFs. An Alaska
run is not a desktop-size demonstration. Run the small unit tests first.

## Supplying the grid

Provide one of three **explicit** Alaska input configurations. Path examples
are relative to the configuration file; replace them with your inputs.

| Top-level `fishnet` | `alaska.fishnet_kind` | Other `alaska` settings |
| --- | --- | --- |
| WGS84 polygon feature class containing the signed integer `PIXELID` | `polygons` (default) | `grid_reference`: retained historical grid for its affine and crop |
| Single-band Int32 GeoTIFF with signed global cell IDs | `pixelid_raster` | `grid_reference`: retained historical grid for its affine and crop |
| Original single-band historical land-area GeoTIFF (its **mask only**) | `paired_area_masks` | `water_mask`: original corresponding water-area GeoTIFF (its **mask only**); the first input also provides the reference grid unless `grid_reference` is supplied |

For example, the Alaska-specific portion for paired masks is:

```json
{
  "fishnet": "inputs/grids/ak_historical_land.tif",
  "alaska": {
    "fishnet_kind": "paired_area_masks",
    "water_mask": "inputs/grids/ak_historical_water.tif",
    "county_field": "COUNTYFP20"
  }
}
```

The two files above describe the **original retained grid footprint**. They
are not the contemporary state water vector and do not supply geodesic land or
water values. Conversely, the top-level `water` option supplies actual
TIGER 2022 **polygons** for overlay; it is not a raster mask. Do not
substitute the new Alaska scientific output masks for the historical inputs.
The polygon option lets researchers reuse established sparse geometry. If
those geometric inputs are unavailable, do not derive a statewide bounding-box
fishnet from the block envelope: that is not the 2020 Alaska grid.

The native GIS stage requires ArcPy and NumPy. Paired-mask preparation also
requires Rasterio in that interpreter; the optional mask step writes only
an integer **ID geometry input**, never a final scientific surface. All final
rasters are written by ArcGIS. No live network access or user-specific path
is used. A fresh run refuses to overwrite its input or an existing output
directory. Intermediate files are removed only from the run's private directory
after all 31 TIFFs are written; on failure they remain available.

## How the calculation works

1. The historical lattice is north-up WGS84 with a nominal cell size of
   0.00416666665°. Its cropped dimensions are 86,195 by 4,872, but only
   18,129,391 cells belong to its sparse support. The first global row/column
   is (4450, 178). IDs use
   `(global_row - 18720) * 86400 + global_col`, not raster index or OBJECTID.
   The implementation verifies the support fingerprint, center positions and
   cell sizes; it does not create polygons for the whole rectangular crop.
2. Classify whole blocks by county. Split county 016 into western/eastern
   longitudes, giving 31 partitions from 30 counties. Do not split a polygon
   merely because the state spans the dateline: a source block whose envelope
   crosses the representation boundary is an error. Select intersecting
   sparse fishnet polygons separately for each county/side.
3. Measure geodesic block area (km²); clip by prepared state water; store
   block wet area as Float32 and dry area as Float64. Intersect the block
   polygons with local cells (no input rank override); measure intersection
   area and clipped water in double precision. Missing water for an existing
   piece is zero; dry area is `max(total - wet, 0)`. A missing piece is
   not a zero-area observation.
4. Sum all piece land and water separately by signed PIXELID. Join only the
   **local** fishnet; convert its sums with `PolygonToRaster(CELL_CENTER)`.
   Accumulate westerly area rasters by sequential `SUM` in county order.
   East contains only 016_E. Use `FIRST` between proven-disjoint longitude
   domains, plus two NoData corner anchors to preserve the global crop.
5. For counts, retain only finite pieces with block dry area > 0 and
   `numpy.round(piece_dry_km2, 5) > 0`. Compute the **unrounded** Float64
   weight `piece_dry_km2 / block_dry_km2`, then multiply the block's
   canonical count by that weight. Reduce in stable source-row order within
   PIXELID and fixed part order within each longitude domain. Shared pixels
   receive both contributions. Place one variable at a time by signed ID;
   do not average, rescale or renormalize. Valid zero counts stay zero;
   absence of eligible pieces stays NoData. Preserve the count mask independently
   of the two area masks.
6. Write 29 count and two area TIFFs (Float64, WGS84, lossless LZW). The
   shared NetCDF stage reads these TIFFs and their individual masks.

## What has been tested

`python -m unittest test_alaska` covers both longitude domains, signed negative
IDs, stable reduction, overlap/zero/NoData, the five-decimal eligibility gate,
and rejection of an invalid geographic representation. The curation review
also compared 659,362 retained intersections from three county/side partitions
to independently preserved results: all per-PIXELID count arrays matched their
original fingerprints. On the eastern Aleutian component, values, valid-zero
classes and masks of all 29 count TIFFs matched the recomputed data; the two
area fields matched to within 2.8 × 10⁻¹⁷ km² with identical masks.

Those tests validate the count kernel and retained domain representation, **not**
a new end-to-end run of ArcGIS starting from raw polygons. An independent
licensed run with the documented inputs should compare all 31 grids to the
scientific release before claiming end-to-end reproduction.
