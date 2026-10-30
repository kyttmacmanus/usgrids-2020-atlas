"""Scoped finalization checks; frozen science and original lock records remain immutable."""
from pathlib import Path
import json,re,hashlib
ROOT=Path(__file__).resolve().parents[1]
def verify(site=None):
 site=site or ROOT/'site';load=lambda p:json.loads(p.read_text('utf8'))
 a=load(site/'assets/data/atlas.json');e=load(site/'assets/data/editorial.json');lock=load(ROOT/'tools/alpha_finalization_lock.json')
 assert len(a['variables'])==31 and len(a['geographies'])==53 and 'FEMW18CHILD' not in a['variables']
 assert a['variables']['WOMCHILD']['definition']=='SUM(P12_030N:P12_039N)'
 assert e['descriptions']['WOMCHILD']=='Female population ages 15 through 49. This variable does not count children or identify mothers.'
 js=(site/'assets/site.js').read_text('utf8');editorial=(site/'assets/editorial.js').read_text('utf8');helper=(site/'assets/explorer-tools.js').read_text('utf8')
 expected="[['home','index.html','Home'],['explore','explore.html','Explore Maps'],['access','data.html','Data Access'],['methods','methods.html','Science & Methods']]"
 assert 'const links='+expected in js
 assert 'document.body.innerHTML=header()+(' in js and '<section class="review-notice"' not in js
 assert 'href="feedback.html">Feedback &amp; Corrections</a>' in js
 assert 'approximately 500 m near the equator; cell dimensions vary with latitude' in js
 assert 'classPresentation(m,b).label' in js and 'function classPresentation(m,b)' in helper
 assert 'Exact class boundaries' in helper and 'm.edges[i+1]' in helper
 assert 'Different geographic scales:' in helper and helper.index('comparison-scale-note')<helper.index('<div class="compare-grid">')
 assert 'Apparent map size should not be used to compare geographic extent or the magnitude of values.' in helper
 assert lock['historical_definition_clarification']['after'] in editorial
 assert 'does not establish that the two variable names originally represented the same demographic concept' in editorial
 assert 'source definition has not been verified' in editorial
 assert 'FEMW18CHILD' not in editorial[editorial.index('function editorialMethods'):editorial.index('id="correction"')]
 feedback=editorial[editorial.index('function editorialFeedback'):editorial.index('async function initEditorialTools')]
 for anchor in ['feedback','review-criteria','review-publication']:assert 'id="'+anchor+'"' in feedback
 assert feedback.index('id="feedback"')<feedback.index('Explore example maps')
 for phrase in ['GitHub requires an account','Do not include confidential information or unpublished sensitive material','does not automatically transmit feedback','NoData']:
  assert phrase in editorial+helper,phrase
 assert e['authors']==['Kytt MacManus','Hieu Tran','Juan F. Martinez','Alex de Sherbinin','Greg Yetman']
 assert 'publication pending' in e['dataset_citation'] and 'provisional citation' in e['dataset_citation']
 assert 'scientific review preview' not in e['atlas_citation'].lower()
 assert 'Scientific data release in preparation' in e['download_status']
 assert 'World Resources Institute' in e['historical_acknowledgments'] and '80GSFC23CA001' in e['historical_acknowledgments']
 for name in ['atlas_feedback.yml','scientific_review.yml']:
  template=(ROOT/'.github/ISSUE_TEMPLATE'/name).read_text('utf8')
  for category in ['Scientific data concern','Documentation correction','Map or classification issue','Website or accessibility problem','Feature suggestion','Other']:assert category in template
  assert 'GitHub Issues are publicly visible' in template and 'Release-blocking' not in template
  context=template.split('id: selection_context')[1].split('  - type:')[0];assert 'required: true' not in context
 for name in ['index','explore','compare','data','methods','documentation','feedback','review']:
  html=(site/(name+'.html')).read_text('utf8');assert 'Scientific Review Preview' not in re.search(r'<title>.*?</title>',html)[0]
  for asset in ['site.js','editorial.js','explorer-tools.js','refinement.js','refinement.css']:assert asset+'?v=alpha-final-20261030a' in html
 assert 'data-page="review"' in (site/'review.html').read_text('utf8')
 assert 'data-page="feedback"' in (site/'feedback.html').read_text('utf8')
 return {'status':'PASS','canonical_variables':31,'geographies':53,'WOMCHILD_definition_verified':True,'historical_concept_equivalence_not_claimed':True,'navigation_order':['Home','Explore Maps','Data Access','Science & Methods'],'legacy_page_and_issue_template_preserved':True,'feedback_public_visibility_and_account_disclosed':True,'publication_status_qualified':True,'map_processing':False}
if __name__=='__main__':print(json.dumps(verify(),indent=2))
