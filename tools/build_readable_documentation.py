"""Deterministic HTML presentation of the already-public curated Markdown records.

No GIS, scientific recomputation, source mutation, or external Markdown runtime.
"""
from pathlib import Path
import json,re,html,hashlib
ROOT=Path(__file__).resolve().parents[1];SITE=ROOT/'site'
RECORDS=[('methodology','METHODOLOGY.md'),('data-dictionary','DATA_DICTIONARY.md'),('geospatial-metadata','GEOSPATIAL_METADATA.md'),('known-limitations','KNOWN_LIMITATIONS.md')]
def digest(text):return hashlib.sha256(text.encode('utf8')).hexdigest()
def slug(text):return re.sub(r'[^a-z0-9]+','-',text.lower()).strip('-')
def inline(text):
    # Source content is escaped before limited inline formatting; no source HTML executes.
    out=[]
    for i,part in enumerate(text.split('`')):
        if i%2:out.append('<code>'+html.escape(part)+'</code>');continue
        escaped=html.escape(part)
        escaped=re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',escaped)
        escaped=re.sub(r'https://[^\s<]+',lambda m:'<a href="'+m.group(0)+'" target="_blank" rel="noopener">'+m.group(0)+'</a>',escaped)
        out.append(escaped)
    return ''.join(out)
def render(text,record_id):
    lines=text.splitlines();out=[];toc=[];i=0
    while i<len(lines):
        line=lines[i]
        if not line.strip():i+=1;continue
        heading=re.match(r'^(#{1,6}) (.+)$',line)
        if heading:
            level=2 if len(heading[1])==1 else 3;title=heading[2];anchor=record_id+'-'+('overview' if level==2 else slug(title));toc.append((anchor,title));out.append(f'<h{level} id="{anchor}">{inline(title)}</h{level}>');i+=1;continue
        if line.startswith('|'):
            rows=[]
            while i<len(lines) and lines[i].startswith('|'):
                cells=[c.strip() for c in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?',c) for c in cells):rows.append(cells)
                i+=1
            cls='dictionary-table' if record_id=='data-dictionary' else 'geography-table' if record_id=='geospatial-metadata' else ''
            out.append(f'<div class="doc-table-region" tabindex="0" role="region" aria-label="Scrollable {record_id.replace("-"," ")} table"><table class="doc-table {cls}"><thead><tr>'+''.join('<th scope="col">'+inline(c)+'</th>' for c in rows[0])+'</tr></thead><tbody>')
            for cells in rows[1:]:
                anchor=' id="doc-var-'+html.escape(cells[0])+'"' if record_id=='data-dictionary' else ''
                out.append('<tr'+anchor+'>'+''.join('<td>'+('<code>'+html.escape(c)+'</code>' if record_id=='data-dictionary' and n in [0,2] else inline(c))+'</td>' for n,c in enumerate(cells))+'</tr>')
            out.append('</tbody></table></div>');continue
        if line.startswith('- '):
            out.append('<ul>')
            while i<len(lines) and lines[i].startswith('- '):out.append('<li>'+inline(lines[i][2:])+'</li>');i+=1
            out.append('</ul>');continue
        paragraph=[]
        while i<len(lines) and lines[i].strip() and not re.match(r'^(?:#{1,6} |\||- )',lines[i]):paragraph.append(lines[i]);i+=1
        assert paragraph,'Unhandled source line: '+lines[i]
        out.append('<p>'+inline(' '.join(paragraph))+'</p>')
    return '\n'.join(out),toc
def build():
    sources=json.loads((SITE/'assets/data/scientific-documentation.json').read_text('utf8'));lock=json.loads((ROOT/'tools/documentation_source_lock.json').read_text('utf8'))
    sections=[];toc=[]
    for record_id,key in RECORDS:
        source=sources[key];assert digest(source['text'])==source['sha256']==lock['curated_texts'][key]
        content,headings=render(source['text'],record_id);toc.extend(headings)
        sections.append(f'<section class="doc-record" id="{record_id}" data-doc-source="{key}" data-source-sha256="{source["sha256"]}"><div class="doc-source-content">{content}</div><details class="doc-source-identity"><summary>Retained source identity</summary><p>{key} · complete source text rendered without scientific edits.</p><code>SHA-256 {source["sha256"]}</code><a href="assets/data/scientific-documentation.json">Machine-readable source records (JSON)</a></details></section>')
    note=lock['approved_reconciliation_note'];assert digest(note['source_fragment_html'])==note['source_fragment_sha256']
    paragraphs=re.findall(r'<p>.*?</p>',note['source_fragment_html'],re.S)
    assert len(paragraphs)==4
    sections.append('<section class="doc-record" id="validation-reconciliation"><h2>Validation and reconciliation</h2><p class="doc-source-note">The following national note is retained from the approved Science &amp; Methods page. Numerical values and scientific qualifications are unchanged.</p><div class="approved-reconciliation-content">'+''.join(paragraphs)+'</div><p><a href="#methodology-validation-policy">Retained validation policy and accepted-exception criteria</a></p><details class="doc-source-identity"><summary>Approved note identity</summary><p>Source: Science &amp; Methods, national reconciliation, approved commit '+note['source_commit']+'.</p><code>Source fragment SHA-256 '+note['source_fragment_sha256']+'</code></details></section>')
    toc.append(('validation-reconciliation','Validation and reconciliation'))
    nav='<nav class="documentation-toc" aria-label="Technical documentation sections">'+''.join(f'<a href="#{anchor}">{html.escape(title)}</a>' for anchor,title in toc)+'</nav>'
    main='<main id="main" class="wrap editorial-page documentation-page"><header class="editorial-intro"><p class="eyebrow">USGRIDS 2020 / Scientific documentation</p><h1>Technical Documentation</h1><p>Detailed methodology, the authoritative corrected dictionary, native geospatial metadata, known limitations, and approved reconciliation context.</p><p class="doc-source-note">Retained records are reproduced in full. Historical implementation and administrative wording remain source context; <a href="methods.html#provenance">current citation and publication guidance</a> records the owner-selected authors and pending archive publication.</p><div class="doc-related"><a href="methods.html">Science &amp; Methods</a><a href="methods.html#allocation">Allocation equation and explanation</a><a href="explore.html">Explore maps</a><a href="data.html">Find scientific data</a></div></header><div class="documentation-search"><label for="documentation-search">Find a documentation section</label><input id="documentation-search" type="search" placeholder="Try validation, geography or limitations" autocomplete="off"></div><p id="documentation-search-status" class="documentation-search-status" role="status" aria-live="polite"></p>'+nav+''.join(sections)+'</main>'
    template=(SITE/'methods.html').read_text('utf8');head=re.search(r'<head>(.*?)</head>',template,re.S).group(1);head=re.sub(r'<title>.*?</title>','<title>Technical Documentation | USGRIDS 2020 · Scientific Review Preview</title>',head);head=re.sub(r'<meta name="description" content="[^"]*">','<meta name="description" content="Readable, checksum-verified USGRIDS methodology, dictionary, geospatial metadata, scientific limitations and reconciliation documentation.">',head)
    document='<!doctype html>\n<html lang="en"><head>'+head+'</head><body data-page="documentation">'+main+'<noscript>These technical records are readable without JavaScript. Interactive atlas controls require JavaScript.</noscript></body></html>\n'
    (SITE/'documentation.html').write_text(document,encoding='utf8');return {'source_records':4,'source_characters':sum(len(sources[k]['text']) for _,k in RECORDS),'source_headings':len(toc),'approved_reconciliation_paragraphs':len(paragraphs)}
if __name__=='__main__':print(json.dumps(build(),indent=2))
