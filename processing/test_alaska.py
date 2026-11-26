"""Small tests for the Alaska-specific numerical contract (no ArcGIS required)."""
import unittest

import numpy as np

import alaska as ak


def pixel(row, col):
    """Encode a known test grid row and column for round-trip assertions."""
    return (row-ak.ROW_OFFSET)*ak.GLOBAL_COLS+col


class AlaskaScience(unittest.TestCase):
    def test_signed_ids_round_trip_both_domains(self):
        rows = np.array([4450, 9321, 8900])
        cols = np.array([178, 86372, 2500])
        ids = pixel(rows, cols)
        self.assertTrue((ids < 0).all())
        rr, cc = ak.coordinates(ids)
        np.testing.assert_array_equal(rr, rows)
        np.testing.assert_array_equal(cc, cols)
        with self.assertRaises(ValueError):
            ak.coordinates([pixel(4450, 177)])

    def test_partition_uses_whole_blocks(self):
        self.assertEqual(ak._side("016", 171, 179.9), "E")
        self.assertEqual(ak._side("016", -179.9, -170), "W")
        self.assertEqual(ak._side("290", -160, -150), "ALL")
        for county, extent in [("016", (-178, 173)), ("290", (177, 179)), ("016", (170, 184))]:
            with self.assertRaises(ValueError):
                ak._side(county, *extent)

    def test_count_eligibility_is_not_area_eligibility(self):
        a, b, c = (pixel(5000, i) for i in (300, 301, 302))
        table = np.array([[0, 0], [7, 1]], dtype="float64")
        plan = ak.weight_plan([a, b, a, c, c], [1, 0, 1, 1, 1],
                              [4, 2, 8, 0, 1], [1.5, 2, 1.0, 1, 0.0000049])
        np.testing.assert_array_equal(plan[0], [a, b])  # no eligible piece for c
        np.testing.assert_array_equal(ak.sum_counts(plan, table, 0, 2), [[3.5, 0.5], [0., 0.]])
        with self.assertRaises(ValueError):
            ak.weight_plan([a], [-1], [1], [1])

    def test_sum_uses_stable_order_not_sorted_values(self):
        a, b = pixel(5000, 300), pixel(5000, 301)
        ids, order, starts = ak.reduction_order([b, a, b, b, a])
        np.testing.assert_array_equal(ids, [a, b])
        np.testing.assert_array_equal(order, [1, 4, 0, 2, 3])
        np.testing.assert_array_equal(starts, [0, 2])
        np.testing.assert_array_equal(np.add.reduceat(np.array([4., 1., 7., 0., 3.])[order], starts), [4., 11.])

    def test_mask_hash_bits_share_a_byte_with_padding(self):
        bits = np.zeros((ak.HEIGHT, (ak.WIDTH+7)//8), dtype="uint8")
        ak._record_cells(bits, [pixel(ak.TOP, ak.LEFT+i) for i in (0, 1, 7, 8, 8)])
        self.assertEqual(bits[0, 0], 131)
        self.assertEqual(bits[0, 1], 1)
        self.assertEqual(bits[0, -1], 0)

    def test_rejects_wrong_reference_or_ambiguous_mode(self):
        with self.assertRaises(ValueError):
            ak._check_spatial_grid(ak.WIDTH, ak.HEIGHT, ak.XMIN+ak.CELL, ak.YMAX, ak.CELL, ak.CELL, 4326)
        with self.assertRaises(ValueError):
            ak.allocate_geography("02", None, None, None, None, None, None, fishnet_kind="paired_area_masks")


if __name__ == "__main__":
    unittest.main()
