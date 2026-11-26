"""Small deterministic examples of the public DHC contract; no Internet needed."""
import csv
import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import prepare_counts as p


class CountPreparationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.src=self.root/'source.csv'
        self.out=self.root/'master.csv'
        self.keys=['010010001001000','010010001001001']
        digest=hashlib.sha256(('\n'.join(self.keys)+'\n').encode('ascii')).hexdigest()
        self.geo=dict(abbr='AL',state_fips='01',expected_blocks=2,sorted_geoid_sha256=digest)
        self.fields=sorted(set().union(*p.formulas().values()))
        self.zero={f:'0' for f in self.fields}
        # Construct four people: female age 0, female 18–19, male 25–29, male 85+.
        self.values=dict(self.zero)
        self.values.update(P1_001N='4',P14_024N='1',P12_031N='1',P12_011N='1',P12_025N='1',
                           P3_002N='2',P3_003N='1',P3_007N='1', P4_002N='3',P4_003N='1',
                           P9_005N='1',P9_006N='1', P16_001N='1',H8_001N='1', H1_001N='2',
                           H3_002N='1',H3_003N='1',H10_002N='1',H12_011N='1')

    def write(self,records):
        names=list(dict.fromkeys(k for row in records for k in row))
        with self.src.open('w',newline='',encoding='utf8') as dest:
            writer=csv.DictWriter(dest,fieldnames=names);writer.writeheader();writer.writerows(records)

    def pair(self):
        return [dict(GEOID=k,**v) for k,v in zip(self.keys,[self.values,self.zero])]

    def test_state_registry(self):
        registry=p._table('geographies.csv')
        self.assertEqual(len({r['state_fips'] for r in registry}),52)
        for key in ['01','AL','Alabama',1]: self.assertEqual(p.geography(key)['state_fips'],'01')
        for key in ['DC','PR','Alaska']: self.assertIn(p.geography(key),registry)
        with self.assertRaises(ValueError): p.geography('national')
        self.assertEqual(len(self.fields),95)

    def test_expected_counts_and_zeroes(self):
        self.write(self.pair()); result=p._prepare(self.geo,self.src,self.out)
        self.assertEqual(result['blocks'],2)
        with self.out.open() as file:
            rows=list(csv.DictReader(file))
        expected=dict(TOTALPOP=4,AUND1=1,A1TO4=0,A5TO17=0,A18TO24=1,AUND25=2,
            A25OV=2,A25TO64=1,A65TO79=0,A80OV=1,WOMCHILD=1,WHITE=2,BLACK=1,
            AMIND=0,ASIAN=0,HAWPI=0,OTHER=1,TWOMORE=0,NHISP=3,HISP=1,NHISPWHITE=1,
            NHISPBLACK=1,HOUSEHOLD=1,HHPOP=1,HHUNIT=2,OCC=1,OWN=1,VACANT=1,HU1P=1)
        self.assertEqual(rows[0],dict(GEOID=self.keys[0],**{k:str(v) for k,v in expected.items()}))
        self.assertEqual(rows[1],dict(GEOID=self.keys[1],**dict.fromkeys(expected,'0')))
        with self.assertRaises(FileExistsError): p._prepare(self.geo,self.src,self.out)

    def test_bad_official_inputs_are_not_written(self):
        for field,value in [('GEOID',self.keys[1]),('GEOID','10010001001000'),
                            ('GEOID','020010001001000'),('GEOID','010010001009999'),
                            ('P1_001N',None),('P1_001N','-666666666'),('P1_001N','4.0'),
                            ('P1_001N','2')]:
            with self.subTest(field=field,value=value):
                records=self.pair();records[0][field]=value; self.write(records)
                with self.assertRaises(ValueError): p._prepare(self.geo,self.src,self.out)
                self.assertFalse(self.out.exists())
        with self.assertRaises(ValueError):
            p._identifier(dict(GEO_ID='1000000US'+self.keys[0],GEOID=self.keys[1]),'01')
        records=self.pair()
        for row in records: del row['P1_001N']
        self.write(records)
        with self.assertRaises(ValueError): p._prepare(self.geo,self.src,self.out)
        self.write(self.pair()[:1])
        with self.assertRaises(ValueError): p._prepare(self.geo,self.src,self.out)
        self.assertFalse(self.out.exists())

    def test_zip_and_optional_alternate_vacancy_field(self):
        rr=self.pair()
        for r in rr:r['H5_001N']=r['H3_003N']
        self.write(rr)
        archive=self.root/'input.zip'
        with zipfile.ZipFile(archive,'w') as z:z.write(self.src,'in/data.csv')
        self.assertEqual(p._prepare(self.geo,archive,self.out)['blocks'],2)
        rr[0]['H5_001N']='0'; self.write(rr)
        with self.assertRaises(ValueError): p._prepare(self.geo,self.src,self.root/'bad.csv')

    def test_keyed_api_batches_and_missing_rows(self):
        def responder(drop=False):
            def request(params):
                fields=dict(params)['get'].split(',')
                if fields==['NAME']:return [['NAME','state','county'],['Example','01','001']]
                header=[*fields,'state','county','tract','block']
                records=[[*(d[f] for f in fields),'01','001','000100',k[-4:]]
                         for k,d in zip(self.keys,[self.values,self.zero])]
                if fields[0]!=self.fields[0]:
                    records.reverse()
                    if drop:records.pop()
                return [header,*records]
            return request
        self.assertEqual(p._fetch(self.geo,self.src,responder())['blocks'],2)
        p._prepare(self.geo,self.src,self.out)
        with self.out.open() as f:
            self.assertEqual([(r['GEOID'],r['TOTALPOP']) for r in csv.DictReader(f)],list(zip(self.keys,['4','0'])))
        bad=self.root/'partial.csv'
        with self.assertRaises(ValueError): p._fetch(self.geo,bad,responder(drop=True))
        self.assertFalse(bad.exists())

    def test_public_geographic_id_receipt_without_counts(self):
        # NAME alone returns block identifiers but requests no Census count fields.
        def names(params):
            q=dict(params)
            self.assertEqual(q["get"],"NAME")
            if q["for"]=="county:*":
                return [["county","NAME","state"],["001","Example county","01"]]
            self.assertEqual(q["for"],"block:*")
            self.assertEqual([v for k,v in params if k=="in"],["state:01","county:001","tract:*"])
            return [["NAME","block","tract","county","state"],
                    *[["Example block",k[-4:],"000100","001","01"] for k in reversed(self.keys)]]
        with patch.object(p,"geography",return_value=self.geo), patch.object(p,"_request",side_effect=names):
            self.assertEqual(p.verify_geography("01"),
                             {"state_fips":"01","blocks":2,"sorted_geoid_sha256":self.geo["sorted_geoid_sha256"]})

if __name__=='__main__':
    unittest.main()
