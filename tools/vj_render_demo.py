"""Render original GPU shader previews using simulated, labeled music features."""
from pathlib import Path
import sys

import cv2
import moderngl
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.vj_engine import VJ_STYLES
from core.vj_shaders import FRAGMENT, VERTEX


def main():
    dest=Path(__file__).resolve().parents[1]/"docs"/"media";dest.mkdir(parents=True,exist_ok=True)
    ctx=moderngl.create_standalone_context(require=330);program=ctx.program(vertex_shader=VERTEX,fragment_shader=FRAGMENT)
    vao=ctx.vertex_array(program,[]);texture=ctx.texture((960,540),4);buffer=ctx.framebuffer([texture]);buffer.use()
    font=ImageFont.truetype("C:/Windows/Fonts/msyh.ttc",20)
    collage=Image.new("RGB",(1280,1440),(11,13,18))
    video=cv2.VideoWriter(str(dest/"vj-demo.mp4"),cv2.VideoWriter_fourcc(*"mp4v"),30,(960,540))
    previews=[]
    for scene,name in enumerate(VJ_STYLES[1:]):
        for tick in range(90):
            t=scene*3+tick/30.;beat=np.exp(-np.mod(t,.5)*7)
            uniforms={"resolution":(960,540),"clock":t+15,"energy":.7,"bass":.45,"treble":.22,"beat":float(beat),
                      "speed":1.,"intensity":1.,"detail":1.,"transition":1.,"scene":scene,"previous":scene,"alpha":0,
                      "lowColor":(0,.96,1.),"highColor":(1.,.12,.82)}
            for key,value in uniforms.items():program[key].value=value
            bands=(.3+.65*np.sin(np.arange(32)*.24+t)**2).astype("f4");program["bands"].write(bands.tobytes())
            vao.render(vertices=3)
            rgb=np.frombuffer(buffer.read(components=3,alignment=1),dtype="u1").reshape(540,960,3)[::-1].copy()
            assert np.mean(rgb)>2,f"Empty shader: {name}"
            frame=Image.fromarray(rgb);label=ImageDraw.Draw(frame)
            label.rectangle((0,0,960,43),fill=(11,13,18));label.text((16,8),f"{name} · GPU shader preview / simulated 120 BPM",font=font,fill=(235,240,255))
            video.write(cv2.cvtColor(np.asarray(frame),cv2.COLOR_RGB2BGR))
            if tick==45:
                x=scene%2*640;y=scene//2*360;collage.paste(frame.resize((640,360)),(x,y))
            if tick%6==0:previews.append(frame.resize((640,360)))
        program["alpha"].value=1;vao.render(vertices=3)
        rgba=np.frombuffer(buffer.read(components=4,alignment=1),dtype="u1").reshape(540,960,4)
        assert rgba[:,:,3].min()<245,f"No alpha: {name}"
        assert rgba[:,:,3].max()>20,f"Empty alpha: {name}"
        assert np.all(rgba[:,:,:3]<=rgba[:,:,3:4]),"Output is not premultiplied RGBA"
    video.release();collage.save(dest/"vj-styles.png",optimize=True)
    previews[0].save(dest/"vj-demo.gif",save_all=True,append_images=previews[1:],duration=200,loop=0)
    print("Rendered eight original styles; opaque/alpha GPU assertions passed.")


if __name__=="__main__":main()
