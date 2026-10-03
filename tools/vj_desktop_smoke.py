"""Isolated desktop UI/remote test instance; does not change personal settings."""
import multiprocessing
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from core.settings import Settings


if __name__=="__main__":
    multiprocessing.freeze_support()
    app.ROOT=Path(__file__).resolve().parents[1]/"build"/"vj-ui-test"
    settings=Settings(app.ROOT/"data"/"settings.json")
    settings.data["remote"]["port"]=8767;settings.save()
    window=app.LaunchpadStudio();window._show_mode("实时 VJ")
    window.title("Launchpad Studio 2.2 · VJ TEST")
    handle=window._handle_remote_command
    window._handle_remote_command=lambda action,value:window._close() if action=="test.close" else handle(action,value)
    window.after(600000,window._close)
    window.mainloop()
