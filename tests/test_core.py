import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from core.launchpad import MODELS, LaunchpadDevice, detect_model
from core.miniapps import SnakeGame, WhackAMole, calendar_frame, clock_frame, weather_frame
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


if __name__=="__main__":unittest.main()
