"""Write ordered scientific features into a new, empty native-precision FileGDB template.

An ordinary new FileGDB can round the original XY scale before it writes any
coordinates. A verified empty native template preserves the double-precision
domain and tolerance. Explicit OIDs preserve input order even if an empty
template's next automatically allocated OID is not one. Uses GDAL's public C
API from the same pyogrio wheel used to re-check the file after closure.
"""
import contextlib
import ctypes as C
import hashlib
from pathlib import Path
import re
import shutil
from zipfile import ZipFile
import pyogrio


def library():
    """Load pyogrio's own GDAL, not an unrelated GIS library from PATH."""
    pkg=Path(pyogrio.__file__).resolve().parent
    candidates=[]
    for folder in (pkg.parent/'pyogrio.libs',pkg/'.dylibs',pkg.parent/'.dylibs'):
        if folder.is_dir():
            candidates += [p for p in folder.iterdir() if re.fullmatch(r'(?:lib)?gdal(?:[-.].*)?(?:\.dll|\.dylib|\.so(?:[.]\d+)*)',p.name,re.I)]
    if len(candidates)!=1:
        raise RuntimeError("Expected exactly one GDAL shared library bundled with pyogrio; use the documented wheel environment")
    lib=C.CDLL(str(candidates[0]))
    p=C.c_void_p; s=C.c_char_p; i=C.c_int
    for name,result,args in [
        ('GDALOpenEx',p,[s,C.c_uint,p,p,p]),('GDALClose',i,[p]),('GDALDatasetGetLayerByName',p,[p,s]),
        ('OGR_L_GetLayerDefn',p,[p]),('OGR_FD_GetFieldIndex',i,[p,s]),('OGR_F_Create',p,[p]),
        ('OGR_F_SetFID',i,[p,C.c_int64]),('OGR_F_SetFieldDouble',None,[p,i,C.c_double]),
        ('OGR_F_SetFieldString',None,[p,i,s]),('OGR_F_SetFieldInteger64',None,[p,i,C.c_int64]),
        ('OGR_G_CreateFromWkb',i,[s,p,C.POINTER(p),i]),('OGR_F_SetGeometryDirectly',i,[p,p]),
        ('OGR_L_CreateFeature',i,[p,p]),('OGR_F_Destroy',None,[p])]:
        f=getattr(lib,name);f.restype=result;f.argtypes=args
    return lib


def unpack_empty(template,dest,layer,expected_sha):
    """Verify trusted template bytes and extract a single empty feature class without paths from the ZIP."""
    with Path(template).open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=expected_sha:
            raise ValueError('Unexpected native schema template')
    dest=Path(dest)
    if dest.exists() or dest.suffix.lower()!='.gdb':raise ValueError('A fresh .gdb path is required')
    with ZipFile(template) as z:
        members=z.infolist()
        if not members or len(members)>150 or sum(i.file_size for i in members)>8*1024**2:
            raise ValueError('Unexpected template size')
        names=[i.filename for i in members]
        if len(set(names))!=len(names) or not all(re.fullmatch(r'reference[.]gdb/(?:gdb|timestamps|a[0-9A-Fa-f]{8}(?:[.][a-zA-Z_0-9]+)+)',n) for n in names):
            raise ValueError('Unexpected native template member')
        dest.mkdir()
        for info in members:
            with z.open(info) as src,(dest/info.filename.split('/')[1]).open('xb') as out:
                shutil.copyfileobj(src,out)
    if pyogrio.list_layers(dest).tolist()!=[[layer,'MultiPolygon']] or pyogrio.read_info(dest,layer=layer)['features']!=0:
        raise ValueError('Template must contain only an empty native polygon feature class')


@contextlib.contextmanager
def inserter(dest,layer,fields):
    """Return a row writer for the newly staged feature class. Preserve WKB, IDs and named scientific fields."""
    lib=library(); ds=lib.GDALOpenEx(str(Path(dest).resolve()).encode('utf8'),5,None,None,None)
    if not ds:raise RuntimeError('Cannot open new template for writing')
    try:
        ly=lib.GDALDatasetGetLayerByName(ds,layer.encode());defn=lib.OGR_L_GetLayerDefn(ly)
        ix=[lib.OGR_FD_GetFieldIndex(defn,n.encode()) for n in fields]
        if min(ix)<0:raise ValueError('Scientific template fields are absent')
        def put(fid,wkb,values):
            """Create one explicitly keyed native feature; never update an existing input feature."""
            ft=lib.OGR_F_Create(defn)
            try:
                if lib.OGR_F_SetFID(ft,int(fid)):raise ValueError('Unexpected feature ID')
                geom=C.c_void_p()
                if lib.OGR_G_CreateFromWkb(wkb,None,C.byref(geom),len(wkb)) or lib.OGR_F_SetGeometryDirectly(ft,geom):
                    raise ValueError('Invalid source polygon WKB')
                for index,value in zip(ix,values,strict=True):
                    if isinstance(value,str):lib.OGR_F_SetFieldString(ft,index,value.encode('utf8'))
                    elif isinstance(value,float):lib.OGR_F_SetFieldDouble(ft,index,value)
                    else:lib.OGR_F_SetFieldInteger64(ft,index,int(value))
                if lib.OGR_L_CreateFeature(ly,ft):raise ValueError('Cannot insert source geometry at the required OID')
            finally:lib.OGR_F_Destroy(ft)
        yield put
    finally:
        if lib.GDALClose(ds):raise RuntimeError('Failed to close native database')
