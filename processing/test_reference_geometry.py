"""Small, distributable input-format tests; no prepared scientific data or GIS license required."""
import hashlib
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np
from obtain_geometry import assert_https,install
try:
    from reference_geometry import HEADER,decode
except ImportError:
    decode=None


class ReferenceInputs(unittest.TestCase):
    """Exercise strict acquire-or-fail behavior and the signed, exact binary geometry encoding."""
    def test_verified_stream(self):
        with TemporaryDirectory() as td:
            path=Path(td)/'download'
            with self.assertRaises(ValueError):
                install(BytesIO(b'bad'),path,3,hashlib.sha256(b'yes').hexdigest())
            self.assertFalse(path.exists())
            self.assertEqual(install(BytesIO(b'yes'),path,3,hashlib.sha256(b'yes').hexdigest()).read_bytes(),b'yes')
            with self.assertRaises(ValueError):
                install(BytesIO(b'yes'),path,3,hashlib.sha256(b'yes').hexdigest())

    def test_https_only(self):
        for u in ('http://data.example/file','file:///input','https://user:password@data.example/file'):
            with self.assertRaises(ValueError):assert_https(u)

    @unittest.skipIf(decode is None,'optional binary geometry reader not installed')
    def test_lossless_ordinals(self):
        coords=np.array([[1.,0.,0.,0.,0.,1.,1.,1.,1.,0.],
                         [2.,0.,1.,0.,1.,1.,2.,1.,2.,0.]],dtype='<f8')
        encoded=np.vstack([np.array([1,2],dtype='<u8'),np.array([-7,-6],dtype='<i8').view('<u8'),coords.view('<u8').T])
        payload=np.diff(encoded,axis=1,prepend=np.zeros((12,1),dtype='<u8')).tobytes()
        fid,pid,wkb=decode(payload,2,'rectangles')
        self.assertEqual(fid.tolist(),[1,2]);self.assertEqual(pid.tolist(),[-7,-6])
        self.assertEqual(wkb.tolist(),[HEADER+v.tobytes() for v in coords])
        with self.assertRaises(ValueError):decode(payload[:-1],2,'rectangles')


if __name__=='__main__':unittest.main()
