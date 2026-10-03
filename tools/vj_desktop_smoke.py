"""Isolated desktop UI/remote test instance; does not change personal settings."""
import multiprocessing
from types import SimpleNamespace
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from core.settings import Settings


if __name__=="__main__":
    multiprocessing.freeze_support()
    port=int(next((arg.split('=',1)[1] for arg in sys.argv if arg.startswith('--port=')),8767))
    app.ROOT=Path(__file__).resolve().parents[1]/"build"/("vj-ui-test" if port==8767 else f"vj-ui-test-{port}")
    settings=Settings(app.ROOT/"data"/"settings.json")
    settings.data["remote"]["port"]=port;settings.save()
    window=app.LaunchpadStudio()
    if "--virtual-pads" in sys.argv:
        # Explicit simulation for routing/UI tests when physical pads are absent.
        from core.launchpad import LaunchpadDevice
        window.lp.disconnect();window.launchpads={};items=[]
        for i,key in enumerate(("x","mk2")):
            device=LaunchpadDevice(model=key);device.connected=True
            device.out=SimpleNamespace(sysex=lambda _message:None,short=lambda *_args:None,close=lambda:None)
            device_id=f"virtual-{key}";window.launchpads[device_id]=device
            items.append({"id":device_id,"number":i+1,"x":i,"y":0,"mode":"性能监控","model":key})
        window.lp=next(iter(window.launchpads.values()));window.multi_cfg.update(enabled=True,link_mode="扩展画布",devices=items)
        window._connected_ui();window.device_status.configure(text="TEST · 2 台模拟灯板")
        remote_state=window._remote_state
        window._remote_state=lambda:{**remote_state(),"test_virtual_pads":True}
    window._show_mode("实时 VJ")
    window.title("Launchpad Studio · VJ TEST"+(" · 模拟灯板" if "--virtual-pads" in sys.argv else ""))
    handle=window._handle_remote_command
    window._handle_remote_command=lambda action,value:window._close() if action=="test.close" else handle(action,value)
    window.after(600000,window._close)
    window.mainloop()
