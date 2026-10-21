# USGRIDS 2020 — Scientific Review Preview

A static scientific atlas for review of the corrected 2020 Census allocated-grid release candidate. Proposed dataset citation available; Harvard Dataverse publication and DOI pending. No Dataverse deposit or final dataset publication is claimed.

The owner-selected proposed dataset authors, in order, are Kytt MacManus; Hieu Tran; Juan Martinez; Alex de Sherbinin; Greg Yetman. The dataset citation remains provisional; the final publication year, registered version, DOI, license and repository identity are not assigned. See [publication guidance](docs/PUBLICATION_GUIDANCE.md) for the exact provisional dataset citation and separate interactive-atlas citation. `site/assets/data/editorial.json` is the canonical editorial configuration.

The preparation, validation, and dissemination of USGRIDS 2020 were supported in part by the Columbia University Research Stabilization Fund (Round 2).

The full site contains 53 geographic selections, 31 canonical variables, 1,643 geography-variable pairs and 4,823 existing validated map views. Maps, exact class thresholds, full-resolution frequencies, valid-cell denominators and scientific identities are retained; this repository performs no raster processing, map rendering or statistics computation.

The public source catalog preserves 1,956 physical scientific file identities: 1,643 GeoTIFFs, 53 NetCDFs and 260 Shapefile components. Grouping the five components of each of 52 Census-block Shapefile datasets gives 1,748 logical products. Scientific source files, historical scripts, internal QA archives and credentials are not included. Scientific files are being prepared for publication in Harvard Dataverse; downloads are not yet available. Curated methods/dictionary/limitations remain available without external archive downloads.

Open site/review.html through any local static HTTP server to review. See ALEX_REVIEW_GUIDE.md. The guide links to Compare Maps and the working GitHub feedback form, with a downloadable text alternative. tools/verify_site.py checks the static manifest, protected maps/metadata, unchanged derived statistics, grouped-catalog integrity and editorial invariants with Python's standard library.

The Pages workflow is manual only and has no push trigger. Its public_visibility_approved input and PUBLIC_VISIBILITY_APPROVED repository variable must both be true, and approved_commit_sha must equal the exact workflow commit. Preserve the existing github-pages environment rules and any additional required exact-commit owner approval. Never enable or bypass these gates merely because local checks pass. The hosted workflow packages site/ only; it does not rebuild maps. No essential asset uses Git LFS.

No license is assigned by this preparation. A preview label does not settle rights. The owner's authorization for scoped revisions to the already-public website does not authorize the separate scientific Dataverse release or bypass any required additional exact-commit approval. Final data publication and any later archive links require their own approvals.
