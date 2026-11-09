"""Durable print requests handed to the official Mac Bambu Studio app.

Queueing or opening a file never means the printer has started. The operator
selects the cloud-connected printer and starts the print in Bambu Studio.
"""
from pathlib import Path
import hashlib,json,os,re,secrets,shutil,subprocess,threading,time,zipfile

APP=Path('/Applications/BambuStudio.app')
ROOT=Path(os.environ.get('CREATURE_LAB_STUDIO_QUEUE',str(Path(__file__).resolve().parent/'runtime/studio_queue')))
LOCK=threading.RLock()

def available():return (APP/'Contents/MacOS/BambuStudio').is_file()
def _root():ROOT.mkdir(parents=True,exist_ok=True);return ROOT
def _path(id):
    if not re.fullmatch(r'[a-f0-9]{20}',str(id)):raise ValueError('印刷依頼が見つかりません。')
    return _root()/id/'request.json'
def _read(path):return json.loads(path.read_text())
def _save(path,value):
    backup=path.with_name('request_before_updates.json')
    if path.exists() and not backup.exists():shutil.copy2(path,backup)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def public(value):
    return {k:v for k,v in value.items() if k not in ('filename','sha256')}|{
        'download_url':'/api/studio/queue/'+value['id']+'/download'}
def get(id):
    path=_path(id)
    if not path.is_file():raise ValueError('印刷依頼が見つかりません。')
    return _read(path)
def items():
    with LOCK:
        return sorted((public(_read(p)) for p in _root().glob('*/request.json')),key=lambda v:v['created'],reverse=True)

def enqueue(sliced,name,model_id=None):
    if not available():raise ValueError('このMacにBambu Studioが見つかりません。')
    if (sliced.get('nozzle'),sliced.get('quality'),sliced.get('speed_percent'))!=('0.6','standard',100):
        raise ValueError('A1 mini・0.6 mm・標準100%の印刷ファイルが必要です。')
    name=str(name or 'オリジナル生物').strip()[:40] or 'オリジナル生物'
    source=Path(sliced['path'])
    with zipfile.ZipFile(source) as archive:
        settings=json.loads(archive.read('Metadata/project_settings.config'))
        if settings.get('printer_model')!='Bambu Lab A1 mini' or settings.get('nozzle_diameter')!=['0.6']:
            raise ValueError('印刷ファイルのプリンター設定が一致しません。')
        if sliced['gcode_entry'] not in archive.namelist():raise ValueError('印刷G-codeが見つかりません。')
    with LOCK:
        for old in items():
            if old['slice_id']==sliced['id']:return public(get(old['id']))
        id=secrets.token_hex(10);folder=_root()/id;folder.mkdir()
        safe=re.sub(r'[^\wぁ-んァ-ヶ一-龠ー-]','_',name).strip('_')[:32] or 'creature'
        filename='CreatureLab_'+safe+'_'+id[:6]+'.gcode.3mf'
        target=folder/filename
        with source.open('rb') as src,target.open('xb') as dst:shutil.copyfileobj(src,dst)
        sha=hashlib.sha256(target.read_bytes()).hexdigest()
        if sha!=hashlib.sha256(source.read_bytes()).hexdigest():raise ValueError('印刷ファイルのコピー検証に失敗しました。')
        value=dict(id=id,name=name,created=time.time(),status='queued',slice_id=sliced['id'],model_id=model_id,
            filename=filename,sha256=sha,nozzle='0.6',quality='standard',speed_percent=100,
            model_seconds=sliced['model_seconds'],total_seconds=sliced['total_seconds'],grams=sliced['grams'])
        with (folder/'request.json').open('x') as out:json.dump(value,out,ensure_ascii=False,indent=2)
        return public(value)

def file(id):
    value=get(id);path=_path(id).parent/value['filename']
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=value['sha256']:
        raise ValueError('印刷ファイルを確認できません。')
    return path

def open_studio(id):
    """Called only from the Mac queue's explicit Open button; no print action."""
    if not available():raise ValueError('このMacにBambu Studioが見つかりません。')
    with LOCK:
        value=get(id);path=file(id)
        result=subprocess.run(['/usr/bin/open','-a',str(APP),str(path)],capture_output=True,text=True,timeout=12)
        if result.returncode:raise ValueError('Bambu Studioでファイルを開けませんでした。Mac側を確認してください。')
        value.update(status='opened',opened_at=time.time())
        _save(_path(id),value)
        return public(value)|{'message':'Bambu Studioへ渡しました。Macでプリンターと内容を確認し、「プレートを印刷」を押してください。'}

def mark_sent(id):
    with LOCK:
        value=get(id)
        if value['status']=='queued':raise ValueError('先にBambu Studioで開いて、送信してください。')
        value.update(status='sent_by_operator',marked_sent_at=time.time())
        _save(_path(id),value)
        return public(value)
