# Explorer distributions and comparison view

The explorer uses the original map images, 31 immutable layer partitions and their original classification records. The homepage and vector identity are retained. `Compare maps side by side` opens `compare.html`; no map service, raster arithmetic or new framework is used.

## Classifications

The user-facing name **Global positive quintiles** corresponds to the unchanged `shared` mode, image names and record identities. `c=shared` remains valid; `c=global` is accepted and canonicalized to `shared`. The same aliases work for `c1` and `c2` on comparisons.

Fixed count classes use the existing predetermined numeric boundaries. Local positive quintiles use positive values within one geography. Global positive quintiles use pooled positive values from the 52 geographic components; the national composite is excluded from fitting. Global denotes the USGRIDS study domain, not the world. Valid zero and NoData remain separate.

The two area variables retain their existing Local and Global classifications. No validated fixed area thresholds exist; none have been invented. The information control explains this distinction. It opens on hover, click, Enter/Space and touch; Escape closes it. Popups stay within the viewport.

## Two distributions

`Grid cells` is the default. It shows each class's exact valid-cell count and percentage of all valid cells. `Allocated values` shows the actual original Float64 values summed within each class and the percentage of the total valid allocated value. Switching views retains the map selection. The `d=values` parameter can retain the value view on refresh.

Units are allocated persons for demographic/occupied-housing population variables, allocated households for HOUSEHOLD, allocated housing units for HHUNIT/OCC/OWN/VACANT/HU1P, and km² for the two area variables. Valid zero has its real cell frequency and an allocated-value sum of zero. NoData is excluded from both distributions; its exact count remains in expandable provenance. If an allocated total is zero, its value percentages are undefined rather than fabricated as percentages.

Values are never estimated from preview pixels, counts, midpoint approximations or colors. The read-only analysis uses each frozen corrected source GeoTIFF's path and SHA-256 from the original metadata and verifies the frozen release manifest:

`829b327fb2950d37c9c3932061d501bd6447ecd4adecdfefe3ed2b4800860cc1`

All available modes are classified in the same deterministic raster pass, with bounded 1024×1024 windows, native masked reads, Float64 boundaries and original interval semantics. No positive Alaska NoData sentinel is treated as data. NumPy pairwise Float64 block sums are combined with `math.fsum`; the predeclared reconciliation bound is `abs(error) <= 1e-9 + 1e-12*abs(reference total)`, matching the existing frozen total-reconciliation policy. Every bin count must match the authoritative histogram exactly. Unexplained mismatches stop processing and are never published as verified values.

The separate private process checkpoints each completed geography-variable raster, including source hash, file state, input signature, grid, units, original classification IDs, counts, full-precision sums and verification results. A single-process lock prevents duplicate writers. A compatible restart reuses verified checkpoints; it does not reacquire or regenerate inputs. The generator, restart commands, pilot evidence and resource measurements are supplied in the review handback rather than publishing private processing files.

The pilot gate precedes full production and covers Delaware and Puerto Rico TOTALPOP, Hawaii HAWPI, Delaware land and water, Alaska TOTALPOP, and the actual national population, land and water rasters. Pilots independently reproduce interval membership with direct predicates and `math.fsum` of original values.

## National reconciliation

National summaries are read from the actual national rasters using their own masks. Component histograms are not added. National TOTALPOP has 62,967,001 valid cells; component valid-cell counts sum to 63,055,358. Identical allocated totals do not make those histograms interchangeable.

The national allocated TOTALPOP sum is 334,733,492.4976411, versus the supplied corresponding Census benchmark of 334,735,155. The difference is about 1,662.5024 people, or 0.00049666%. The frozen `validation/NATIONAL_RECONCILIATION.csv` records zero national-versus-component allocated-total residual. Historical Puerto Rico source-conservation diagnostics and retained allocation eligibility rules establish that allocation residuals exist, but the reviewed evidence does not uniquely attribute the entire national benchmark difference to rounding, masking or unallocated geometry. The site states no unproven single cause and does not modify the rasters to match the benchmark. The small profile footnote is limited to national TOTALPOP; Methods provides the details.

## Loading and failure behavior

Derived summaries live separately under `site/assets/data/class-values/`: one compact JSON per variable and a coverage/checksum index. Visitors fetch only the selected variable's summary. Original layer partitions are not edited. The browser checks summary SHA-256, source identity, class IDs/edges, exact counts, totals, units and zero semantics before enabling Allocated values. Missing, mismatched or unverified summaries retain the correct Grid cells view with an availability notice. There are no estimated substitute sums.

## Comparison

The default compares Delaware TOTALPOP with Puerto Rico TOTALPOP in Global classes. Each labeled panel has separate selectors, original map, numeric legend, units, universe, concise profile and full-explorer link. Desktop panels sit side by side and small screens stack them. Geographic framing and inset notes are retained; equal display sizes do not imply equal scales.

Same-variable comparisons prefer identical Fixed or Global boundaries. Local comparisons remain available with a quiet explanation that colors can represent different numeric values. Different-variable comparisons explain that colors do not establish comparable units, universes or meanings. Separate legends are always retained.

Example:

`compare.html?g1=10&v1=TOTALPOP&c1=shared&g2=72&v2=TOTALPOP&c2=shared`

Selections update browser history; refresh, back/forward and Swap A/B preserve the expected states. Invalid parameters fail clearly without substituting unrelated maps. Selection epochs prevent stale asynchronous responses from replacing newer selections. Panel labels, field labels, keyboard controls and live announcements identify both maps.

## Verification and deployment

Run `python tools/verify_site.py`. It verifies the full deployment manifest and original site invariants, then invokes `tools/verify_class_values.py`. The additional verifier requires complete 1,643-layer/31-variable coverage, independently read national inputs, exact bin counts, frozen source/class identities, value-total reconciliations and interval-sum bounds. `tools/scientific_asset_lock.json` fixes the SHA-256 of all 4,857 original scientific maps/metadata files at baseline commit `ae544cef48e0016164fcc64ee7be128abf61f646`.

Only static site assets are uploaded by the existing manual Pages workflow. Its exact-SHA, public-visibility and environment protections remain unchanged. No source rasters, NetCDFs, Shapefiles, private checkpoints or credentials are deployed. This scientific preview introduces no DOI, registered archive file IDs or working scientific download claims.
