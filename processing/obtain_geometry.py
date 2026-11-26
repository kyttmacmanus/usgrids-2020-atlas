"""Obtain one approved scientific input over HTTPS and verify its published identity before use.

Use the DOI landing page to get the original-file download link and its expected
size and SHA-256. The utility never searches for a near match, saves credentials
or uploads anything. No bulk research data are embedded in the source repository.
"""
import argparse
import hashlib
import os
from pathlib import Path
import re
import tempfile
from urllib import parse,request


class HTTPSOnly(request.HTTPRedirectHandler):
    """Permit repository-to-object-store redirects, never a plaintext or local redirect."""
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        """Reject non-HTTPS or embedded credentials on every redirect."""
        assert_https(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def assert_https(url):
    """Require an explicit HTTPS location without user, password or fragment."""
    u=parse.urlsplit(url)
    if u.scheme!='https' or not u.hostname or u.username or u.password or u.fragment:
        raise ValueError('Expected an HTTPS file download URL without embedded credentials')


def install(stream,dest,expected_size,expected_sha256):
    """Stream bounded bytes to same-disk scratch; expose a new verified file or nothing."""
    target=Path(dest).resolve()
    if target.exists() or not target.parent.is_dir(): raise ValueError('Choose a new local file')
    if expected_size<=0 or not re.fullmatch(r'[0-9a-fA-F]{64}',expected_sha256):
        raise ValueError('Require a positive byte size and the original, trusted SHA-256')
    digest=hashlib.sha256(); total=0
    with tempfile.TemporaryDirectory(dir=target.parent,prefix='usgrids_input_') as td:
        stage=Path(td)/'original'
        with stage.open('xb') as f:
            while chunk:=stream.read(1024*1024):
                total+=len(chunk)
                if total>expected_size: raise ValueError('Response exceeds published size')
                digest.update(chunk); f.write(chunk)
        if total!=expected_size or digest.hexdigest()!=expected_sha256.lower():
            raise ValueError('Incomplete or incorrect download; do not use it')
        os.link(stage,target)
    return target


def fetch(url,dest,size,sha256):
    """Fetch an uncredentialed public file once, then compare independent byte identity."""
    assert_https(url)
    with request.build_opener(HTTPSOnly).open(url,timeout=180) as src:
        return install(src,dest,size,sha256)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('url');p.add_argument('new_file');p.add_argument('--bytes',type=int,required=True)
    p.add_argument('--sha256',required=True)
    a=p.parse_args()
    print(fetch(a.url,a.new_file,a.bytes,a.sha256))
