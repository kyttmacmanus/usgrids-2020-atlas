# USGRIDS website publication guidance

This editorial guidance applies to the existing scientific review website. It does not alter the frozen scientific release or the separate Dataverse preparation stream.

## Provisional dataset citation

Owner-selected author order: Kytt MacManus; Hieu Tran; Juan Martinez; Alex de Sherbinin; Greg Yetman.

MacManus, K., Tran, H., Martinez, J., de Sherbinin, A., & Yetman, G. (2026). USGRIDS 2020: Gridded 2020 U.S. Census Demographic and Housing Counts and Land/Water Area at 15-Arc-Second Resolution [Dataset, provisional citation]. Center for Integrated Earth System Information (CIESIN), Columbia University. Harvard Dataverse (publication pending).

Proposed dataset citation available; Harvard Dataverse publication and DOI pending.

The proposed 2026 citation year remains provisional and is distinct from the 2020 Census vintage. Final publication year, registered version, DOI, license and repository identity must come from actual archive registration. The proposed citation does not imply Harvard registration or approval.

## Interactive atlas citation

MacManus, K. (2026). USGRIDS 2020 Scientific Atlas [Interactive web atlas, scientific review preview]. Center for Integrated Earth System Information (CIESIN), Columbia University. https://kyttmacmanus.github.io/usgrids-2020-atlas/

## Funding and Acknowledgments

The preparation, validation, and dissemination of USGRIDS 2020 were supported in part by the Columbia University Research Stabilization Fund (Round 2).

## Editorial source of truth

`site/assets/data/editorial.json` supplies the author order, both citations, funding sentence, publication status, dictionary browsing categories and review cases. Methods, Data Access and the public Review Guide use the same configuration. Do not edit frozen scientific metadata to establish provisional editorial credit.

The existing scientific-documentation JSON retains historical scientific records and their checksums. Publication-status language embedded in retained source records is historical; this guidance supplies current editorial status without changing those protected records.

## Products and delivery

53 geographies; 31 variables (29 counts and two areas); 15-arc-second EPSG:4326 grid. The scientific catalog preserves 1,643 GeoTIFFs, 53 NetCDFs with all 31 variables, and 260 Shapefile components forming 52 Census-block polygon datasets. This is 1,956 physical scientific files and 1,748 logical products after grouping Shapefiles. The national composite has no block Shapefile dataset.

Scientific files are being prepared for publication in Harvard Dataverse; downloads are not yet available.

The catalog enables a future file link only with a verified REGISTERED status and actual HTTPS Harvard Dataverse file URL; no pending file receives a download action. A verified archive URL and registered identity must be supplied before activation.

## Allocation equation verification

The conceptual equation is Pc = sum_b[Pb * (Abc / Ab)] for eligible contributions. Ab is the positive geodesic block-land area `max(GEODESIC_AREA - GEODESIC_WATER, 0)`. Abc is the block/grid-intersection land after the same water-source treatment. The historical density is count/GEODESIC_LAND, and intersected counts are density*PIXEL_LAND only under the retained rounded-land eligibility. The denominator is neither ALAND20 nor the sum of only surviving rounded intersections. The zero-density/rounded-zero-land null branch and documented canonical-zero mask qualification remain explicit.

Read-only evidence reviewed: frozen corrected-release documentation/METHODS.md and documentation/REPRODUCIBILITY.md, release_work/validation/release_completion/HISTORICAL_ALLOCATION_METHOD.md and HISTORICAL_ALLOCATION_PARAMETERS.json, the frozen NO_RANK intersect variant, and the retained production calculate_density/calculate_count functions. The historical parameter document includes obsolete phase statuses; its method definitions are corroborated by the final frozen documentation. No source code is executed and no scientific processing occurs in this revision.

## Review and feedback

Public review guide: https://kyttmacmanus.github.io/usgrids-2020-atlas/review.html

Compare maps: https://kyttmacmanus.github.io/usgrids-2020-atlas/compare.html

Primary feedback: https://github.com/kyttmacmanus/usgrids-2020-atlas/issues/new?template=scientific_review.yml (GitHub account required).

Alternative: https://kyttmacmanus.github.io/usgrids-2020-atlas/review-feedback.txt — download, complete, and share through the reviewer's own channel. No automatic feedback or invitation is sent.

## Verification

Run `python tools/verify_site.py`. Its existing original-scientific-asset lock is unchanged. The editorial preservation lock protects the derived-statistics JSON, original CSS, main stylesheet, logo/favicon and exact manual deployment workflow. The owner-authorized usability refinement updates presentation code under a recorded scoped exception; the additional refinement lock retains every pre-existing scientific/editorial JSON file and map, the original scientific verification functions and exact chart-bin renderer. Homepage content/layout remains identical after normalizing its approved classification-label change. Browser checks and before/after screenshots accompany the private review handback.
