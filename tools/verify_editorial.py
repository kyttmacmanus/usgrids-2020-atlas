"""Independent editorial/catalog/preservation checks; standard library, no GIS."""
from pathlib import Path
import json,hashlib,collections,re
ROOT=Path(__file__).resolve().parents[1]
AUTHORS=['Kytt MacManus','Hieu Tran','Juan Martinez','Alex de Sherbinin','Greg Yetman']
FUNDING='The preparation, validation, and dissemination of USGRIDS 2020 were supported in part by the Columbia University Research Stabilization Fund (Round 2).'
PREFIX='MacManus, K., Tran, H., Martinez, J., de Sherbinin, A., & Yetman, G. (2026). '

def load(p):return json.loads(p.read_text('utf8'))
def verify(site=None):
    site=site or ROOT/'site';e=load(site/'assets/data/editorial.json');a=load(site/'assets/data/atlas.json')
    lock=load(ROOT/'tools/editorial_preservation_lock.json')
    for rel,expected in lock['assets'].items():
        data=(ROOT/rel).read_bytes()
        # Git normalizes workflow text to LF; public site assets are explicitly binary.
        if rel=='.github/workflows/pages-review.yml':data=data.replace(b'\r\n',b'\n')
        assert hashlib.sha256(data).hexdigest()==expected,rel
    assert len([p for p in lock['assets'] if p.startswith('site/assets/data/class-values/')])==32
    js=(site/'assets/site.js').read_text('utf8');home=js[js.index('function home(){'):js.index('function explorer(){')]
    approved_home=home.replace("${classificationName('fixed')}",'Fixed count classes')
    assert hashlib.sha256(approved_home.encode()).hexdigest()==lock['homepage_function_sha256'],'Homepage content/layout changed beyond authorized classification label'
    assert e['authors']==AUTHORS and e['funding']==FUNDING
    assert e['dataset_citation']==PREFIX+e['dataset_title']+' [Dataset, provisional citation]. Center for Integrated Earth System Information (CIESIN), Columbia University. Harvard Dataverse (publication pending).'
    assert e['status']=='PROVISIONAL_OWNER_SELECTED_NOT_ARCHIVE_REGISTERED'
    assert e['publication_status']=='Proposed dataset citation available; Harvard Dataverse publication and DOI pending.'
    assert e['download_status']=='Scientific files are being prepared for publication in Harvard Dataverse; downloads are not yet available.'
    assert 'scientific review preview' in e['atlas_citation'] and e['atlas_citation'].startswith('MacManus, K. (2026). ')
    category_vars=[v for vs in e['categories'].values() for v in vs]
    assert len(category_vars)==len(set(category_vars))==31 and set(category_vars)==set(a['variables'])==set(e['descriptions'])
    assert list(e['categories'])==['Population and Age','Race and Ethnicity','Households and Housing','Land and Water Area']
    assert len(e['categories']['Land and Water Area'])==2 and sum(not v['area'] for v in a['variables'].values())==29
    assert 'FEMW18CHILD' not in category_vars
    code=(site/'assets/editorial.js').read_text('utf8')
    for anchor in ['framework','allocation','dictionary','validation','limitations','provenance']:
        assert f'id="{anchor}" data-method-section' in code
    assert code.count('data-method-section')==6
    assert '<details class="technical-note" id="national-reconciliation">' in code
    assert '<details class="technical-note" id="correction">' in code
    assert '<a href="#correction">' not in code and '380' not in code
    assert 'round(PIXEL_LAND,5)&gt;0' in code and 'GEODESIC_LAND' in code and 'ALAND20' in code
    assert 'role="math"' in code and 'no uniquely established cause' in code
    assert '1,662.5' in code and '334,733,492.4976411' in code and '334,735,155' in code
    assert "d.definition" in code and "d.universe" in code and "d.source_urls" in code
    for phrase in ['Every color has a source.','One grid.','An allocation,','The vocabulary of the atlas.','Evidence at the source resolution.','Read the limits','A traceable release.','The map is an invitation.','Continue with','Find the scientific file.','A citation to carry forward.','Look closely.','Creators and DOI pending','Authorship & citation pending approval','individual authorship and DOI are being finalized','Issues link can be enabled']:
        assert phrase not in js+code,phrase
    files=load(site/'assets/data/file-catalog.json');counts=collections.Counter(f['artifact_class'] for f in files)
    assert counts=={'geotiff':1643,'netcdf':53,'shapefile':260} and len(files)==1956
    assert all(f['geography'] in a['geographies'] and f['bytes']>=0 and re.fullmatch('[0-9a-f]{64}',f['sha256']) for f in files)
    grouped=collections.defaultdict(list)
    for f in files:
        if f['artifact_class']=='shapefile':grouped[(f['geography'],str(Path(f['path']).with_suffix('')))].append(f)
    assert len(grouped)==52
    for (geo,stem),components in grouped.items():
        assert geo!='NATIONAL' and len(components)==5
        assert {Path(c['path']).suffix for c in components}=={'.shp','.shx','.dbf','.prj','.cpg'}
    for geo in a['geographies']:
        bygeo=[f for f in files if f['geography']==geo]
        assert sum(f['artifact_class']=='geotiff' for f in bygeo)==31
        nc=[f for f in bygeo if f['artifact_class']=='netcdf'];assert len(nc)==1 and set(nc[0]['variables'])==set(a['variables'])
        assert sum(f['artifact_class']=='shapefile' for f in bygeo)==(0 if geo=='NATIONAL' else 5)
    assert 1643+53+len(grouped)==1748
    assert all(f.get('download_url') is None and f['repository_status']=='PENDING_REGISTRATION' for f in files)
    assert "f.repository_status==='REGISTERED'" in code and 'dataverse\\.harvard\\.edu' in code
    assert e['feedback_url']=='https://github.com/kyttmacmanus/usgrids-2020-atlas/issues/new?template=scientific_review.yml'
    for f in ['ALEX_REVIEW_GUIDE.md','docs/PUBLICATION_GUIDANCE.md']:
        text=(ROOT/f).read_text('utf8');assert e['dataset_citation'] in text and FUNDING in text and '; '.join(AUTHORS) in text
    template=(site/'review-feedback.txt').read_text('utf8');assert 'does not automatically' in template
    for field in ['Review category','Exact selected map or page URL','Observed','Expected','impact','Supporting evidence','Suggested correction','optional']:assert field in template
    issue=(ROOT/'.github/ISSUE_TEMPLATE/scientific_review.yml').read_text('utf8')
    for feature in ['Compare Maps','Science & Methods','Data Access','Scientific Review Guide']:assert feature in issue
    layers={key:layer for rel in a['layer_partitions'].values() for key,layer in load(site/rel).items()}
    assert len(e['review_cases'])==10 and sum(c['group']=='core' for c in e['review_cases'])==5
    for case in e['review_cases']:assert case['c'] in layers[case['g']+'_'+case['v']]['modes']
    for p in site.glob('*.html'):
        html=p.read_text('utf8');assert html.count('assets/editorial.js?')==1 and html.count('assets/editorial.css?')==1
        assert html.index('assets/editorial.js?')<html.index('assets/site.js?')
    return {'status':'PASS','dictionary_variables':31,'category_coverage':'31/31','logical_products':1748,'physical_files':1956,'geotiff':1643,'netcdf':53,'complete_shapefile_sets':52,'shapefile_components':260,'derived_statistics_files_unchanged':32,'approved_homepage_function_unchanged':True,'author_order':AUTHORS,'exact_funding_sentence':True,'manual_workflow_unchanged':True,'scientific_processing':False}
if __name__=='__main__':print(json.dumps(verify(),indent=2))
