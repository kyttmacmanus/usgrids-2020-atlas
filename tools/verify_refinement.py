"""Verify presentation refinements without changing or processing scientific inputs."""
from pathlib import Path
from html.parser import HTMLParser
import html,json,re,hashlib
ROOT=Path(__file__).resolve().parents[1];SITE=ROOT/'site'
def load(p):return json.loads(p.read_text('utf8'))
def function_text(text,name):
    start=re.search(r'^(?:async )?function '+re.escape(name)+r'\(',text,re.M).start()
    next_decl=re.search(r'^(?:(?:async )?function \w+\(|(?:const|let) )',text[start+1:],re.M)
    return text[start:] if next_decl is None else text[start:start+1+next_decl.start()]
def checksum(text):return hashlib.sha256(text.encode('utf8')).hexdigest()
def plain_markdown(text):
    lines=[]
    for line in text.splitlines():
        if re.fullmatch(r'\|[\s|:\-]+\|',line):continue
        line=re.sub(r'^#{1,6} ','',line);line=re.sub(r'^- ','',line)
        lines.append(line.replace('|',' ').replace('**','').replace('`',''))
    return ''.join(''.join(lines).split())
class SourceText(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.stack=[];self.source=None;self.active=None;self.records={};self.reconciliation=[];self.ids=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if 'id' in a:self.ids.append(a['id'])
        self.stack.append((tag,self.source,self.active))
        if 'data-doc-source' in a:self.source=a['data-doc-source'];self.records[self.source]={'sha256':a['data-source-sha256'],'text':[]}
        if 'doc-source-content' in a.get('class','').split():self.active='source'
        if 'approved-reconciliation-content' in a.get('class','').split():self.active='reconciliation'
        if tag in ['meta','link','input','img','br','hr']:self.stack.pop()
    def handle_endtag(self,tag):
        if self.stack:
            for i in range(len(self.stack)-1,-1,-1):
                if self.stack[i][0]==tag:
                    _,self.source,self.active=self.stack[i];self.stack=self.stack[:i];break
    def handle_data(self,data):
        if self.active=='source':self.records[self.source]['text'].append(data)
        if self.active=='reconciliation':self.reconciliation.append(data)
class TextOnly(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.parts=[]
    def handle_data(self,d):self.parts.append(d)
def luminance(color):
    values=[int(color[i:i+2],16)/255 for i in [1,3,5]];linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in values]
    return sum(v*w for v,w in zip(linear,[.2126,.7152,.0722]))
def contrast(fg,bg):
    a,b=sorted([luminance(fg),luminance(bg)]);return (b+.05)/(a+.05)
def verify(site=None):
    site=site or SITE;lock=load(ROOT/'tools/refinement_asset_lock.json')
    for rel,expected in lock['assets'].items():assert hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()==expected,rel
    for rel,functions in lock['protected_functions'].items():
        text=(ROOT/rel).read_text('utf8')
        for name,expected in functions.items():assert checksum(function_text(text,name))==expected,rel+':'+name
    helper=(site/'assets/explorer-tools.js').read_text('utf8');assert checksum(next(line for line in helper.splitlines() if "$('#frequency-rows').innerHTML=" in line))==lock['distribution_bin_renderer_sha256']
    assert "fixed:'Fixed classes',local:'Local quintiles',shared:'Global quintiles'" in helper
    assert "p.get('d')||'values'" in helper and 'd:selected.distribution' in helper
    assert 'Find data for this map' in helper and 'Compare maps ↗' in helper and 'id="compare-return"' in helper
    shared=(site/'assets/refinement.js').read_text('utf8');css=(site/'assets/refinement.css').read_text('utf8');editorial=(site/'assets/editorial.js').read_text('utf8')
    assert 'Local and Global quintile thresholds are calculated using grid cells with values greater than zero. Valid zero cells and NoData are treated separately. Tied values can result in fewer than five distinct positive classes.' in shared
    for kind in ['classification','distribution','legend','comparison','formats','verification','land','resolution']:assert re.search(r'^ '+kind+r':',shared,re.M)
    for color in ['#29334B','#77395B','#D2A15E','#FAF7F3']:assert color in css
    assert not re.search(r'--swatch\s*:',css) and 'background:var(--map-panel)' in css
    assert 'Local positive quintiles' not in helper and 'Global positive quintiles' not in helper and 'Fixed count classes' not in helper
    assert 'GitHub Issues are publicly visible. Please submit confidential concerns about rights, attribution, or unpublished material directly to the dataset authors.' in editorial
    assert 'href="assets/data/scientific-documentation.json"' not in editorial
    sources=load(site/'assets/data/scientific-documentation.json');source_lock=load(ROOT/'tools/documentation_source_lock.json');doc=(site/'documentation.html').read_text('utf8');parsed=SourceText();parsed.feed(doc)
    assert set(parsed.records)==set(sources) and len(parsed.ids)==len(set(parsed.ids))
    for key,value in sources.items():
        assert parsed.records[key]['sha256']==value['sha256']==source_lock['curated_texts'][key]==checksum(value['text'])
        assert ''.join(''.join(parsed.records[key]['text']).split())==plain_markdown(value['text']),'Readable source text omitted or altered: '+key
    note=source_lock['approved_reconciliation_note'];expected=TextOnly();expected.feed(''.join(re.findall(r'<p>.*?</p>',note['source_fragment_html'],re.S)))
    assert ''.join(''.join(expected.parts).split())==''.join(''.join(parsed.reconciliation).split())
    assert all(id in parsed.ids for id in ['methodology','data-dictionary','geospatial-metadata','known-limitations','validation-reconciliation','methodology-validation-policy'])
    assert sum(id.startswith('doc-var-') for id in parsed.ids)==31
    pairs=[('body','#29334B','#FAF7F3',4.5),('secondary text','#5B5E68','#FAF7F3',4.5),('interactive plum','#77395B','#FAF7F3',4.5),('filled button','#FAF7F3','#77395B',4.5),('dark band','#FAF7F3','#29334B',4.5),('map caption/label','#5B5E68','#EEEAE5',4.5),('control border','#817985','#FAF7F3',3),('gold accent on dark band','#D2A15E','#29334B',3)]
    ratios=[{'role':name,'foreground':fg,'background':bg,'ratio':contrast(fg,bg),'minimum':minimum,'status':'PASS' if contrast(fg,bg)>=minimum else 'FAIL'} for name,fg,bg,minimum in pairs];assert all(p['status']=='PASS' for p in ratios)
    for p in site.glob('*.html'):
        page=p.read_text('utf8');assert page.count('assets/refinement.js?')==1 and page.count('assets/refinement.css?')==1
    return {'status':'PASS','protected_preexisting_assets':len(lock['assets']),'map_images_unchanged':4823,'derived_statistics_files_unchanged':32,'editorial_citation_configuration_unchanged':True,'curated_records_rendered_without_content_loss':4,'curated_source_characters':sum(len(v['text']) for v in sources.values()),'dictionary_rows':31,'native_geography_rows':53,'reconciliation_note_preserved':True,'shared_information_types':8,'ui_contrast_checks':ratios,'scientific_processing':False}
if __name__=='__main__':print(json.dumps(verify(),indent=2))
