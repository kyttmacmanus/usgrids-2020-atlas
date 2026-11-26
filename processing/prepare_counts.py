"""Prepare 29 integer 2020 DHC counts for every Census block in one jurisdiction.

Join using textual Census identifiers before computing any formulas. No GIS
license or third-party packages are required. See SOURCE_PREPARATION.md.
"""
import argparse
import csv
import hashlib
import io
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = "https://api.census.gov/data/2020/dec/dhc"
ID_PARTS = {"state": 2, "county": 3, "tract": 6, "block": 4}
FIELD = r"([PH][0-9]+)_([0-9]{3})N"
COUNT_RE = re.compile(r"[0-9]+")


def _table(name):
    """Read one bundled UTF-8 specification in file order, independent of working directory."""
    with (ROOT / name).open(encoding="utf-8-sig", newline="") as src:
        return list(csv.DictReader(src))


def geography(state):
    """Accept FIPS, postal abbreviation, or full name of an included jurisdiction."""
    token = str(state).strip().casefold()
    if token.isascii() and token.isdigit():
        token = token.zfill(2)
    hits = [r for r in _table("geographies.csv")
            if token in (r["state_fips"], r["abbr"].casefold(), r["name"].casefold())]
    if len(hits) != 1:
        raise ValueError(f"Not a USGRIDS 2020 component: {state!r}")
    return hits[0]


def _terms(expr):
    """Expand the small, closed formula language; both SUM endpoints are included."""
    result = []
    for term in expr.split("+"):
        if re.fullmatch(FIELD, term):
            result.append(term)
            continue
        span = re.fullmatch(r"SUM\(" + FIELD + ":" + FIELD + r"\)", term)
        if not span or span[1] != span[3] or int(span[2]) > int(span[4]):
            raise ValueError(f"Unsupported DHC expression: {term}")
        result.extend(f"{span[1]}_{i:03d}N" for i in range(int(span[2]), int(span[4])+1))
    if len(set(result)) != len(result):
        raise ValueError("Overlapping terms in one variable")
    return result


def formulas():
    """Map the 29 canonical counts to DHC fields, retaining their public output order.

    The two grid-cell area variables do not come from tabular Census counts.
    The optional alternate vacancy measure is a cross-check, not an additive term.
    """
    rules = {}
    for r in _table("variable_definitions.csv"):
        if r["category"] == "area":
            continue  # PIXEL_LAND and PIXEL_WATER are area measurements, not Census counts.
        v = r["variable"]
        if v in rules:
            raise ValueError("Duplicate canonical variable")
        # H3_003N is the primary vacancy count. The H5 assurance note is not
        # a second additive term; compare it separately when supplied.
        rules[v] = _terms(r["source_expression"].split(";")[0])
    if len(rules) != 29:
        raise ValueError("Expected 29 count variables")
    return rules


def _identifier(row, state):
    """Check every supported ID representation that is present; never infer digits."""
    ids = []
    if "GEOID" in row:
        ids.append(row["GEOID"])
    if "GEO_ID" in row:
        m = re.fullmatch(r"1000000US([0-9]{15})", str(row["GEO_ID"]))
        if not m:
            raise ValueError("GEO_ID must identify a 2020 Census block (summary level 100)")
        ids.append(m[1])
    if row.keys() & ID_PARTS.keys():
        parts = []
        for field, width in ID_PARTS.items():
            value = row.get(field, "")
            if not isinstance(value, str) or not re.fullmatch(rf"[0-9]{{{width}}}", value):
                raise ValueError(f"Invalid or missing block identifier component: {field}")
            parts.append(value)
        ids.append("".join(parts))
    if (not ids or len(set(ids)) != 1 or not isinstance(ids[0], str)
            or not re.fullmatch(r"[0-9]{15}", ids[0]) or not ids[0].startswith(state)):
        raise ValueError("Missing, conflicting, malformed or wrong-state block identifier")
    return ids[0]


def _value(value):
    """Parse an observed DHC count as an exact nonnegative integer, including zero."""
    # Missing or negative/suppressed source counts are not legitimate zeroes.
    if type(value) not in (str, int) or not COUNT_RE.fullmatch(str(value)):
        raise ValueError("Expected a nonnegative DHC integer; found null, fractional, or non-count")
    return int(value)


def _check_coverage(ids, geo):
    """Test both size and membership of a unique block-ID set against the 2020 geography.

    Return the order-independent ID digest on success. A same-size set containing
    one missing and one invented block must fail even if its population sums match.
    """
    # A count check alone would accept an invented ID replacing a genuine one.
    # Sort fixed-width ASCII strings so upstream response order cannot affect coverage.
    h = hashlib.sha256()
    for key in sorted(ids):
        h.update(key.encode("ascii") + b"\n")
    if len(ids) != int(geo["expected_blocks"]) or h.hexdigest() != geo["sorted_geoid_sha256"]:
        raise ValueError(f"Incomplete or unexpected 2020 block key set for {geo['abbr']}")
    return h.hexdigest()


def _check_identities(v):
    """Reject a block that violates a separately defined population or housing identity.

    Age, race, and ethnicity partitions each sum to total population; they are
    never added to one another. The two nested non-Hispanic race groups are
    subsets, and occupied plus vacant units exhaust total housing units.
    """
    # These compare independent DHC tables/age partitions, not arbitrary
    # overlapping counts. Do not 'repair' a failed identity by moving counts.
    if not (v["AUND25"] == sum(v[k] for k in ("AUND1","A1TO4","A5TO17","A18TO24"))
            and v["A25OV"] == v["A25TO64"]+v["A65TO79"]+v["A80OV"]
            and v["TOTALPOP"] == v["AUND25"]+v["A25OV"] == v["NHISP"]+v["HISP"]
            == sum(v[k] for k in ("WHITE","BLACK","AMIND","ASIAN","HAWPI","OTHER","TWOMORE"))
            and v["HHUNIT"] == v["OCC"]+v["VACANT"] and v["HOUSEHOLD"] == v["OCC"]
            and max(v["OWN"], v["HU1P"]) <= v["OCC"]
            and v["NHISPWHITE"] <= min(v["NHISP"], v["WHITE"])
            and v["NHISPBLACK"] <= min(v["NHISP"], v["BLACK"])):
        raise ValueError("Block count partition or subset relation failed")


@contextmanager
def _atomic_csv(destination):
    """Expose a complete validated file or nothing; never replace user data."""
    out = Path(destination)
    if out.exists():
        raise FileExistsError(out)
    # Same-directory staging keeps the atomic no-clobber hard link on one volume.
    # Remove the temporary name on success or exception; readers see no partial CSV.
    with tempfile.NamedTemporaryFile(dir=out.parent, mode="w", encoding="utf-8",
                                     newline="", prefix=".usgrids-", delete=False) as tmp:
        path = Path(tmp.name)
        try:
            yield csv.writer(tmp, lineterminator="\r\n")
            tmp.close()
            os.link(path, out)
        finally:
            tmp.close()
            path.unlink(missing_ok=True)


@contextmanager
def _open_csv(source):
    """Yield a text stream for a wide CSV or the sole CSV member in a ZIP.

    Read the archive member directly without extracting it or interpreting
    user-supplied filenames as destinations. This does not parse segmented DHC files.
    """
    path = Path(source)
    if path.suffix.casefold() == ".zip":
        # Read one member directly, do not extract arbitrary archive names.
        with zipfile.ZipFile(path) as z:
            tables = [i for i in z.infolist() if not i.is_dir() and i.filename.lower().endswith(".csv")]
            if len(tables) != 1:
                raise ValueError("Expected exactly one wide block-level DHC CSV in ZIP")
            with z.open(tables[0]) as raw, io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as src:
                yield src
    else:
        with path.open(encoding="utf-8-sig", newline="") as src:
            yield src


def _prepare(geo, source, output):
    """Stream official block rows into an unpublished, then atomically exposed count table.

    Evaluate the published formulas only after validating the block's key and raw
    counts; publish only after every row and the entire state's key set pass.
    The return value describes input coverage, not spatial allocation quality.
    """
    rules = formulas()
    required = sorted(set().union(*rules.values()))
    seen = set()
    with _open_csv(source) as src, _atomic_csv(output) as dest:
        rows = csv.DictReader(src, strict=True)
        header = rows.fieldnames or []
        if len(header) != len(set(header)) or not set(required).issubset(header):
            raise ValueError("DHC input has duplicate columns or lacks primary source fields")
        dest.writerow(["GEOID", *rules])
        for row in rows:
            try:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError("Source CSV row width differs from its header")
                key = _identifier(row, geo["state_fips"])
                if key in seen:
                    raise ValueError("Duplicate block GEOID")
                seen.add(key)
                n = {f:_value(row[f]) for f in required}
                if "H5_001N" in row and _value(row["H5_001N"]) != n["H3_003N"]:
                    raise ValueError("H5_001N disagrees with H3_003N")
                v = {code:sum(n[f] for f in terms) for code, terms in rules.items()}
                _check_identities(v)
                dest.writerow([key,*v.values()])
            except ValueError as exc:
                raise ValueError(f"DHC input row {rows.line_num}: {exc}") from exc
        digest = _check_coverage(seen, geo)
    return dict(state_fips=geo["state_fips"], blocks=len(seen), count_variables=len(rules),
                source_fields=len(required), sorted_geoid_sha256=digest)


def prepare_counts(state, source, output):
    """Write GEOID + 29 canonical integer counts from one full state DHC wide CSV."""
    return _prepare(geography(state), source, output)


def _request(params):
    """Make an official HTTPS API request and decode JSON without exposing credentials.

    Retry transient transport/server failures; report permanent query or decoding
    errors without the request URL. The caller supplies its own Census API key.
    """
    # Never discover keys in files or put a token-bearing URL in a traceback.
    # Only a caller-set environment secret is sent to the official HTTPS host.
    key = os.environ.get("CENSUS_API_KEY")
    if not key:
        raise ValueError("Set CENSUS_API_KEY privately for acquisition, or use a local DHC CSV")
    url = BASE+"?"+urllib.parse.urlencode([*params,("key",key)])
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=180) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            code=exc.code
            exc.close()
            if code not in (429,500,502,503,504) or attempt==3:
                raise ValueError(f"Census API HTTP {code}; check key and query permissions") from None
        except (urllib.error.URLError,TimeoutError,OSError):
            if attempt==3:
                raise ValueError("Census API unavailable; retry the acquisition later") from None
        except (UnicodeError,json.JSONDecodeError):
            raise ValueError("Census API returned a non-JSON response; check API access") from None
        time.sleep(2**attempt)


def _api_rows(payload, fields):
    """Decode the Census API's header-plus-rows JSON; never assume returned column order."""
    if not isinstance(payload,list) or len(payload)<2 or not isinstance(payload[0],list):
        raise ValueError("Empty/malformed Census response")
    head=payload[0]
    if set(head)!=set(fields) or len(set(head))!=len(head):
        raise ValueError("Census API columns differ from request")
    for values in payload[1:]:
        if not isinstance(values,list) or len(values)!=len(head):
            raise ValueError("Census API row width differs from header")
        yield dict(zip(head,values))


def _fetch(geo, output, request):
    """Resolve the geography's counties, then acquire the union of all required DHC fields.

    The request callable can supply recorded or synthetic responses for offline
    testing; operational requests always target the official year-2020 DHC endpoint.
    """
    state=geo["state_fips"]
    target=sorted(set().union(*formulas().values()))
    counties=_county_ids(state,request)
    return _fetch_counties(geo, output, request, target, counties)


def _county_ids(state, request):
    """Enumerate unique three-digit counties for this state from the DHC API itself.

    This keeps the block queries tied to the Census dataset's geographic vintage
    rather than to a modern list or the host machine's directory structure.
    """
    county_list=request([("get","NAME"),("for","county:*"),("in",f"state:{state}")])
    counties=[]
    for row in _api_rows(county_list,["NAME","state","county"]):
        if row["state"]!=state or not re.fullmatch("[0-9]{3}",str(row["county"])) or row["county"] in counties:
            raise ValueError("Invalid/duplicate county returned for requested geography")
        counties.append(row["county"])
    return counties


def verify_geography(state):
    """Reproduce the 2020 DHC geography receipt from public names/IDs, not counts."""
    geo=geography(state)
    fips=geo["state_fips"]
    ids=set()
    for county in sorted(_county_ids(fips,_request)):
        params=[("get","NAME"),("for","block:*"),("in",f"state:{fips}"),
                ("in",f"county:{county}"),("in","tract:*")]
        for row in _api_rows(_request(params),["NAME",*ID_PARTS]):
            key=_identifier(row,fips)
            if row["county"]!=county or key in ids:
                raise ValueError("Unexpected county or duplicate block in geography request")
            ids.add(key)
    return dict(state_fips=fips,blocks=len(ids),sorted_geoid_sha256=_check_coverage(ids,geo))


def _fetch_counties(geo, output, request, target, counties):
    """Assemble an official wide raw table by block key across field batches within counties.

    Preserve zero-valued and unpopulated blocks. Every field batch in a county must
    cover exactly the same block IDs; only a complete full-state table is exposed.
    """
    state=geo["state_fips"]
    all_ids=set()
    with _atomic_csv(output) as dest:
        dest.writerow(["GEOID",*target])
        for county in sorted(counties):
            # 95 fields exceed one Census request. Keep only one county's join in
            # memory, and join by GEOID, not by the API's incidental row order.
            joined={}
            for start in range(0,len(target),45):
                fields=target[start:start+45]
                params=[("get",",".join(fields)),("for","block:*"),("in",f"state:{state}"),
                        ("in",f"county:{county}"),("in","tract:*")]
                batch_ids=set()
                for row in _api_rows(request(params),[*fields,*ID_PARTS]):
                    key=_identifier(row,state)
                    if row["county"]!=county or key in batch_ids or (start and key not in joined):
                        raise ValueError("Unexpected block or duplicate GEOID in Census field batch")
                    batch_ids.add(key)
                    joined.setdefault(key,[]).extend(_value(row[f]) for f in fields)
                if batch_ids != joined.keys():
                    raise ValueError("Missing GEOID in Census field batch")
            for key in sorted(joined):
                dest.writerow([key,*joined[key]])
            all_ids.update(joined)
        digest=_check_coverage(all_ids,geo)
    return dict(state_fips=state, counties=len(counties), blocks=len(all_ids), source_fields=len(target),
                sorted_geoid_sha256=digest)


def fetch_dhc(state, output):
    """Acquire block-level year-2020 DHC inputs for one included jurisdiction."""
    return _fetch(geography(state),output,_request)


def main():
    """Select one command: compute counts locally, acquire a raw CSV, or verify geography alone."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--geography", required=True, help="Jurisdiction FIPS, postal abbreviation, or full name")
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input", type=Path, help="Wide DHC CSV or ZIP containing one such CSV")
    group.add_argument("--fetch-to", type=Path, help="Fetch a new raw wide state DHC CSV using CENSUS_API_KEY")
    group.add_argument("--verify-geography", action="store_true", help="Reproduce block key-set receipt from the Census geography API")
    parser.add_argument("--output", type=Path, help="New canonical CSV (required with --input)")
    args=parser.parse_args()
    if (args.input is None) != (args.output is None):
        parser.error("--output is required with --input and is not used with --fetch-to")
    result=(verify_geography(args.geography) if args.verify_geography else
            fetch_dhc(args.geography,args.fetch_to) if args.fetch_to else
            prepare_counts(args.geography,args.input,args.output))
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
