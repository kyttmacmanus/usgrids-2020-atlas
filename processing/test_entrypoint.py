"""Small public interface tests. No ArcGIS license, data downloads or external writes."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from usgrids import dispatch


class ScopeTests(unittest.TestCase):
    def test_routes(self):
        """The two valid scopes must call different implementations."""
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"config.json"
            for spec,target in (({"state":"10"},"run_geography.run"),({"kind":"national"},"national.run")):
                p.write_text(json.dumps(spec))
                with patch(target) as run:
                    dispatch(p,"check")
                    run.assert_called_once_with(p.resolve(),"check")

    def test_ambiguous_scope(self):
        """Reject combinations that could otherwise silently select the wrong method."""
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"config.json"
            for obj,stage in (({"kind":"national","state":"10"},"all"),({"kind":"national"},"counts"),({},"spatial")):
                p.write_text(json.dumps(obj))
                with self.assertRaises(ValueError): dispatch(p,stage)
