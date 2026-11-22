import unittest
import numpy as np
from app.visual_role_features import visual_features, BODY_SIZE, CONTEXT_SIZE

class VisualRoleTests(unittest.TestCase):
    def test_dimensions_and_finite(self):
        v=visual_features(np.zeros((80,100,3),np.uint8),(.2,.2,.6,.8))
        self.assertEqual([len(x) for x in v],[24,BODY_SIZE,CONTEXT_SIZE])
        self.assertTrue(all(np.isfinite(x).all() for x in v))

    def test_target_removed_from_context(self):
        a=np.full((100,100,3),80,np.uint8);b=a.copy();b[30:70,30:70]=200
        va=visual_features(a,(.3,.3,.7,.7));vb=visual_features(b,(.3,.3,.7,.7))
        np.testing.assert_array_equal(va[2],vb[2])
        self.assertFalse(np.array_equal(va[1],vb[1]))

    def test_surrounding_changes_do_not_change_body(self):
        a=np.zeros((100,100,3),np.uint8);b=a.copy();b[:25]=255
        va=visual_features(a,(.3,.3,.7,.7));vb=visual_features(b,(.3,.3,.7,.7))
        np.testing.assert_array_equal(va[1],vb[1])
        self.assertFalse(np.array_equal(va[2],vb[2]))

    def test_spatial_order_is_retained(self):
        rng=np.random.default_rng(1);a=rng.integers(0,255,(64,32,3),dtype=np.uint8)
        b=a[::-1].copy()
        self.assertFalse(np.array_equal(visual_features(a,(0,0,1,1))[1],visual_features(b,(0,0,1,1))[1]))

    def test_clipping_and_bad_boxes(self):
        a=np.zeros((32,32,3),np.uint8)
        self.assertTrue(np.isfinite(visual_features(a,(-1,-1,2,2))[1]).all())
        for box in [(0,0,0,1),(1,1,0,0),(0,0,float('nan'),1)]:
            with self.assertRaises(ValueError):visual_features(a,box)

if __name__=='__main__':unittest.main()
