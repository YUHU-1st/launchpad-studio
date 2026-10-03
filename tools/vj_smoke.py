"""Real GPU + real audio output-process checks. Run from the repository root."""
import copy
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.audio_engine import audio_devices
from core.settings import DEFAULT
from core.vj_engine import VJController, VJ_STYLES, VJ_LED_STYLES, display_targets


def main():
    cfg=copy.deepcopy(DEFAULT["vj"])
    devices=audio_devices()
    cfg.update(device=devices[0][0],width=640,height=360,output_size=(16,8),map_launchpad=True,launchpads=["test-a","test-b"],
               log_path=str(Path("data/vj-smoke.log").resolve()))
    controller=VJController();frames=0;seen=set();sizes=set()
    def wait(seconds,expected=None):
        nonlocal frames
        end=time.monotonic()+seconds
        matched=expected is None
        while time.monotonic()<end:
            for message in controller.poll():
                if "error" in message:raise RuntimeError(message["error"])
                if "pixels" in message:frames+=1;sizes.add(message["pixels"].shape)
            if not controller.state.get("running"):raise RuntimeError("VJ output stopped prematurely")
            if controller.state.get("scene"):seen.add(controller.state["scene"])
            if expected and all(controller.state.get(key)==value for key,value in expected.items()):matched=True
            time.sleep(.03)
        assert matched,(expected,controller.state)
    try:
        controller.start(cfg);wait(3)
        for style in VJ_STYLES[1:]:
            cfg["style"]=style;controller.update(cfg);wait(1.8)
        for style in VJ_LED_STYLES[1:-1]:
            cfg["led_style"]=style;controller.update(cfg);wait(.4)
        cfg["led_style"]="原画采样";controller.update(cfg);wait(1)
        cfg.update(alpha=True,screens=[display_targets()[0]["id"]],width=1280,height=720,output_size=(8,16),fps=60)
        controller.update(cfg);wait(4,{"width":1280,"height":720,"windows":["preview",display_targets()[0]["id"]]})
        cfg.update(alpha=False,screens=[],device=devices[1][0]);controller.update(cfg);wait(6,{"windows":["preview"]})
        cfg.update(led_style="扫描激光",preview=False,screens=[],output_size=(8,8))
        controller.update(cfg);wait(2,{"windows":[],"led_width":8,"led_height":8})
        assert len(seen)==8,(seen,controller.state)
        assert sizes=={(8,16,3),(16,8,3),(8,8,3)},sizes
        assert frames>100,frames
        print({"styles":len(seen),"LED_frames":frames,"sizes":list(sizes),"state":controller.state})
    finally:controller.stop()
    assert controller.process is None,"VJ process did not shut down"
    Path("data/vj-smoke-result.txt").write_text(f"PASS: 8 styles; {frames} LED frames; alpha/fullscreen/reconfigure/stop\n",encoding="utf-8")


if __name__=="__main__":main()
