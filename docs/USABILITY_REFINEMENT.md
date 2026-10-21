# Atlas usability and visual refinement

This pass changes website presentation and readable documentation. It reuses all 4,823 map images, original scientific metadata and existing verified class-value summaries. No source rasters, classification fits, derived sums, masks or separate Dataverse deliverables are processed or modified.

## Explorer and comparison

The main navigation remains Home, Explore Maps, Science & Methods and Data Access. The homepage retains its hero, national map composition, scientific caption, numeric legend and three information blocks. Compare Maps is a secondary Explorer action, with the current map in Panel A. Its existing independent selectors, legends, Swap A/B, history and mobile layout remain. A modest return link follows Panel A.

Find data for this map lands at the selected geography/variable catalog with the matching GeoTIFF and 31-variable NetCDF, with access to the complete geography catalog and its grouped block Shapefile where applicable. The URL carries the map classification/distribution for return; classification does not change the scientific files. No unregistered scientific download is enabled.

The allocated-value distribution is the default, using the already-verified sums and variable-aware population/household/housing-unit/land/water labels. Explicit d=cells and d=values remain valid and canonical URLs retain the actual displayed measure. Missing or invalid value summaries show a clear notice and truthful Grid cells fallback. Zero, NoData, exact intervals and scientific denominators are unchanged.

Prominent labels are Fixed classes, Local quintiles and Global quintiles. The fixed/local/shared keys and global alias are retained. Positive-only fitting, tied boundaries, zero/NoData separation and the 52-component Global domain remain explicit in shared help.

## Contextual explanations

One reusable native details/summary component serves classification, distribution, legend/masks, map comparison, file formats, checksums, eligible land and geographic resolution. It supports hover, click/tap, Enter/Space, Escape with focus return, outside-click dismissal and viewport-clamped scrolling panels. Primary labels, units, separate legends and map-scale qualifications remain visible.

GitHub Issues remains the primary feedback channel, with the requested public-visibility privacy note and unchanged text-template alternative. No feedback or invitations are sent automatically.

## Readable technical records

documentation.html renders all four records in scientific-documentation.json, preserving each complete source text and SHA-256, including critical scientific exceptions. The approved national reconciliation note is retained separately with its baseline source identity. Section navigation, search, stable fragments, code expressions and scrollable tables make the records readable. Source JSON remains a secondary machine-readable resource. Historical administrative wording is identified as source context; current citation/author/publication guidance remains separate and unchanged.

The deterministic builder is tools/build_readable_documentation.py. tools/verify_refinement.py independently compares rendered source text, dictionary rows, protected source hashes, scientific presentation/verification functions and unchanged map assets. It does not run GIS or scientific statistics production.

## Interface palette and contrast

Navy #29334B; muted plum #77395B; restrained warm gold #D2A15E; warm off-white #FAF7F3. Supporting gray is #5B5E68. The subtle national-map panel is #EEEAE5, preserving the visual difference between transparent NoData and white zero pixels. The approved vector logo is unchanged. Scientific swatches, images and distribution-bar colors continue to come from their original metadata.

UI contrast checks use the W3C relative-luminance formula and unrounded thresholds: normal text at least 4.5:1 and control/focus cues at least 3:1. See the [text contrast guidance](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html) and [non-text contrast guidance](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html). Scientific color ramps are preserved; these scoped checks do not claim a complete accessibility certification.

## Reproduction

Run python tools/verify_site.py for the full scientific-preservation and editorial/refinement checks. Browser scripts and before/after/live screenshots accompany the private handback. The existing exact-commit manual Pages workflow and all public-visibility/environment safeguards remain unchanged.
