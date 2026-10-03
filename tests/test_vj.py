import copy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
import json
from pathlib import Path
import tempfile

import numpy as np

from core.settings import DEFAULT, Settings
from core.remote import RemoteServer
from core.vj_engine import RealtimeMusicFeatures, VJ_LED_STYLES, led_frame, validate_vj_config, native_led_pixels, vj_colors, vj_led_layout, vj_led_routes
from core.multi_launchpad import LINK_EXTEND, LINK_MIRROR, LINK_INDEPENDENT
from app import LaunchpadStudio


class VJTests(unittest.TestCase):
    def test_existing_mapped_profiles_migrate_to_explicit_pad_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"settings.json"
            path.write_text(json.dumps({"vj":{"map_launchpad":True},"multi_launchpad":{"devices":[{"id":"x"},{"id":"mk2"}]}}),encoding="utf-8")
            cfg=Settings(path).data["vj"]
            self.assertEqual(cfg["launchpads"],["x","mk2"]);validate_vj_config(cfg)

    def test_config_resolution_aspect_and_targets(self):
        cfg=copy.deepcopy(DEFAULT["vj"])
        self.assertEqual(validate_vj_config(cfg)["fps"],30)
        for override in ({"width":7681},{"height":500},{"fps":120},{"threshold":float("nan")},
                         {"preview":False,"screens":[]},{"screens":[1]},{"screens":["A","A"]},{"alpha":"false"},{"palette":"unknown"},
                         {"map_launchpad":True},{"launchpads":[1]},{"launchpads":["lp1","lp1"]},{"led_style":"unknown"},{"led_contrast":6}):
            with self.subTest(override=override),self.assertRaises(ValueError):validate_vj_config({**cfg,**override})
        result=validate_vj_config({**cfg,"width":3840,"height":1080,"aspect":"32:9","preview":False,"screens":["A","B"]})
        self.assertEqual(result["screens"],["A","B"])
        led_only=validate_vj_config({**cfg,"map_launchpad":True,"launchpads":["lp1"],"preview":False,"screens":[]})
        self.assertEqual((led_only["width"],led_only["height"]),(1920,1080))
        with self.assertRaises(ValueError):validate_vj_config({**led_only,"led_style":"原画采样"})

    def test_native_led_effects_have_black_space_bright_pixels_and_motion(self):
        cfg={**DEFAULT["vj"],"output_size":(16,8)}
        features={"energy":.8,"beat":.9,"beats":8,"bands":np.linspace(.2,.9,32),"mood":"热烈"}
        for style in VJ_LED_STYLES[1:-1]:
            with self.subTest(style=style):
                cfg["led_style"]=style
                a,_=native_led_pixels(cfg,features,1.3,0)
                b,_=native_led_pixels(cfg,{**features,"beats":9,"beat":.5},2.1,0)
                self.assertEqual(a.shape,(8,16,3));self.assertEqual(a.dtype,np.uint8)
                self.assertGreater(a.max(),150);self.assertGreater(np.count_nonzero(np.max(a,axis=2)==0),8)
                self.assertFalse(np.array_equal(a,b))
        before,_=native_led_pixels(cfg,features,1.3,0)
        after,_=native_led_pixels({**cfg,"width":3840,"height":2160,"aspect":"16:9","speed":3,"detail":2},features,1.3,0)
        np.testing.assert_array_equal(before,after)
        self.assertEqual(vj_colors(cfg,features),vj_colors({**cfg,"led_style":"扫描激光"},features))

    def test_selected_pad_geometry_does_not_change_screen_resolution(self):
        items=[{"id":"a","x":-1,"y":0},{"id":"b","x":0,"y":0},{"id":"c","x":0,"y":1}]
        self.assertEqual(vj_led_layout(items,["a"],LINK_EXTEND)[0],(8,8))
        self.assertEqual(vj_led_layout(items,["a","b"],LINK_EXTEND)[0],(16,8))
        self.assertEqual(vj_led_layout(items,["b","c"],LINK_INDEPENDENT)[0],(8,16))
        self.assertEqual(vj_led_layout(items,["a","b"],LINK_MIRROR)[0],(8,8))
        pads={key:tuple((x,y) for y in range(1,9) for x in range(8)) for key in ("a","b","c")}
        image=np.zeros((16,8,3),dtype='u1');image[:8]=(250,0,0);image[8:]=(0,0,250)
        routed=vj_led_routes(led_frame(image),items,pads,["b","c"],LINK_INDEPENDENT)
        self.assertEqual(set(routed),{"b","c"});self.assertEqual(routed["b"][(0,1)],(250,0,0));self.assertEqual(routed["c"][(0,1)],(0,0,250))

    def test_other_modes_never_overwrite_selected_vj_pads(self):
        studio=LaunchpadStudio.__new__(LaunchpadStudio)
        pads=tuple((x,y) for y in range(9) for x in range(9) if (x,y)!=(8,0))
        a=SimpleNamespace(pads=pads,connected=True,set_frame=Mock());b=SimpleNamespace(pads=pads,connected=True,set_frame=Mock())
        studio.lp=a;studio.launchpads={"a":a,"b":b};studio.mode_frames={};studio.mode="实时 VJ";studio.active_mode="实时 VJ";studio.active_modes={"实时 VJ","性能监控"}
        studio.multi_cfg={"enabled":True,"link_mode":LINK_EXTEND};studio.settings_store=SimpleNamespace(data={"vj":{**DEFAULT["vj"],"map_launchpad":True,"launchpads":["a"]}})
        studio._layout_configs=Mock(return_value=[{"id":"a","x":0,"y":0},{"id":"b","x":1,"y":0}]);studio._sync_canvas_preview=Mock()
        studio.apply_frame(led_frame(np.full((8,8,3),(0,250,0),dtype='u1')),"实时 VJ")
        a.set_frame.assert_called_once();b.set_frame.assert_not_called()
        studio.apply_frame(led_frame(np.full((8,16,3),(0,0,250),dtype='u1')),"性能监控")
        self.assertEqual(a.set_frame.call_count,1);self.assertEqual(b.set_frame.call_args.args[0][(0,1)],(0,0,250))

    def test_explicit_led_mode_change_preserves_existing_projection(self):
        studio=LaunchpadStudio.__new__(LaunchpadStudio)
        studio.multi_cfg={"enabled":False};studio.active_modes=set();studio.score_effect_token=0
        studio.vj=SimpleNamespace(state={"running":True},config={"preview":True,"screens":[],"map_launchpad":True},update=Mock())
        studio.settings_store=SimpleNamespace(data={"vj":{"map_launchpad":True}},save=Mock());studio._stop_all=Mock()
        studio._activate_mode("性能监控")
        studio._stop_all.assert_called_once_with(False,keep_vj=True)
        self.assertFalse(studio.settings_store.data["vj"]["map_launchpad"])
        self.assertFalse(studio.vj.update.call_args.args[0]["map_launchpad"])

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


class RemoteAssetTests(unittest.IsolatedAsyncioTestCase):
    async def test_small_ui_assets_do_not_use_native_sendfile(self):
        server=RemoteServer.__new__(RemoteServer);server.web_root=Path(__file__).resolve().parents[1]/"remote"
        index=await server._index(None)
        self.assertEqual(index.content_type,"text/html");self.assertIn(b'vj-launchpads',index.body)
        for name,mime in (("app.js","application/javascript"),("style.css","text/css")):
            response=await server._asset(SimpleNamespace(path='/'+name))
            self.assertEqual(response.content_type,mime);self.assertEqual(response.body,(server.web_root/name).read_bytes())
