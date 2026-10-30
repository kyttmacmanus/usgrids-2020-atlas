"""Current release disposition, reproducible editorial output and frozen-source identity."""
from pathlib import Path
import json,hashlib,re,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
def verify(site=None):
 site=site or ROOT/'site';load=lambda p:json.loads(p.read_text('utf8'))
 lock=load(ROOT/'tools/femw18child_closure_lock.json');a=load(site/'assets/data/atlas.json')
 assert len(a['variables'])==31 and sum(not v['area'] for v in a['variables'].values())==29
 assert len(a['geographies'])==53 and len(a['layer_partitions'])==31
 assert not any(re.search(r'FEMW?18CHIL',v,re.I) for v in a['variables'])
 assert a['variables']['WOMCHILD']['name']=='Female population ages 15–49'
 assert a['variables']['WOMCHILD']['definition']=='SUM(P12_030N:P12_039N)'
 catalog=load(site/'assets/data/file-catalog.json');assert len(catalog)==1956
 assert 'FEMW18CHIL' not in json.dumps(catalog).upper()
 assert all(f.get('download_url') is None and f['repository_status']=='PENDING_REGISTRATION' for f in catalog)
 methods=(site/'assets/editorial.js').read_text('utf8');doc=(site/'documentation.html').read_text('utf8');generator=(ROOT/'tools/build_readable_documentation.py').read_text('utf8')
 for text in [methods,doc,generator]:assert lock['methods_after'] in text
 assert methods.count(lock['methods_after'])==1
 note=doc.split('id="current-definition"',1)[1].split('</section>',1)[0]
 assert '<h2>Historical variable correction</h2>' in note
 assert 'female-headed households with related children under age 18' in note
 assert 'current release decision is resolved' in note and 'historical evidence' in note
 assert 'source definition has not been verified' not in note+methods
 assert 'P20_017N' not in methods+note
 for filename in ['index','explore','compare','methods','documentation','data','feedback','review']:
  html=(site/(filename+'.html')).read_text('utf8')
  for asset in ['site.js','editorial.js']:assert asset+'?v='+lock['cache_version'] in html
 assert 'assets/editorial.js?v='+lock['cache_version'] in (site/'assets/site.js').read_text('utf8')
 source=site/'assets/data/scientific-documentation.json'
 # Frozen curated records are additionally checked against their established lock.
 source_lock=load(ROOT/'tools/documentation_source_lock.json');records=load(source)
 for name,digest in source_lock['curated_texts'].items():assert hashlib.sha256(records[name]['text'].encode()).hexdigest()==digest
 before=(site/'documentation.html').read_bytes()
 assert b'\r\n' not in before,'Generated documentation must use platform-independent LF bytes'
 subprocess.run([sys.executable,str(ROOT/'tools/build_readable_documentation.py')],check=True,capture_output=True)
 assert (site/'documentation.html').read_bytes()==before,'Stale generated documentation'
 return {'status':'PASS','release_decision':'EXCLUDED; no replacement','canonical_variables':31,'WOMCHILD_retained':True,'curated_records_preserved':4,'generated_documentation_current':True,'cache_references_updated':True,'scientific_processing':False}
if __name__=='__main__':print(json.dumps(verify(),indent=2))
