"""Authenticated integration checks against the isolated desktop test instance."""
import asyncio
import json
from pathlib import Path
import sys

import aiohttp


async def main():
    root=Path(__file__).resolve().parents[1]
    profile=Path(sys.argv[1]) if len(sys.argv)>1 else root/"build/vj-ui-test"
    cfg=json.loads((profile/"data/settings.json").read_text(encoding="utf-8"))
    async with aiohttp.ClientSession(headers={"X-Launchpad-Token":cfg["remote"]["pin"]}) as http:
        async with http.ws_connect(f"http://127.0.0.2:{cfg['remote']['port']}/ws") as ws:
            async def command(action,value=None):
                await ws.send_json({"type":"command","action":action,"value":value})
            async def until(predicate,timeout=12):
                end=asyncio.get_running_loop().time()+timeout
                while asyncio.get_running_loop().time()<end:
                    message=await ws.receive_json(timeout=timeout)
                    state=message.get("state")
                    if state and "vj" in state and predicate(state):return state
                raise TimeoutError("Expected VJ state was not reached")
            await command("vj.refresh")
            state=await until(lambda s:bool(s["vj"]["devices"]))
            selected=[pad["id"] for pad in state["vj"]["launchpads"]]
            if not selected:raise RuntimeError("Connect Launchpads or launch the explicit --virtual-pads fixture")
            await command("vj.config",{"device":state["vj"]["devices"][0]["name"],"width":1280,"height":720,
                "aspect":"16:9","map_launchpad":False,"alpha":False,"screens":[],"preview":True})
            await command("performance.start");await command("vj.start")
            state=await until(lambda s:s["vj"]["state"].get("fps",0)>10 and s["active_mode"]=="性能监控")
            print("VJ independently runs alongside performance monitoring")
            await command("vj.config",{"map_launchpad":True,"launchpads":[selected[0]],"style":"几何万花筒","led_style":"扫描激光"})
            state=await until(lambda s:s["active_mode"]=="实时 VJ" and s["vj"]["state"].get("scene")=="几何万花筒")
            await command("mode.show","布局设置")
            state=await until(lambda s:s["mode"]=="布局设置")
            assert state["vj"]["state"]["running"] and state["active_mode"]=="实时 VJ"
            if state["launchpad"]["connected"]:
                assert any(c!="000000" for d in state["launchpad"]["devices"] for c in d["led_grid"] if c),"Physical LED frame stayed black"
                print("Launchpad output colors are nonzero (simulation="+str(state.get("test_virtual_pads",False))+")")
            assert state["vj"]["led_size"]==[8,8] and state["vj"]["config"]["width"]==1280
            assert "性能监控" in state["active_modes"],state["active_modes"]
            if len(selected)>1:
                await command("vj.config",{"launchpads":selected})
                await until(lambda s:s["vj"]["state"].get("led_width")==16)
                await command("vj.config",{"launchpads":[selected[-1]],"preview":False,"screens":[]})
                state=await until(lambda s:s["vj"]["state"].get("windows")==[] and s["vj"]["state"].get("led_width")==8)
                assert state["vj"]["config"]["width"]==1280
                print("Selected-pad resizing, preservation of other modes, independent screen size and LED-only output passed")
                await command("vj.config",{"preview":True})
            await command("performance.start")
            state=await until(lambda s:s["active_mode"]=="性能监控" and not s["vj"]["config"]["map_launchpad"] and s["vj"]["state"].get("running"))
            print("Starting another LED mode preserves the independently projected VJ screen")
            await command("vj.config",{"map_launchpad":True,"launchpads":selected});await until(lambda s:s["vj"]["state"].get("fps",0)>10)
            await command("app.blackout")
            state=await until(lambda s:not s["active_mode"] and not s["vj"]["state"].get("running"))
            print("Mode-page switching, explicit mode start, blackout and VJ stop passed")


if __name__=="__main__":asyncio.run(main())
