"""Verify released Census-block coordinates; restore the original storage precision when required.

Inputs are the geography's USGRIDS block Shapefile, a small scientific reference
specification, and the common empty native block template. Counts are not read
from the Shapefile. For Puerto Rico the original processing input already was
the distributed Shapefile, so no geodatabase conversion should be performed.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile
import numpy as np
import pyogrio
from pyogrio.raw import read
from native_reference_io import inserter,unpack_empty

BLOCK_TEMPLATE='e5e5afab2211d5ef0d94574ca482672c33373f54a39784ae77d60245c09ed1d3'
PREFIX=bytes.fromhex('010600000001000000')
POLYGON=bytes.fromhex('0103000000')


def run(shapefile,spec,dest=None,template=None):
    """Check all rows and exact polygon ordinates; optionally create a fresh verified native block class."""
    s=json.loads(Path(spec).read_text('utf8'))
    if s['format']!='USGRIDS ordered blocks 1' or not s['validated']:
        raise ValueError('An independently verified block specification is required')
    direct=s['state_fips']=='72'; geometry=Path(shapefile)
    if geometry.suffix.lower()=='.zip':
        # Read only known Census-block components via GDAL's read-only ZIP
        # transport. Do not extract arbitrary archive paths or create scratch
        # data. For large states external extraction may give faster I/O.
        member='Shapefile/blocks_state_'+s['state_fips']
        with ZipFile(geometry) as z:
            names=z.namelist()
            if any(names.count(member+ext)!=1 for ext in ('.shp','.dbf','.shx','.prj','.cpg')):
                raise ValueError('Missing or ambiguous geography-specific Shapefile members')
        geometry='/vsizip/'+geometry.resolve().as_posix()+'/'+member+'.shp'
    elif geometry.suffix.lower()!='.shp':
        raise ValueError('Supply the released science ZIP or its complete block Shapefile family')
    if dest and (direct or not template):raise ValueError('A native template is required for GDB states; PR uses the Shapefile directly')
    fields=['COUNTYFP20','GEOID20']; total=s['rows']
    attrs={};result={}
    for name,path in [('shapefile',geometry)]+([('restored_gdb',Path(dest))] if dest else []):
        gdb=name=='restored_gdb'
        with ExitStack() as stack:
            put=None
            if dest and not gdb:
                unpack_empty(template,Path(dest),'blocks',BLOCK_TEMPLATE)
                put=stack.enter_context(inserter(dest,'blocks',fields))
            info=pyogrio.read_info(path)
            if info['features']!=total or info['crs']!='EPSG:4326':raise ValueError('Wrong block count or CRS')
            hashes={k:hashlib.sha256() for k in ('wkb','geoid','county','oid')}
            # FID sequences can contain original gaps; the supply record preserves
            # only those deviations from the otherwise monotonic native row order.
            ranges=np.asarray(s['oid_runs'],dtype='int64')
            if ranges.ndim!=2 or ranges.shape[1]!=2 or ranges[0,0]!=0 or np.any(np.diff(ranges[:,0])<=0):
                raise ValueError('Invalid source OID run map')
            for offset in range(0,total,12000):
                md,fids,raw,values=read(path,layer='blocks' if gdb else None,columns=fields,return_fids=True,
                                      skip_features=offset,max_features=min(total-offset,12000))
                attr=dict(zip(md['fields'],values));pos=np.arange(offset,offset+len(raw),dtype='int64')
                oid=pos+ranges[np.searchsorted(ranges[:,0],pos,side='right')-1,1]
                if gdb and not np.array_equal(oid,fids):raise ValueError('Restored OIDs differ from source')
                for j,w in enumerate(raw):
                    # A single-ring/member Polygon can have the same ordered vertices
                    # as a 1-part MultiPolygon. Change only the wrapper, not a vertex.
                    w=PREFIX+w if not direct and not gdb and w.startswith(POLYGON) else w
                    hashes['wkb'].update(w)
                    if put:put(oid[j],w,(str(attr['COUNTYFP20'][j]),str(attr['GEOID20'][j])))
                hashes['oid'].update(oid.astype('<i8').tobytes())
                for src,k in (('COUNTYFP20','county'),('GEOID20','geoid')):
                    hashes[k].update(('\n'.join(attr[src])+'\n').encode('ascii'))
            if {k:h.hexdigest() for k,h in hashes.items()}!=s['sha256']:
                raise ValueError('Source fidelity verification failed; do not use the output')
            if gdb:
                # Coordinate equality alone does not establish that future ArcGIS
                # overlays will use the same quantization domain and tolerance.
                from xml.etree import ElementTree as et
                defs=pyogrio.read_dataframe(path,sql='SELECT Name,Definition FROM GDB_Items',read_geometry=False)
                root=et.fromstring(defs[defs.Name=='blocks'].iloc[0].Definition)
                for tag,expected in {'XOrigin':-400.,'YOrigin':-400.,'XYScale':999999999.99999988,
                                     'XYTolerance':8.983152841195215e-09}.items():
                    vals=[float(n.text) for n in root.iter() if n.tag.rsplit('}',1)[-1]==tag]
                    if not vals or any(v!=expected for v in vals):
                        raise ValueError('Native block precision did not survive: '+tag)
            result[name]='PASS'
    return {'state':s['state_fips'],'rows':total,'checks':result,'output_layer':'blocks' if dest else None}


if __name__=='__main__':
    par=argparse.ArgumentParser(description=__doc__);par.add_argument('shapefile');par.add_argument('spec')
    par.add_argument('--new-gdb');par.add_argument('--native-template'); args=par.parse_args()
    print(json.dumps(run(args.shapefile,args.spec,args.new_gdb,args.native_template),indent=2))
