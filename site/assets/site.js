'use strict';
const pageName=document.body.dataset.page;
const $=s=>document.querySelector(s);
const num=n=>new Intl.NumberFormat('en-US').format(n);
const compact=n=>{if(n===null||n===undefined)return '—';const a=Math.abs(n);return a>0&&a<.01?new Intl.NumberFormat('en-US',{maximumSignificantDigits:4,notation:a<.0001?'scientific':'standard'}).format(n):new Intl.NumberFormat('en-US',{maximumFractionDigits:2}).format(n)};
const escape=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let atlas,state;
const links=[['home','index.html','Home'],['explore','explore.html','Explore maps'],['methods','methods.html','Science & methods'],['access','data.html','Data access']];
const header=()=>`<a class="skip" href="#main">Skip to content</a><header class="site-header wrap"><a class="brand" href="index.html" aria-label="USGRIDS 2020 home"><img class="brand-logo" src="assets/brand/logo-horizontal.svg?v=branding-20261021" width="314" height="60" alt="USGRIDS 2020"></a><nav class="site-nav" aria-label="Main navigation">${links.map(([p,url,label],i)=>`<a href="${url}" ${pageName===p?'aria-current="page"':''}><span class="nav-number">0${i+1}</span>${label}</a>`).join('')}</nav><span class="edition" aria-label="Census vintage 2020">2020</span></header>`;
const footer=()=>`<footer class="site-footer wrap"><span>USGRIDS 2020 · Digital scientific atlas · Scientific Review Preview</span><span>${escape(editorial.publication_status)} <a href="methods.html#provenance">Citation</a></span></footer>`;
function mobileNational(layer,m){
 if(layer.geography!=='NATIONAL'||!m.panels.every(p=>p.display_crop))return '';
 return `<div class="national-mobile" aria-label="National map, responsive composition">${m.panels.map((p,i)=>{const [x,y,w,h]=p.display_crop;return `<div class="national-region region-${i}"><span class="region-label">${escape(p.name)}</span><div class="region-crop" style="aspect-ratio:${w*m.width/(h*m.height)}"><img src="${m.image}" alt="${escape(p.name)} · ${escape(classificationName(m.mode))}" style="width:${100/w}%;max-width:none;position:absolute;left:${-x/w*100}%;top:${-y/h*100}%;height:auto" decoding="async"></div></div>`}).join('')}</div>`;
}
function mapMarkup(layer,mode,cls=''){
 const m=layer.modes[mode];
 return `<figure class="map-frame ${cls} ${layer.geography==='NATIONAL'?'national-plate':''}" aria-label="${escape(atlas.geographies[layer.geography])} ${escape(atlas.variables[layer.variable].name)} map"><div class="map-surface" style="--map-ratio:${m.width/m.height}" data-geography="${layer.geography}" data-layer="${layer.id}" data-mode="${mode}"><img src="${m.image}" width="${m.width}" height="${m.height}" alt="${escape(atlas.variables[layer.variable].name)} in ${escape(atlas.geographies[layer.geography])}, ${escape(classificationName(m.mode))}. Colors correspond to the adjacent numeric legend. NoData is transparent; valid zero is white." decoding="async">${m.panels.length>1?m.panels.map(p=>`<span class="map-label" style="left:${p.label_position[0]}%;top:${p.label_position[1]}%">${escape(p.name)}</span>`).join(''):''}</div>${mobileNational(layer,m)}</figure>`;
}
function home(){
 const l=atlas.layers.NATIONAL_TOTALPOP,m=l.modes.fixed;
 return `<main id="main"><section class="hero wrap"><div class="hero-copy"><div class="eyebrow">2020 Census Gridded Data</div><h1>US Census<br>Grids 2020</h1><p>A national dataset of 29 demographic and housing count variables from the 2020 Census, allocated from Census blocks to a 15-arc-second geographic grid. Includes gridded land and water area for the 50 states, the District of Columbia, and Puerto Rico.</p><a class="text-link" href="explore.html">Explore maps <span class="arrow" aria-hidden="true">↗</span></a></div><div class="hero-map">${mapMarkup(l,'fixed')}<p class="map-caption">TOTALPOP · Allocated population per cell · Four geographic panels, different scales.<br>Northwestern Hawaiian Islands and western Aleutians omitted from this display; retained in all source data and statistics.</p></div></section><div class="home-legend wrap"><p>Population per cell<br><span class="quiet">Fixed count classes</span></p><div class="mini-legend" aria-label="Population legend">${m.legend.map(b=>`<span><i class="swatch ${b.category==='nodata'?'nodata':''}" style="--swatch:${b.color}" aria-hidden="true"></i>${escape(b.label)}</span>`).join('')}</div></div><section class="context-band"><div class="context-grid wrap"><div><h2>Spatial Resolution</h2><p>15-arc-second geographic grid (EPSG:4326). Cell dimensions vary with latitude.</p></div><div><h2>Geographic Coverage</h2><p>50 states, the District of Columbia, Puerto Rico, and a national composite.</p></div><div><h2>Data Contents</h2><p>29 demographic and housing count variables and two gridded area variables, delivered as 1,643 GeoTIFF rasters, 53 NetCDF files, and 52 Census-block Shapefile datasets.</p></div></div></section><section class="home-story wrap"><h2>Interpreting Gridded Census Data</h2><div><p>Grid-cell values are allocated estimates derived from Census blocks, not population counts observed directly at each cell. Fractional values are expected. Valid zeros and NoData are distinct.</p><a class="text-link" href="methods.html">Methods and documentation <span class="arrow" aria-hidden="true">↗</span></a></div></section></main>`;
}
function explorer(){return enhancedExplorerMarkup();}
async function update(){return updateExplorer('replace');}
function methods(){return editorialMethods();}
function access(){return editorialAccess();}
function review(){return editorialReview();}
let selectionEpoch=0;
const variableLoads=new Map();
document.addEventListener('error',event=>{
 if(event.target instanceof HTMLImageElement && document.documentElement.dataset.ready!=='error')showError(Error('The map image for this scientific selection could not be loaded. No alternate map was substituted.'));
},true);
async function ensureVariable(v){
 if(!atlas.layer_partitions)return;
 if(atlas.sample&&!atlas.explore_variable_ids.includes(v))throw Error('This variable is not included in the compact review sample. Use the complete local site described in START_HERE.md.');
 if(!Object.hasOwn(atlas.variables,v))throw Error('Unknown scientific variable: '+v);
 if(!variableLoads.has(v))variableLoads.set(v,(async()=>{
   const r=await fetch(atlas.layer_partitions[v]);if(!r.ok)throw Error('Scientific metadata unavailable for '+v);
   const layers=await r.json();if(!Object.values(layers).every(l=>l.variable===v))throw Error('Scientific partition identity mismatch');
   Object.assign(atlas.layers,layers);
 })());
 await variableLoads.get(v);
}
function showError(error){
 document.documentElement.dataset.ready='error';
 const main=$('main');main.innerHTML=`<div class="error-message"><h1>Selection unavailable.</h1><p>${escape(error.message)}</p><p>No unrelated scientific surface has been substituted.</p><a href="explore.html">Return to the atlas</a></div>`;
}
function changeSelection(rebuild=true){return update(rebuild).catch(showError)}
async function attachPageTools(){return initEditorialTools();}
async function ensureEditorialAssets(){
 const pending=[];
 if(typeof editorialMethods!=='function')pending.push(new Promise((resolve,reject)=>{const script=document.createElement('script');script.src='assets/editorial.js?v=editorial-20261021a';script.onload=resolve;script.onerror=()=>reject(Error('Editorial presentation unavailable'));document.head.append(script);}));
 if(!document.querySelector('link[href^="assets/editorial.css"]'))pending.push(new Promise((resolve,reject)=>{const style=document.createElement('link');style.rel='stylesheet';style.href='assets/editorial.css?v=editorial-20261021a';style.onload=resolve;style.onerror=()=>reject(Error('Editorial stylesheet unavailable'));document.head.append(style);}));
 await Promise.all(pending);
}
async function start(){
 await ensureEditorialAssets();
 const response=await fetch('assets/data/atlas.json');if(!response.ok)throw Error('Scientific metadata could not be loaded');atlas=await response.json();atlas.layers??={};
 const params=new URLSearchParams(location.search),g=params.get('g')||'NATIONAL',v=params.get('v')||'TOTALPOP';
 if(!Object.hasOwn(atlas.geographies,g)||!Object.hasOwn(atlas.variables,v))throw Error('No scientific record exists for the requested geography or variable.');
 if(atlas.sample&&['explore','access'].includes(pageName)&&!atlas.explore_geography_ids.includes(g))throw Error('This geography is not included in the compact review sample. Use the complete local site described in START_HERE.md.');
 if(['home','explore'].includes(pageName))await ensureVariable(pageName==='home'?'TOTALPOP':v);
 const editorialResponse=await fetch('assets/data/editorial.json?v=editorial-20261021a');if(!editorialResponse.ok)throw Error('Editorial documentation unavailable');editorial=await editorialResponse.json();
 document.body.innerHTML=header()+`<section class="review-notice" aria-label="Scientific review status"><div class="wrap"><p><strong>USGRIDS 2020 — Scientific Review Preview</strong><span>${escape(editorial.publication_status)}</span></p><a class="text-link" href="review.html">Scientific Review Guide ↗</a></div></section>`+({home,explore:explorer,methods,access,review,compare:comparisonPage}[pageName]())+footer();
 if(atlas.sample)document.body.insertAdjacentHTML('afterbegin','<p class="sample-notice">REVIEW SAMPLE · 6 geographies · 4 variables · 60 map views. The complete local site has 53 geographies and 31 variables.</p>');
 if(pageName==='explore')await initEnhancedExplorer();
 if(pageName==='compare')await initComparison();
 await attachPageTools();document.documentElement.dataset.ready='true';window.atlasData=atlas;
 const fragment=document.getElementById(location.hash.slice(1));if(fragment)fragment.scrollIntoView();
}
start().catch(showError);
