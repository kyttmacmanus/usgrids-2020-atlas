"""Small public fixtures for the national scientific contract; no GIS license needed."""
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import numpy as np
import national as N


class NationalTests(unittest.TestCase):
    """Distinguish arithmetical/contract tests from actual ArcGIS integration."""

    def test_stats(self):
        """Count valid zero; reject infinity; exclude NaN from a Float64 sum."""
        self.assertEqual(N.array_stats(np.array([[np.nan,0.],[0.25,0.5]])),(3,.75,0.))
        self.assertEqual(N.array_stats([np.nan]),(0,0.,None))
        with self.assertRaises(ValueError): N.array_stats([float('inf')])
        with self.assertRaises(ValueError): N.array_stats([float('-inf')])

    def test_reconciliation(self):
        """The full component set and the frozen tolerance are required, even at zero."""
        totals=[0.]*50+[0.125,0.25]
        self.assertEqual(N.reconcile(.375,totals)['residual'],0)
        with self.assertRaises(ValueError): N.reconcile(.3751,totals)
        with self.assertRaises(ValueError): N.reconcile(.375,totals[1:])
        with self.assertRaises(ValueError): N.reconcile(math.nan,totals)

    def test_native_operand_order(self):
        """Verify argument dispatch only; the mock is not a licensed rasterization run."""
        source=[Path(s+'.tif') for s,_ in N.registry()]
        arcpy=Mock()
        N.geographic_sum(arcpy,source,Path('result.tif'))
        arcpy.ia.CellStatistics.assert_called_once_with([str(p) for p in source],'SUM','DATA','SINGLE_BAND',90,'AUTO_DETECT')
        arcpy.ia.CellStatistics.return_value.save.assert_called_once_with('result.tif')
        self.assertEqual([source[0].stem,source[-1].stem],['01','72'])
        with self.assertRaises(ValueError): N.geographic_sum(arcpy,source[1:],Path('unused.tif'))

    def test_cropped_dateline_lattice(self):
        """Reject materially shifted component origins; accept harmless fractional serialization drift."""
        a=Mock()
        r=a.Raster.return_value
        r.bandCount=1; r.pixelType='F64'; r.spatialReference.factoryCode=4326
        r.meanCellHeight=r.meanCellWidth=N.CELL_DEGREES
        r.extent.XMin=N.WEST+N.CELL_DEGREES*0.000108; r.extent.YMax=N.NORTH
        r.width=N.SHAPE[1]; r.height=N.SHAPE[0]
        r.extent.XMax=r.extent.XMin+r.width*N.CELL_DEGREES; r.extent.YMin=N.NORTH-r.height*N.CELL_DEGREES
        N.grid(a,'mock',national=True)
        r.extent.XMin+=N.CELL_DEGREES*0.5
        with self.assertRaises(ValueError): N.grid(a,'mock')

    def test_refuse_unsafe_input(self):
        """Check an incomplete input tree and output collision without creating GIS data."""
        with TemporaryDirectory() as d:
            p=Path(d); root=p/'inputs'; root.mkdir(); config=p/'config.json'
            cfg={'kind':'national','layout':'archive_tiffs','component_root':'inputs','outdir':'fresh'}
            config.write_text(json.dumps(cfg),encoding='utf8')
            with self.assertRaises(FileNotFoundError): N.configuration(config)
            cfg['outdir']='inputs/nested'
            config.write_text(json.dumps(cfg),encoding='utf8')
            with self.assertRaises(ValueError): N.configuration(config)
            with self.assertRaises(OSError): N.disk_gate(root,2**80)
        self.assertGreater(N.space_needed('spatial'),N.space_needed('netcdf'))

    def test_single_scope_can_use_52_counts_without_areas(self):
        """TOTALPOP-only config needs 52 native count paths, not 31 full state sets."""
        with TemporaryDirectory() as d:
            p=Path(d); root=p/'inputs'; root.mkdir(); cfg=p/'state_maps.json'
            cfg.write_text(json.dumps({'kind':'national','layout':'archive_tiffs',
                                      'component_root':'inputs','outdir':'new'}),encoding='utf-8')
            for f,s in N.registry():
                (root/f).mkdir(); (root/f/f'usa{s}_TOTALPOP_CNT.tif').touch()
            _,group,_,_=N.configuration(cfg,needed=('TOTALPOP',))
            self.assertEqual(len(group),52)
            self.assertTrue(all(set(m)=={'TOTALPOP'} for m in group.values()))
            with self.assertRaises(FileNotFoundError): N.configuration(cfg)
            with self.assertRaises(ValueError): N.run(cfg,'netcdf',variable='TOTALPOP')

    def test_intermediate_relocation_fails_closed(self):
        """Injected copy corruption must never delete the surviving stage TIFF."""
        with TemporaryDirectory() as d:
            p=Path(d); first=p/'working_native'/'case'; first.mkdir(parents=True)
            dest=p/'scratch'; dest.mkdir(); image=first/'TOTALPOP_stage.tif'
            image.write_bytes(b'fixture'); arcpy=Mock()
            with patch.object(N,'disk_gate'), patch.object(N.shutil,'copyfile',side_effect=lambda a,b:Path(b).write_bytes(b'changed')):
                with self.assertRaises(IOError): N.verified_tiff_relocation(arcpy,image,dest)
            self.assertEqual(image.read_bytes(),b'fixture')
            arcpy.management.Delete.assert_not_called()

    def test_raw_national_plane_provisioned(self):
        """A large sparse grid's small final compressed size is not its native save budget."""
        with TemporaryDirectory() as d, patch.object(N,"disk_gate") as gate:
            N.single_space(d,d)
            gate.assert_called_once_with(d, N.RESERVE+86195*12863*8+2**30+512*2**20+2*2**30)


if __name__=='__main__':
    unittest.main()
