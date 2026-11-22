import sys
from pathlib import Path
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from evaluate_frozen_visual import frozen_crop

class FrozenCropTests(unittest.TestCase):
    def test_whole_person_kept_and_colour_correct(self):
        image=np.zeros((20,10,3),np.uint8);image[:,:,2]=255
        square=np.asarray(frozen_crop(image,(0,0,1,1),lambda x:x))
        self.assertEqual(square.shape[0],square.shape[1])
        self.assertEqual(int(((square[:,:,0]==255)&(square[:,:,2]==0)).sum()),200)
        self.assertGreater(square.shape[0],20*8/7)
    def test_invalid_box_rejected(self):
        for box in [(0,0,0,1),(0,0,float('nan'),1)]:
            with self.assertRaises(ValueError):frozen_crop(np.zeros((10,10,3),np.uint8),box,lambda x:x)
if __name__=='__main__':unittest.main()
