# Historical variable correction — 30 October 2026

The owner has resolved the release disposition: FEMW18CHILD remains excluded; no replacement is introduced. The release retains 29 Census-derived count variables and two area variables.

An originally proposed female-headed-household indicator was excluded from this release after review identified a mismatch between its documented definition and produced source expression. The historical output duplicated the women-ages-15–49 variable and did not constitute a valid independent household measure.

The original source implementation used SUM(P12_030N:P12_039N), which counts female persons ages 15–49 rather than households. The release retains this expression under its correct WOMCHILD definition. No independently verified household-count product corresponding to the intended historical definition was recovered from the inspected project materials.

The intended related-children household concept and actual person-age construction are different measures. This closure does not claim exhaustive nationwide pixel identity. Historical curated records are preserved unchanged and distinguished from current guidance on Technical Documentation.

The revision changes the Methods exception paragraph, separate generated documentation context, and script cache references. It preserves scientific assets, metadata, masks, classifications, statistics, inventories and the manual exact-commit Pages workflow. The formal CIESIN-style co-author review documents and supporting validation receipts remain in the owner's review package. Harvard Dataverse publication and scientific downloads remain pending.

Validation: `python tools/verify_site.py`, including `verify_femw18child_closure.py`; responsive browser, generated-output, internal-link and frozen-checksum checks are recorded separately. No new maps or scientific products are produced.
