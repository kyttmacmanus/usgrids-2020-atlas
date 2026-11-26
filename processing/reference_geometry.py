"""Restore a losslessly packed USGRIDS analysis fishnet without inferring any vertices.

The reference package is data, not code. Each row stores the original order, FID,
signed scientific PIXELID and all polygon vertex IEEE-754 bits. Integer differences
are used only for lossless compression. No coordinates are calculated from a grid
origin or a bounding box. Requires NumPy and pyogrio with the OpenFileGDB writer.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import re
import sys
from zipfile import ZipFile
import numpy as np
from pyogrio import read_info
from pyogrio.raw import read
from native_reference_io import unpack_empty, inserter

FISH_TEMPLATE='983bc3781652ae9f28b6cb1bddba6f4371f0752792dfd609b90042256e0c557f'

HEADER=bytes.fromhex("01060000000100000001030000000100000005000000")
RECORD=np.dtype([("header","V22"),("ordinates","<u8",(10,))])


def decode(payload,count,kind):
    """Decode one bounded chunk and return FIDs, PIXELIDs and exact feature WKB in native order."""
    if count<=0 or count>100000:
        raise ValueError("Invalid chunk dimensions")
    if kind=='rectangles':
        if len(payload)!=count*12*8:
            raise ValueError("Wrong rectangular chunk length")
        cols=np.frombuffer(payload,dtype='<u8').reshape(12,count).cumsum(axis=1,dtype='<u8')
        full=np.empty(count,dtype=RECORD)
        full['header']=np.void(HEADER)
        full['ordinates']=cols[2:].T
        data=full.tobytes()
        raw=np.fromiter((data[n:n+102] for n in range(0,len(data),102)),dtype=object,count=count)
        return cols[0].view('<i8'),cols[1].view('<i8'),raw
    if kind!='literal' or len(payload)<24*count:
        raise ValueError("Unknown or truncated lossless encoding")
    parts=np.frombuffer(payload,dtype='<i8',count=count*3).reshape(3,count)
    sizes=parts[2]
    if np.any(sizes<9) or sum(map(int,sizes))!=len(payload)-24*count:
        raise ValueError("Malformed literal record lengths")
    pos=24*count; raw=np.empty(count,dtype=object)
    for i,n in enumerate(sizes):
        raw[i]=payload[pos:pos+n];pos+=n
    return parts[0],parts[1],raw


def hashes():
    """Maintain three independent digests in source order for geometry, feature and scientific IDs."""
    return {k:hashlib.sha256() for k in ('fid','pixelid','wkb')}


def update(h,fids,ids,wkb):
    """Feed canonical little-endian IDs and unmodified WKB; data rows are never spatially resorted."""
    h['fid'].update(np.asarray(fids,dtype='<i8').tobytes())
    h['pixelid'].update(np.asarray(ids,dtype='<i8').tobytes())
    h['wkb'].update(b''.join(wkb))


def checked(info,h,total):
    """Fail closed if row count or any byte-level identity differs from the packaged reference."""
    if total!=info['features'] or {k:v.hexdigest() for k,v in h.items()}!=info['sha256']:
        raise ValueError("Geometry, FID or PIXELID failed exact source verification")


def restore(package,dest=None,template=None):
    """Verify or create a new native-precision FileGDB; then independently reopen and compare all features.

    Destination must not exist. Failure can leave an unverified partial database
    for diagnosis. Never use it unless final verification passes. Excludes source
    demographic attributes and GIS histories, which do not define this grid.
    """
    dest=Path(dest).resolve() if dest else None
    if dest and (dest.exists() or dest.suffix.lower()!='.gdb' or not dest.parent.is_dir()):
        raise ValueError("Specify a new .gdb within an existing directory")
    h=hashes(); total=0
    if dest and not template:
        raise ValueError('Supply the exact native template. A default new FileGDB is not numerically equivalent.')
    with ZipFile(package) as z, ExitStack() as stack:
        info=json.loads(z.read('geometry.json'))
        if info['format']!='USGRIDS exact fishnet 1' or info['crs']!='EPSG:4326' or not re.fullmatch('[a-zA-Z][a-zA-Z0-9_]*',info['layer']):
            raise ValueError("Unrecognized geometry source")
        p=info['precision'];fields=['PIXELID']
        opts={k.upper():str(p[k]) for k in ('XOrigin','YOrigin','XYScale','XYTolerance')}
        dtype=info['pixelid_dtype']
        if dtype not in ('int32','float64','int64'): raise ValueError("Unknown PIXELID dtype")
        if dest:
            unpack_empty(template,dest,'cells',FISH_TEMPLATE)
            put=stack.enter_context(inserter(dest,'cells',fields))
        for i,ch in enumerate(info['chunks']):
            member=z.getinfo(f'cells/{i:05d}.bin')
            if member.file_size>64*1024**2: raise ValueError("Chunk exceeds decompression limit")
            fid,ids,raw=decode(z.read(member),ch['rows'],ch['kind'])
            update(h,fid,ids,raw)
            if dest:
                if not np.array_equal(fid,np.arange(total+1,total+len(ids)+1)):
                    raise ValueError("Noncontiguous source FIDs: cannot assign a new default OID sequence")
                for oid,pid,wkb in zip(fid,ids,raw,strict=True):
                    put(oid,wkb,(float(pid),))
            total+=len(raw)
        checked(info,h,total)
    if dest:
        layer='cells'; out=read_info(dest,layer=layer)
        if out['crs']!=info['crs'] or out['features']!=total or 'PIXELID' not in out['fields']:
            raise ValueError("Restored feature schema does not match")
        # The GIS writer can quantize output. Never assume that passing the input
        # checks proves the resulting on-disk feature class matches.
        h=hashes()
        for start in range(0,total,50000):
            _,fids,raw,attrs=read(dest,layer=layer,return_fids=True,columns=fields,
                                   skip_features=start,max_features=min(50000,total-start))
            update(h,fids,attrs[0],raw)
        checked(info,h,total)
        import pyogrio
        import xml.etree.ElementTree as et
        defs=pyogrio.read_dataframe(dest,sql='SELECT Name, Definition FROM GDB_Items',read_geometry=False)
        xml=et.fromstring(defs[defs.Name==layer].iloc[0].Definition)
        for k in opts:
            vals=[float(n.text) for n in xml.iter() if n.tag.rsplit('}',1)[-1].upper()==k]
            if not vals or any(v!=float(opts[k]) for v in vals):
                raise ValueError("Native spatial storage precision did not survive: "+k)
    return {'features':total,'verified':'exact stored WKB, row order, FIDs and PIXELIDs',
            'native_restoration':dest is not None,'layer':'cells' if dest else info['layer']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package',type=Path)
    parser.add_argument('--new-gdb',type=Path,help='Restore and re-read this new FileGDB; omit to verify only.')
    parser.add_argument('--native-template',type=Path,help='Matching verified empty native GDB template ZIP.')
    args=parser.parse_args()
    print(json.dumps(restore(args.package,args.new_gdb,args.native_template),indent=2))
