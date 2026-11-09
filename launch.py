"""Mac launcher; the service is local and keeps working for the paired iPad."""
from pathlib import Path
import json,urllib.request,subprocess,time,os,webbrowser,sys,shutil
ROOT=Path(__file__).resolve().parent
PYTHON=os.environ.get('CREATURE_LAB_PYTHON',sys.executable)
URL='http://127.0.0.1:8765'
def ready():
    try:return json.load(urllib.request.urlopen(URL+'/health',timeout=1)).get('app')=='creature-lab'
    except Exception:return False
def launch(open_browser=True):
    if not ready():
        import shlex
        (ROOT/'runtime').mkdir(exist_ok=True)
        session='creature_lab_service_20261105'
        command=shlex.quote(PYTHON)+' -u '+shlex.quote(str(ROOT/'server.py'))+' 2>&1 | tee -a '+shlex.quote(str(ROOT/'runtime/server.log'))
        tmux=shutil.which('tmux')
        if not tmux:raise RuntimeError('Install tmux or run python server.py directly.')
        if subprocess.run([tmux,'has-session','-t',session],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
            subprocess.run([tmux,'new-session','-d','-s',session,'-c',str(ROOT)],check=True)
        subprocess.run([tmux,'send-keys','-t',session,command,'Enter'],check=True)
        subprocess.run(['osascript','-e','tell application "Terminal" to do script "'+tmux+' attach -r -t '+session+'"'],stdout=subprocess.DEVNULL,check=False)
        for _ in range(60):
            if ready():break
            time.sleep(.2)
        else:raise RuntimeError('起動できませんでした。runtime/server.logを確認してください。')
    if open_browser:webbrowser.open(URL)
    return URL
if __name__=='__main__':
    if '--check' in sys.argv:print('READY' if ready() else 'STOPPED')
    else:launch()
