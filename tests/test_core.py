import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from core.launchpad import MODELS, LaunchpadDevice, detect_model
from core.miniapps import SnakeGame, WhackAMole, calendar_frame, clock_frame, weather_frame
from core.rhythm import RhythmGame, chart_from_analysis
from core.settings import Settings


class FakeMidiOut:
    def __init__(self):self.sysex_messages=[]; self.short_messages=[]
    def sysex(self,data):self.sysex_messages.append(data)
    def short(self,*data):self.short_messages.append(data)


class LaunchpadModelTests(unittest.TestCase):
    def test_addresses_are_unique_per_message_type(self):
        for model in MODELS:
            addresses=[]
            for xy in model.pads:
                status=0xB0 if model.address_kind=="legacy" and xy[1]==0 else 0x90
                addresses.append((status,model.address(*xy)))
            self.assertEqual(len(addresses),len(set(addresses)),model.name)

    def test_auto_detection_prefers_specific_models(self):
        self.assertEqual(detect_model("Launchpad Pro MK3 MIDI").key,"pro_mk3")
        self.assertEqual(detect_model("Launchpad Mini MK3").key,"mini_mk3")
        self.assertEqual(detect_model("Launchpad MK2").key,"mk2")

    def test_protocol_output(self):
        device=LaunchpadDevice(); device.out=FakeMidiOut(); device.connected=True
        device.set_model("x"); device.set_frame({(0,8):(255,128,0)},force=True)
        self.assertEqual(device.out.sysex_messages[-1][:7],bytes([240,0,32,41,2,12,3]))
        device.set_model("s"); device.set_frame({(0,8):(20,80,220)},force=True)
        self.assertTrue(device.out.short_messages)


class SettingsTests(unittest.TestCase):
    def test_migration_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"settings.json"
            path.write_text(json.dumps({"detail_params":{"music":{"threshold":.08}}}),encoding="utf-8")
            settings=Settings(path)
            self.assertEqual(settings.data["detail_params"]["music"]["threshold"],.08)
            self.assertIn("freq_min",settings.data["detail_params"]["music"])
            settings.save(); self.assertEqual(Settings(path).data["detail_params"]["music"]["threshold"],.08)


class MiniAppTests(unittest.TestCase):
    def test_frames_have_canonical_80_controls(self):
        now=datetime(2026,9,10,12,34,56)
        for frame in (clock_frame(now,4,(1,2,3),(4,5,6)),calendar_frame(now,2,(1,2,3),(4,5,6)),weather_frame(61,22)):
            self.assertEqual(len(frame),80)

    def test_games_respond(self):
        snake=SnakeGame(); snake.steer((0,-1)); self.assertTrue(snake.tick())
        mole=WhackAMole(); self.assertTrue(mole.hit(mole.target)); self.assertEqual(mole.score,1)

    def test_snake_wraps_at_every_edge(self):
        cases=(((7,4),(1,0),(0,4)),((0,4),(-1,0),(7,4)),((4,1),(0,-1),(4,8)),((4,8),(0,1),(4,1)))
        for start,direction,expected in cases:
            snake=SnakeGame(); snake.snake=[start]; snake.direction=direction; snake.next_direction=direction
            self.assertTrue(snake.tick()); self.assertEqual(snake.snake[0],expected)

    def test_mole_difficulty_controls_available_chances(self):
        mole=WhackAMole(); mole.reset(max_misses=8)
        for _ in range(7):mole.timeout()
        self.assertTrue(mole.running); self.assertEqual(mole.misses,7)
        mole.timeout(); self.assertFalse(mole.running)

    def test_top_control_labels_match_launchpad_icons(self):
        device=LaunchpadDevice()
        self.assertEqual([device.pad_label(x,0) for x in range(4)],["↑","↓","←","→"])

    def test_rhythm_chart_and_both_layouts(self):
        sr=8000; t=np.arange(sr*5)/sr; samples=(np.sin(2*np.pi*220*t)*.04).astype(np.float32)
        for second in range(1,5):samples[second*sr:second*sr+300]+=.8*np.hanning(300).astype(np.float32)
        analysis=SimpleNamespace(data=samples,sr=sr,duration=5.0,bpm=120)
        for style in ("瀑布音游","环形音游"):
            chart=chart_from_analysis(analysis,"test.wav",style,"普通",6)
            self.assertGreater(len(chart.notes),3)
            game=RhythmGame(); game.reset(chart,3,"普通")
            note=chart.notes[0]; result=game.hit(game.targets()[note.lane],note.time)
            self.assertEqual(result,"perfect"); self.assertEqual(len(game.frame(note.time)),80)


if __name__=="__main__":unittest.main()
