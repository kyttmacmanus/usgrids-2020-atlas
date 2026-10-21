"""Standard-library verification of derived display sums and immutable science.

No source-raster processing or network access occurs in deployment verification.
"""
from pathlib import Path
import json,hashlib,math
ROOT=Path(__file__).resolve().parents[1]
FINGERPRINT='829b327fb2950d37c9c3932061d501bd6447ecd4adecdfefe3ed2b4800860cc1'
def load(p):return json.loads(p.read_text('utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def units(v):return 'km²' if v.startswith('PIXEL_') else 'allocated households' if v=='HOUSEHOLD' else 'allocated housing units' if v in ['HHUNIT','OCC','OWN','VACANT','HU1P'] else 'allocated persons'
def verify(site=None):
    site=site or ROOT/'site';lock=load(ROOT/'tools/scientific_asset_lock.json')
    assert lock['baseline_commit']=='ae544cef48e0016164fcc64ee7be128abf61f646'
    assert len(lock['assets'])==4857
    for rel,h in lock['assets'].items():assert sha(ROOT/rel)==h,'Frozen scientific asset changed: '+rel
    atlas=load(site/'assets/data/atlas.json');assert atlas['source_release']['manifest_sha256']==FINGERPRINT
    index=load(site/'assets/data/class-values/index.json')
    assert index['status']=='COMPLETE' and index['completed']==index['expected']==1643
    assert index['release_manifest_sha256']==FINGERPRINT and set(index['partitions'])==set(atlas['variables'])
    assert index['policy']['absolute_tolerance']==1e-9 and index['policy']['relative_tolerance']==1e-12
    total=mode_count=national=0;original_layers={}
    for variable,info in index['partitions'].items():
        p=site/info['path'];assert p.resolve().is_relative_to((site/'assets/data/class-values').resolve())
        assert sha(p)==info['sha256'] and info['completed']==info['expected']==53
        data=load(p);layers=load(site/atlas['layer_partitions'][variable]);original_layers.update(layers)
        assert data['variable']==variable and data['coverage']['completed']==data['coverage']['expected']==53 and set(data['layers'])==set(layers)
        for lid,r in data['layers'].items():
            l=layers[lid];s=l['statistics'];assert r['status']=='PASS' and r['id']==lid and r['geography']==l['geography'] and r['variable']==variable
            assert r['source']==l['sources']['geotiff'] and r['source_sha256_verified'] is True
            assert r['release_manifest_sha256']==FINGERPRINT and r['implementation']==index['implementation'] and r['policy']==index['policy']
            assert r['units']==units(variable) and r['valid_cell_count']==s['valid_cell_count'] and r['zero_cell_count']==s['zero_cell_count'] and r['nodata_count']==s['missing_cell_count']
            assert r['grid']['width']*r['grid']['height']==s['total_cell_count'] and r['grid']['dtype']=='float64' and r['grid']['crs']=='EPSG:4326'
            assert r['valid_cell_count']+r['nodata_count']==s['total_cell_count']
            tol=1e-9+1e-12*abs(s['valid_value_sum']);assert r['sum_reconciliation_tolerance']==tol
            assert r['authoritative_valid_value_sum']==s['valid_value_sum'] and abs(r['valid_value_sum']-s['valid_value_sum'])<=tol
            expected_signature=hashlib.sha256(json.dumps({'version':r['implementation'],'policy':r['policy'],'source':l['sources']['geotiff'],'statistics':s,'classifications':{k:{x:m[x] for x in ['edges','bins','interval_convention','classification_record_id']} for k,m in l['modes'].items()}},sort_keys=True).encode()).hexdigest()
            assert r['input_signature']==expected_signature and set(r['modes'])==set(l['modes'])
            assert r['national_read_independently']==(l['geography']=='NATIONAL')
            if l['geography']=='NATIONAL':assert r['source']['path'].startswith('geotiff/national/');national+=1
            for key,m in l['modes'].items():
                mode_count+=1;v=r['modes'][key]
                assert v['classification_record_id']==m['classification_record_id'] and v['edges']==m['edges']
                assert v['count_reconciliation']==v['sum_reconciliation']=='PASS' and len(v['bins'])==len(m['bins'])
                assert sum(b['count'] for b in v['bins'])==s['valid_cell_count']
                assert v['bins'][0]['category']=='zero' and v['bins'][0]['value_sum']==0
                assert abs(math.fsum(b['value_sum'] for b in v['bins'])-s['valid_value_sum'])<=tol
                assert math.isfinite(v['bin_value_total']) and abs(v['bin_value_total']-math.fsum(b['value_sum'] for b in v['bins']))<=tol and abs(v['sum_residual_vs_authoritative'])<=tol
                for i,(b,original) in enumerate(zip(v['bins'],m['bins'])):
                    assert b['count']==original['count'] and b['label']==original['label'] and b['category']==original['category'] and b['category']!='nodata'
                    assert math.isfinite(b['value_sum']) and b['value_sum']>=0
                    assert (b['value_percent'] is None) if r['valid_value_sum']==0 else math.isclose(b['value_percent'],100*b['value_sum']/r['valid_value_sum'],rel_tol=0,abs_tol=1e-10)
                    if i:
                        if key=='fixed':lo=0 if i==1 else m['edges'][i-2];hi=m['edges'][i-1] if i-1<len(m['edges']) else math.inf
                        else:lo=m['edges'][i-1];hi=m['edges'][i] if len(m['edges'])>1 else lo
                        btol=1e-9+1e-12*abs(b['value_sum'])
                        if not b['count']:assert b['value_sum']==0
                        else:assert b['count']*lo-btol<=b['value_sum'] and (math.isinf(hi) or b['value_sum']<=b['count']*hi+btol),(lid,key,i,'interval-sum bound')
            total+=1
    assert total==1643 and mode_count==4823 and national==31
    assert original_layers['NATIONAL_TOTALPOP']['statistics']['valid_cell_count']==62967001
    assert sum(l['statistics']['valid_cell_count'] for l in original_layers.values() if l['variable']=='TOTALPOP' and l['geography']!='NATIONAL')==63055358
    assert (site/'compare.html').is_file() and (site/'assets/explorer-tools.js').is_file()
    return {'class_value_layers':total,'verified_classification_summaries':mode_count,'independently_read_national_rasters':national,'original_scientific_files_unchanged':len(lock['assets']),'status':'PASS'}
if __name__=='__main__':print(json.dumps(verify(),indent=2))
