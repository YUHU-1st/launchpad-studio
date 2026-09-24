import json
import tempfile
import unittest
import comtypes
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import numpy as np

from core.audio_engine import reactive_frame
from core.launchpad import MODELS, LaunchpadDevice, detect_model, is_launchpad_control_port, is_launchpad_port
from core.macros import tap_hotkey
from core.miniapps import SnakeGame, WhackAMole, calendar_frame, clock_frame, weather_frame
from core.multi_launchpad import LINK_EXTEND, LINK_INDEPENDENT, canvas_geometry, normalize_configs, number_frame, route_frames
from core.rhythm import RhythmGame, chart_from_analysis
from core.settings import Settings
from core.video_engine import VideoPlayer
from core.windows_media import SystemMediaBridge, parse_lrc


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

    def test_windows_abbreviated_port_names_are_detected(self):
        self.assertTrue(is_launchpad_port("LPX MIDI"))
        self.assertTrue(is_launchpad_port("MIDIIN2 (LPMiniMK3 MIDI)"))
        self.assertTrue(is_launchpad_control_port("LPX MIDI"))
        self.assertFalse(is_launchpad_control_port("MIDIIN2 (LPX MIDI)"))
        self.assertFalse(is_launchpad_control_port("Launchpad Pro MK3 DAW"))
        self.assertEqual(detect_model("LPX MIDI").key,"x")
        self.assertEqual(detect_model("LPMiniMK3 MIDI").key,"mini_mk3")
        self.assertEqual(detect_model("LPProMK3 MIDI").key,"pro_mk3")

    def test_protocol_output(self):
        device=LaunchpadDevice(); device.out=FakeMidiOut(); device.connected=True
        device.set_model("x"); device.set_frame({(0,8):(255,128,0)},force=True)
        self.assertEqual(device.out.sysex_messages[-1][:7],bytes([240,0,32,41,2,12,3]))
        device.set_model("s"); device.set_frame({(0,8):(20,80,220)},force=True)
        self.assertTrue(device.out.short_messages)


class MultiLaunchpadTests(unittest.TestCase):
    def setUp(self):
        self.pads=tuple((x,y) for y in range(9) for x in range(9) if not (y==0 and x==8))
        self.frame={(x,y+1):(x*20,y*20,10) for y in range(8) for x in range(16)}
        self.frame.update({(x,0):(1,2,3) for x in range(16)})

    def test_relative_layout_normalizes_negative_coordinates(self):
        width,height,positions=canvas_geometry([
            {"id":"left","x":-1,"y":2},{"id":"right","x":1,"y":3},
        ])
        self.assertEqual((width,height),(3,2))
        self.assertEqual(positions,{"left":(0,0),"right":(2,1)})

    def test_extended_canvas_splits_across_devices(self):
        self.frame[(0,0)]=(9,8,7); self.frame[(8,0)]=(6,5,4); self.frame[(16,1)]=(3,2,1)
        configs=[{"id":"a","x":0,"y":0},{"id":"b","x":1,"y":0}]
        routed=route_frames(configs,{"a":self.pads,"b":self.pads},{"视频播放":self.frame},LINK_EXTEND,"视频播放")
        self.assertEqual(routed["a"][(0,1)],self.frame[(0,1)])
        self.assertEqual(routed["b"][(0,1)],self.frame[(8,1)])
        self.assertEqual(routed["b"][(7,8)],self.frame[(15,8)])
        self.assertEqual(routed["a"][(0,0)],(9,8,7))
        self.assertEqual(routed["b"][(0,0)],(6,5,4))
        self.assertEqual(routed["a"][(8,1)],(3,2,1))

    def test_independent_sources_do_not_cross_devices(self):
        red={(x,y):(255,0,0) for x,y in self.pads}
        blue={(x,y):(0,0,255) for x,y in self.pads}
        configs=[{"id":"a","mode":"性能监控"},{"id":"b","mode":"音乐演示"}]
        routed=route_frames(configs,{"a":self.pads,"b":self.pads},{"性能监控":red,"音乐演示":blue},LINK_INDEPENDENT,"音乐演示")
        self.assertEqual(routed["a"][(3,4)],(255,0,0))
        self.assertEqual(routed["b"][(3,4)],(0,0,255))

    def test_number_identifier_is_visible_and_distinct(self):
        one=number_frame(1); twelve=number_frame(12)
        self.assertNotEqual(one,twelve)
        self.assertGreater(sum(color==(0,210,255) for color in twelve.values()),8)

    def test_audio_and_video_render_native_wide_canvas(self):
        samples=np.sin(np.linspace(0,40*np.pi,4096)).astype(np.float32)
        audio=reactive_frame(samples,44100,"频谱",output_size=(16,8))
        self.assertIn((15,8),audio)
        self.assertIn((16,8),audio)
        image=np.zeros((90,160,3),dtype=np.uint8); image[:,:,1]=180
        video=VideoPlayer(lambda _frame:None)._filter(image,"原色视频",{},(16,8))
        self.assertEqual(video.shape,(8,16,3))

    def test_mobile_multi_device_config_is_normalized_and_validated(self):
        raw=[{"id":"lp1","number":1,"x":-1,"y":0,"mode":"音乐演示","model":"x","input_index":0,"output_index":1},
             {"id":"lp2","number":2,"x":0,"y":0,"mode":"性能监控","model":"mk2","input_index":1,"output_index":2}]
        configs=normalize_configs(raw,["LPX MIDI","Launchpad MK2"],["Synth","LPX MIDI","Launchpad MK2"],{"auto","x","mk2"},LINK_EXTEND)
        self.assertEqual(configs[0]["input"],"LPX MIDI")
        self.assertEqual(configs[1]["output"],"Launchpad MK2")
        duplicate=[dict(raw[0]),dict(raw[1],input_index=0)]
        with self.assertRaisesRegex(ValueError,"端口重复"):
            normalize_configs(duplicate,["LPX MIDI","Launchpad MK2"],["Synth","LPX MIDI","Launchpad MK2"],{"auto","x","mk2"},LINK_EXTEND)
        overlap=[dict(raw[0],x=0),dict(raw[1],x=0)]
        with self.assertRaisesRegex(ValueError,"位置重叠"):
            normalize_configs(overlap,["LPX MIDI","Launchpad MK2"],["Synth","LPX MIDI","Launchpad MK2"],{"auto","x","mk2"},LINK_EXTEND)


class SettingsTests(unittest.TestCase):
    def test_migration_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"settings.json"
            path.write_text(json.dumps({"detail_params":{"music":{"threshold":.08}}}),encoding="utf-8")
            settings=Settings(path)
            self.assertEqual(settings.data["detail_params"]["music"]["threshold"],.08)
            self.assertIn("freq_min",settings.data["detail_params"]["music"])
            settings.save(); self.assertEqual(Settings(path).data["detail_params"]["music"]["threshold"],.08)
            self.assertEqual(Settings(path).data["remote"]["port"],8765)
            self.assertEqual(Settings(path).data["multi_launchpad"]["link_mode"],"扩展画布")


class RemoteMediaTests(unittest.TestCase):
    def test_lrc_parser_orders_fractional_timestamps(self):
        lines=parse_lrc("[00:12.50]第二句\n[00:01.250]第一句\n[01:02]第三句")
        self.assertEqual([item["text"] for item in lines],["第一句","第二句","第三句"])
        self.assertEqual(lines[0]["time"],1.25)

    def test_lrc_parser_expands_multiple_timestamps(self):
        lines=parse_lrc("[00:01.50][00:03.250]Hello\n[01:02]World")
        self.assertEqual([item["time"] for item in lines],[1.5,3.25,62.0])
        self.assertEqual([item["text"] for item in lines],["Hello","Hello","World"])


class RemoteMediaCommandTests(unittest.IsolatedAsyncioTestCase):
    def test_media_thread_initializes_com_as_mta(self):
        with patch("core.windows_media.WindowsAudioSystem.snapshot",return_value={}):bridge=SystemMediaBridge()
        def close_coroutine(coroutine):
            coroutine.close()
        with patch("comtypes.CoInitializeEx") as initialize, patch("comtypes.CoUninitialize") as uninitialize, \
             patch("core.windows_media.asyncio.run",side_effect=close_coroutine):
            bridge._thread_main()
        initialize.assert_called_once_with(comtypes.COINIT_MULTITHREADED)
        uninitialize.assert_called_once_with()

    def test_media_key_mapping_uses_extended_key_events(self):
        with patch("core.macros.user32.keybd_event") as key_event:
            tap_hotkey("MEDIA_PLAY_PAUSE")
        self.assertEqual(
            [call.args for call in key_event.call_args_list],
            [(0xB3,0,0x0001,0),(0xB3,0,0x0003,0)],
        )

    async def test_none_winrt_result_is_accepted_without_toggle_fallback(self):
        methods={
            "play":"try_play_async",
            "pause":"try_pause_async",
            "play_pause":"try_toggle_play_pause_async",
        }
        for action,method in methods.items():
            with self.subTest(action=action):
                session=SimpleNamespace(**{method:AsyncMock(return_value=None)})
                self.assertTrue(await SystemMediaBridge._media_command(session,action,None))

        session=SimpleNamespace(try_play_async=AsyncMock(return_value=None))
        with patch("core.windows_media.WindowsAudioSystem.snapshot",return_value={}):bridge=SystemMediaBridge()
        bridge.command("play")
        with patch("core.windows_media.tap_hotkey") as tap:
            await bridge._drain_commands(session)
        tap.assert_not_called()

    async def test_explicit_false_uses_safe_fallback_for_paused_session(self):
        session=SimpleNamespace(
            try_play_async=AsyncMock(return_value=False),
            get_playback_info=lambda:SimpleNamespace(playback_status=5),
        )
        with patch("core.windows_media.WindowsAudioSystem.snapshot",return_value={}):bridge=SystemMediaBridge()
        bridge.command("play")
        with patch("core.windows_media.tap_hotkey") as tap, self.assertLogs("core.windows_media",level="INFO") as logs:
            await bridge._drain_commands(session)
        tap.assert_called_once_with("MEDIA_PLAY_PAUSE")
        self.assertTrue(any("fallback_sent=True" in line for line in logs.output))

    async def test_explicit_fallback_never_toggles_away_from_target_state(self):
        playing=SimpleNamespace(get_playback_info=lambda:SimpleNamespace(playback_status=4))
        paused=SimpleNamespace(get_playback_info=lambda:SimpleNamespace(playback_status=5))
        with patch("core.windows_media.tap_hotkey") as tap:
            self.assertFalse(SystemMediaBridge._fallback_media_key("play",playing))
            self.assertFalse(SystemMediaBridge._fallback_media_key("pause",paused))
        tap.assert_not_called()

    async def test_seek_forwards_ticks_without_creating_timeline_state(self):
        session=SimpleNamespace(try_change_playback_position_async=AsyncMock(return_value=True))
        self.assertTrue(await SystemMediaBridge._media_command(session,"seek",12.345))
        session.try_change_playback_position_async.assert_awaited_once_with(123450000)


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
