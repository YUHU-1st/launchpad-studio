import copy
import unittest

import numpy as np

from core.settings import DEFAULT
from core.vj_engine import RealtimeMusicFeatures, led_frame, validate_vj_config


class VJTests(unittest.TestCase):
    def test_config_resolution_aspect_and_targets(self):
        cfg=copy.deepcopy(DEFAULT["vj"])
        self.assertEqual(validate_vj_config(cfg)["fps"],30)
        for override in ({"width":7681},{"height":500},{"fps":120},{"threshold":float("nan")},
                         {"preview":False,"screens":[]},{"screens":[1]},{"screens":["A","A"]},{"alpha":"false"},{"palette":"unknown"}):
            with self.subTest(override=override),self.assertRaises(ValueError):validate_vj_config({**cfg,**override})
        result=validate_vj_config({**cfg,"width":3840,"height":1080,"aspect":"32:9","preview":False,"screens":["A","B"]})
        self.assertEqual(result["screens"],["A","B"])

    def test_streaming_tempo_locks_to_synthetic_120_bpm(self):
        analysis=RealtimeMusicFeatures();sr=48000
        for start in range(0,sr*10,1024):
            t=np.arange(start,start+1024)/sr
            envelope=np.exp(-np.mod(t,.5)*30)
            analysis.feed((.5*envelope*np.sin(2*np.pi*90*t)).astype("f4"),sr)
        result=analysis.snapshot()
        self.assertAlmostEqual(result["bpm"],120,delta=5)
        self.assertGreater(result["confidence"],.6)
        self.assertGreater(result["beats"],15)
        self.assertGreater(result["energy"],0)
        self.assertEqual(len(result["bands"]),32)

    def test_silence_is_not_given_a_fictitious_tempo(self):
        analysis=RealtimeMusicFeatures()
        for _ in range(180):analysis.feed(np.zeros(1024),48000)
        result=analysis.snapshot()
        self.assertEqual(result["bpm"],0);self.assertEqual(result["energy"],0)
        self.assertEqual(result["mood"],"安静")

    def test_led_mapping_preserves_native_extended_dimensions(self):
        image=np.zeros((16,24,3),dtype="u1");image[0,0]=(255,100,10);image[-1,-1]=(10,20,250)
        frame=led_frame(image,.5)
        self.assertEqual(frame[(0,1)],(127,50,5))
        self.assertEqual(frame[(23,16)],(5,10,125))
        self.assertEqual(frame[(23,0)],(0,0,0))
        self.assertEqual(frame[(24,16)],(5,10,125))
        self.assertEqual(len(frame),24*16+24+16)
