"""Verify the prerendered site only; no render/GIS/network dependencies."""
from pathlib import Path
import json,csv,hashlib,collections,re
from verify_class_values import verify as verify_class_values
ROOT=Path(__file__).resolve().parents[1]
SITE=ROOT/'site'
def load(p):return json.loads(p.read_text('utf8'))
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(4*1024**2),b''):h.update(b)
    return h.hexdigest()
def run():
    with (ROOT/'SITE_DEPLOYMENT_MANIFEST.csv').open(encoding='utf8',newline='') as f:manifest=list(csv.DictReader(f))
    expected={r['relative_path']:r for r in manifest}
    actual={p.relative_to(ROOT).as_posix():p for p in SITE.rglob('*') if p.is_file()}
    assert set(expected)==set(actual),'Missing or unexpected public site file'
    for rel,p in actual.items():
        r=expected[rel];assert p.stat().st_size==int(r['bytes']) and digest(p)==r['sha256'],rel
        assert not p.is_symlink() and p.suffix.lower() not in ['.tif','.tiff','.nc','.shp','.shx','.dbf','.prj','.cpg','.py','.ipynb','.zip','.tar']
    a=load(SITE/'assets/data/atlas.json');assert len(a['geographies'])==53 and len(a['variables'])==31 and not a.get('sample')
    assert a['source_release']['manifest_sha256']=='829b327fb2950d37c9c3932061d501bd6447ecd4adecdfefe3ed2b4800860cc1'
    layers={k:v for rel in a['layer_partitions'].values() for k,v in load(SITE/rel).items()};assert len(layers)==1643
    images=set();views=0
    for l in layers.values():
        assert l['id']==l['geography']+'_'+l['variable'] and l['geography'] in a['geographies'] and l['variable'] in a['variables']
        for m in l['modes'].values():
            p=SITE/m['image'];assert p.exists() and digest(p)==m['image_sha256'];images.add(m['image']);views+=1
            assert sum(b['count'] for b in m['bins'])==m['chart_denominator']==l['statistics']['valid_cell_count']
            assert all(abs(b['percent']-100*b['count']/m['chart_denominator'])<1e-10 for b in m['bins'])
    assert views==len(images)==4823 and images=={p.relative_to(SITE).as_posix() for p in (SITE/'assets/maps').glob('*.webp')}
    catalog=load(SITE/'assets/data/file-catalog.json');assert len(catalog)==1956
    assert collections.Counter(f['artifact_class'] for f in catalog)=={'geotiff':1643,'netcdf':53,'shapefile':260}
    assert all(f.get('download_url') is None and f.get('repository_status')=='PENDING_REGISTRATION' for f in catalog)
    for g in a['geographies']:
        assert {l['variable'] for l in layers.values() if l['geography']==g}==set(a['variables'])
    assert len({f['path'].casefold() for f in catalog})==1956
    assert sum(p.stat().st_size for p in actual.values())<1_000_000_000
    assert max(p.stat().st_size for p in actual.values())<100*1024**2
    derived=verify_class_values(SITE)
    print(json.dumps({'status':'PASS','map_views':views,'geographies':53,'variables':31,'layer_pairs':1643,'scientific_source_catalog':1956,'site_files':len(actual),'site_bytes':sum(p.stat().st_size for p in actual.values()),'max_file_bytes':max(p.stat().st_size for p in actual.values()),'scientific_processing':False,'derived_class_value_verification':derived},indent=2))
if __name__=='__main__':run()
