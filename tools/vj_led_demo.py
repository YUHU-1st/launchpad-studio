"""Native LED + GPU-screen preview; explicitly simulated music, not hardware footage."""
from pathlib import Path
import sys

import cv2
import moderngl
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.settings import DEFAULT
from core.vj_engine import VJ_LED_STYLES, native_led_pixels, vj_colors
from core.vj_shaders import FRAGMENT, VERTEX


def main():
    root=Path(__file__).resolve().parents[1];dest=root/"docs/media"
    ctx=moderngl.create_standalone_context(require=330);program=ctx.program(vertex_shader=VERTEX,fragment_shader=FRAGMENT)
    vao=ctx.vertex_array(program,[]);texture=ctx.texture((640,360),4);buffer=ctx.framebuffer([texture]);buffer.use()
    font=ImageFont.truetype("C:/Windows/Fonts/msyh.ttc",22)
    collage=Image.new("RGB",(1536,1040),(11,13,18))
    raw=root/"build/vj-led-demo-raw.mp4";raw.parent.mkdir(exist_ok=True)
    video=cv2.VideoWriter(str(raw),cv2.VideoWriter_fourcc(*"mp4v"),24,(1280,720))
    cfg={**DEFAULT["vj"],"output_size":(16,8),"palette":"霓虹"}
    for index,name in enumerate(VJ_LED_STYLES[1:-1]):
        cfg["led_style"]=name
        for tick in range(72):
            t=index*3+tick/24;beat=float(np.exp(-np.mod(t,.5)*7))
            features={"energy":.7+.15*np.sin(t),"bass":.4,"treble":.25,"beat":beat,"beats":int(t*2),
                      "bands":.2+.7*np.sin(np.arange(32)*.23+t*2)**2,"mood":"热烈"}
            pixels,_=native_led_pixels(cfg,features,t,index%8)
            low,high=vj_colors(cfg,features)
            uniforms={"resolution":(640,360),"clock":t+15,"energy":features["energy"],"bass":.4,"treble":.25,"beat":beat,
                      "speed":1.,"intensity":1.,"detail":1.,"transition":1.,"scene":index%8,"previous":index%8,"alpha":0,
                      "lowColor":tuple(v/255 for v in low),"highColor":tuple(v/255 for v in high)}
            for key,value in uniforms.items():program[key].value=value
            program["bands"].write(features["bands"].astype("f4").tobytes());vao.render(vertices=3)
            rgb=np.frombuffer(buffer.read(components=3,alignment=1),dtype='u1').reshape(360,640,3)[::-1].copy()
            frame=Image.new("RGB",(1280,720),(11,13,18));frame.paste(Image.fromarray(rgb),(12,120));draw=ImageDraw.Draw(frame)
            draw.text((20,24),f"2.3 · {name} / Native LED · independent screen & pad visuals",font=font,fill=(245,248,255))
            draw.text((20,77),"GPU screen · 640×360",font=font,fill=(160,174,200))
            draw.text((704,77),"Native pads · 16×8 · LP #1 + LP #2",font=font,fill=(160,174,200))
            for y in range(8):
                for x in range(16):
                    a,b=704+x*34,165+y*34;draw.rounded_rectangle((a,b,a+29,b+29),radius=3,fill=tuple(pixels[y,x]))
            draw.line((974,148,974,454),fill=(100,112,137),width=2)
            draw.text((20,538),"共享配色、节拍与情绪 · 灯板独立图形 / Shared palette, beat & mood",font=font,fill=(235,240,255))
            draw.text((20,580),"SIMULATED 120 BPM · production renderers · not physical-device footage",font=font,fill=(160,174,200))
            video.write(cv2.cvtColor(np.asarray(frame),cv2.COLOR_RGB2BGR))
            if tick==36:
                tile=Image.new("RGB",(512,260),(11,13,18));d=ImageDraw.Draw(tile);d.text((12,7),name,font=font,fill=(235,240,255))
                tile.paste(Image.fromarray(pixels).resize((480,208),Image.Resampling.NEAREST),(16,45))
                collage.paste(tile,((index%3)*512,(index//3)*260))
    video.release();collage.save(dest/"vj-led-styles.png",optimize=True)
    print("Rendered twelve native LED styles with a synchronized, independently rendered GPU screen. Simulated music.")


if __name__=="__main__":main()
