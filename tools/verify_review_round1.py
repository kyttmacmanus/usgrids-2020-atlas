"""Presentation-only round-one safeguards. No source GIS products are read or written."""
from pathlib import Path
import json,re,hashlib
ROOT=Path(__file__).resolve().parents[1]
def sha(text):return hashlib.sha256(text.encode('utf8')).hexdigest()
def verify(site=None):
 site=site or ROOT/'site';lock=json.loads((ROOT/'tools/review_round1_lock.json').read_text('utf8'));code=(site/'assets/editorial.js').read_text('utf8')
 closure=json.loads((ROOT/'tools/femw18child_closure_lock.json').read_text('utf8'));code=code.replace(closure['methods_after'],closure['methods_before'])
 clarification=json.loads((ROOT/'tools/alpha_finalization_lock.json').read_text('utf8'))['historical_definition_clarification']
 for name,record in lock['retained_fragments'].items():
  match=re.search(record['pattern'],code.replace(clarification['after'],clarification['before']) if name=='historical_exceptions' else code,re.S);assert match and sha(match[0])==record['sha256'],'Retained scientific explanation changed: '+name
 assert 'class="variable-name">${escape(d.name)}' in code and 'Variable name' in code and 'Variable code' in code and 'Definition</p>' in code
 assert 'aria-describedby="technical-implementation-intro"' in code
 assert code.index('id="technical-implementation-intro"')<code.index('id="technical-implementation"')
 scope=code[code.index('id="coverage-scope"'):code.index("${editorialTable('Interpretation and limitations'")]
 for phrase in ['50 states','District of Columbia','Puerto Rico','American Samoa','Guam','Northern Mariana Islands','U.S. Virgin Islands','outside this release','separate DHC file','not included in this release','2020-census-results.html','2020-island-areas-data-products.html']:assert phrase in scope,phrase
 css=(site/'assets/refinement.css').read_text('utf8');assert '--map-panel:#E1E5E8' in css and '.map-frame{background:var(--map-panel)}' in css
 shared=(site/'assets/refinement.js').read_text('utf8');assert 'also extends outside mapped coverage and does not represent measured values' in shared
 for p in site.glob('*.html'):
  for asset in ['editorial.js','refinement.js','refinement.css','site.js']:
   version='fem-closure-20261030a' if asset in ['editorial.js','site.js'] else 'alpha-final-20261030a'
   assert 'assets/'+asset+'?v='+version in p.read_text('utf8'),(p,asset)
 return {'status':'PASS','baseline_commit':lock['baseline_commit'],'technical_bullets_and_qualifications_unchanged':True,'conceptual_allocation_explanation_unchanged':True,'national_reconciliation_unchanged':True,'historical_exceptions_preserved_with_scoped_definition_clarification':True,'dictionary_presentation_only':True,'census_coverage_sources_linked':True,'consistent_map_backdrop':'#E1E5E8','scientific_processing':False}
if __name__=='__main__':print(json.dumps(verify(),indent=2))
