from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse,quote
from http.cookies import SimpleCookie
import json,secrets,time,threading,hashlib,socket,subprocess,traceback,sys,argparse,re
import geometry,slicer,printer_transport,workshop,studio_handoff

ROOT=Path(__file__).resolve().parent
RUNTIME=ROOT/'runtime';RUNTIME.mkdir(exist_ok=True)
(RUNTIME/'jobs').mkdir(exist_ok=True)
STATE_LOCK=threading.RLock();SEND_LOCK=threading.Lock();GENERATE=ThreadPoolExecutor(max_workers=1);OPERATE=ThreadPoolExecutor(max_workers=2)
JOBS={};MODELS={};SLICES={};CACHE={};SESSIONS=set();PAIR_ATTEMPTS={};SUBMISSIONS=set()
WORKSHOPS={}
PAIR_CODE=''.join(str(secrets.randbelow(10)) for _ in range(6))
PRINTER={'ip':'','serial':'','access_code':'','nozzle':'0.6'}
LAST_PRINTER=None;PORT=8765

def model_digest(config):
    return hashlib.sha256(json.dumps({'config':config,'model_revision':geometry.MODEL_REVISION},sort_keys=True,separators=(',',':')).encode()).hexdigest()

def restore_generated_files():
    """Keep existing printable files and completed creations across an update."""
    for path in (RUNTIME/'jobs').glob('*/recipe.json'):
        key=path.parent.name
        if not re.fullmatch(r'[a-f0-9]{20}',key) or not (path.parent/'creature.stl').is_file():continue
        try:
            value=json.loads(path.read_text());value.update(id=key,stl_url='/api/models/'+key+'/stl',recipe_url='/api/models/'+key+'/recipe')
            MODELS[key]=value;JOBS[key]=dict(id=key,kind='model',status='done',result=value,created=path.stat().st_mtime)
            if value.get('model_revision')==geometry.MODEL_REVISION:CACHE[model_digest(value['config'])]=key
        except (OSError,ValueError,KeyError):continue
    for path in (RUNTIME/'jobs').glob('*/verified.json'):
        key=path.parent.name;file=path.parent/'creature.gcode.3mf'
        if not re.fullmatch(r'[a-f0-9]{20}',key) or not file.is_file():continue
        try:
            value=json.loads(path.read_text());value.update(id=key,path=str(file),download_url='/api/slices/'+key+'/download')
            SLICES[key]=value;JOBS[key]=dict(id=key,kind='slice',status='done',result={k:v for k,v in value.items() if k!='path'},created=path.stat().st_mtime)
        except (OSError,ValueError,KeyError):continue
    snapshots=[p for p in [RUNTIME/'workshop_sessions_for_studio_20261107.json',RUNTIME/'workshop_sessions_for_fangs_20261107.json'] if p.is_file()]
    for snapshot in sorted(snapshots,key=lambda p:p.stat().st_mtime):
        for value in json.loads(snapshot.read_text()):
            s=workshop.Session(value['id'],now=value['started_at']);s.index=value['step_index'];s.config=value['config'];s.phase=value['phase']
            s.deadline=value['deadline'] or value['completed_at'] or time.time();s.completed_at=value['completed_at'];s.selections=value['selections']
            s.prepare_job_id=value.get('prepare_job_id')
            for attribute in ('activity','last_seen_at','client_ip','last_preview_job_id'):
                if attribute in value:setattr(s,attribute,value[attribute])
            WORKSHOPS[s.id]=s
    for path in (RUNTIME/'jobs').glob('*/workshop_result.json'):
        try:
            value=json.loads(path.read_text())
            if value.get('server_port',8765)!=PORT:continue
            sid=value['workshop_id'];key=path.parent.name;sliced=value['slice']
            if sliced['id'] not in SLICES:continue
            SLICES[sliced['id']].update(model_id=value['model']['id'])
            completed=path.stat().st_mtime;s=workshop.Session(sid,now=completed-value['selection_seconds'])
            s.index=6;s.phase='complete';s.completed_at=completed;s.config=value['model']['config'];s.prepare_job_id=key
            if sid in WORKSHOPS:
                s=WORKSHOPS[sid];s.phase='complete';s.index=6;s.prepare_job_id=key
                if s.completed_at is None:s.completed_at=completed
            WORKSHOPS[sid]=s;JOBS[key]=dict(id=key,kind='workshop_prepare',status='done',result=value,created=completed)
        except (OSError,ValueError,KeyError):continue

def addresses():
    out=[]
    for device in ('en0','en1'):
        try:
            ip=subprocess.check_output(['ipconfig','getifaddr',device],stderr=subprocess.DEVNULL,text=True).strip()
            if ip and ip not in out:out.append(ip)
        except (OSError,subprocess.CalledProcessError):pass
    return out
IPS=addresses()

def event(event_type,**data):
    with STATE_LOCK,(RUNTIME/'events.jsonl').open('a') as out:out.write(json.dumps({'time':time.time(),'event':event_type,**data},ensure_ascii=False)+'\n')

def create_job(kind,action):
    with STATE_LOCK:
        if sum(j['status'] in ('queued','running') for j in JOBS.values())>=12:raise ValueError('処理待ちが多くなっています。少し待ってください。')
        key=secrets.token_hex(10);job={'id':key,'kind':kind,'status':'queued','created':time.time()};JOBS[key]=job
    def work():
        with STATE_LOCK:job['status']='running'
        try:
            result=action(key)
            with STATE_LOCK:job.update(status='done',result=result)
            event('job_done',id=key,kind=kind)
        except Exception as exc:
            # No printer credentials appear in arguments or logs.
            traceback.print_exc()
            with STATE_LOCK:job.update(status='error',error=str(exc)[:400])
            event('job_error',id=key,kind=kind,error_type=type(exc).__name__)
    (GENERATE if kind in ('model','workshop_prepare') else OPERATE).submit(work)
    return dict(job)

def build_model(key,config):
    folder=RUNTIME/'jobs'/key;folder.mkdir();path=folder/'creature.stl'
    result=geometry.generate(config,path)
    result.update(id=key,stl_url='/api/models/'+key+'/stl',recipe_url='/api/models/'+key+'/recipe')
    with (folder/'recipe.json').open('x') as out:json.dump(result,out,ensure_ascii=False,indent=2)
    with STATE_LOCK:MODELS[key]=result
    return result

def model_job(config):
    config=geometry.normalize_config(config)
    digest=model_digest(config)
    with STATE_LOCK:
        if digest in CACHE:
            m=MODELS[CACHE[digest]]
            return {'id':m['id'],'kind':'model','status':'done','result':m}
    def generate(key):
        result=build_model(key,config)
        with STATE_LOCK:CACHE[digest]=key
        return result
    return create_job('model',generate)

def slice_job(model_id,nozzle,quality):
    if model_id not in MODELS:raise ValueError('先に生物を作成してください。')
    if nozzle!=workshop.NOZZLE or quality!=workshop.QUALITY:raise ValueError('印刷は0.6 mm・標準（100%）に固定されています。')
    def perform(key):
        result=slicer.slice_model(RUNTIME/'jobs'/model_id/'creature.stl',RUNTIME/'jobs'/key,nozzle,quality)
        result.update(id=key,model_id=model_id,download_url='/api/slices/'+key+'/download')
        with STATE_LOCK:SLICES[key]=result
        return {k:v for k,v in result.items() if k!='path'}
    return create_job('slice',perform)

def prepare_workshop(session):
    if session.state()['phase']!='complete':raise ValueError('すべてのステップが終わってから準備します。')
    if session.prepare_job_id and JOBS[session.prepare_job_id]['status']!='error':return dict(JOBS[session.prepare_job_id])
    chosen=dict(session.config)
    def perform(key):
        trials=[];size=workshop.START_SIZE
        for _ in range(3):
            config=workshop.automatic_config(chosen);config['size']=size
            model_id=secrets.token_hex(10);model=build_model(model_id,config)
            slice_id=secrets.token_hex(10)
            result=slicer.slice_model(RUNTIME/'jobs'/model_id/'creature.stl',RUNTIME/'jobs'/slice_id,workshop.NOZZLE,workshop.QUALITY)
            result.update(id=slice_id,model_id=model_id,download_url='/api/slices/'+slice_id+'/download')
            with STATE_LOCK:SLICES[slice_id]=result
            trials.append(dict(size_mm=size,model_id=model_id,slice_id=slice_id,model_seconds=result['model_seconds'],total_seconds=result['total_seconds']))
            new_size=workshop.next_size(size,result['model_seconds'])
            if new_size is None:break
            size=new_size
        public_slice={k:v for k,v in result.items() if k!='path'}
        selection_seconds=max(0,session.completed_at-session.started)
        preparation_seconds=max(0,time.time()-session.completed_at)
        warning='' if result['model_seconds']<=workshop.MAX_MODEL_SECONDS else 'この組み合わせは造形に5分以上かかります。画面の見積もりを確認してください。'
        output=dict(workshop_id=session.id,server_port=PORT,model=model,slice=public_slice,automatic=True,size_trials=trials,
                    selection_seconds=selection_seconds,preparation_seconds=preparation_seconds,
                    estimated_elapsed_seconds=selection_seconds+preparation_seconds+result['total_seconds'],warning=warning)
        folder=RUNTIME/'jobs'/key;folder.mkdir()
        with (folder/'workshop_result.json').open('x') as out:json.dump(output,out,ensure_ascii=False,indent=2)
        return output
    job=create_job('workshop_prepare',perform);session.prepare_job_id=job['id'];return job

def workshop_monitor():
    queued={v['slice_id']:v for v in studio_handoff.items()}
    with STATE_LOCK:
        output=[]
        for s in sorted(WORKSHOPS.values(),key=lambda s:s.started,reverse=True)[:30]:
            value=s.state();job=JOBS.get(s.prepare_job_id,{})
            model=None;sliced=None;preview={}
            if job.get('status')=='done':model=job['result']['model'];sliced=job['result']['slice']
            else:
                preview=JOBS.get(getattr(s,'last_preview_job_id',None),{})
                if preview.get('status')=='done':model=preview['result']
            request=queued.get(sliced['id']) if sliced else None
            stage='selecting' if s.phase=='selecting' else 'ready' if sliced else 'error' if job.get('status')=='error' else 'preparing' if job else 'chosen'
            if request:stage=request['status']
            value.update(stage=stage,model_ready=bool(sliced),preview_url=model.get('stl_url') if model else None,
                preview_updating=bool(not sliced and (preview.get('status') in ('queued','running') or model and model['config']!=s.config)),
                last_seen_at=getattr(s,'last_seen_at',s.started),client_ip=getattr(s,'client_ip',''),
                activity=list(getattr(s,'activity',[])),error=job.get('error'),request_id=request['id'] if request else None)
            output.append(value)
        return output

class Handler(BaseHTTPRequestHandler):
    server_version='CreatureLab/1.0'
    def log_message(self,format,*args):print(time.strftime('%H:%M:%S'),format%args,flush=True)
    def local(self):return self.client_address[0] in ('127.0.0.1','::1')
    def touch(self,session,action=None,**details):
        session.last_seen_at=time.time();session.client_ip=self.client_address[0]
        if action:
            history=getattr(session,'activity',[])
            history.append(dict(at=session.last_seen_at,action=action,**details));session.activity=history[-40:]
    def staff(self):
        if self.local():return True
        cookie=SimpleCookie()
        try:cookie.load(self.headers.get('Cookie',''))
        except Exception:return False
        return cookie.get('creature_staff') is not None and cookie['creature_staff'].value in SESSIONS
    def reply(self,data,status=200,headers=None):
        blob=json.dumps(data,ensure_ascii=False,allow_nan=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(blob)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        for k,v in (headers or {}).items():self.send_header(k,v)
        self.end_headers();self.wfile.write(blob)
    def file(self,path,mime,download=None):
        data=path.read_bytes();self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)))
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-cache')
        if download:
            fallback=re.sub(r'[^A-Za-z0-9._-]','_',download)
            self.send_header('Content-Disposition','attachment; filename="'+fallback+'"; filename*=UTF-8\'\''+quote(download,safe=''))
        self.end_headers();self.wfile.write(data)
    def do_GET(self):
        path=urlparse(self.path).path
        try:
            if path=='/health':return self.reply({'ok':True,'app':'creature-lab'})
            if path=='/api/catalog':return self.reply(geometry.catalog()|{'workshop':workshop.catalog_policy()})
            if path=='/api/bootstrap':return self.reply(dict(staff=self.staff(),pairing_code=PAIR_CODE if self.local() else None,
                ipad_urls=['http://'+ip+':'+str(PORT) for ip in addresses()],slicer_available=slicer.available(),printer_configured=bool(PRINTER['access_code']),
                backend='Macで自動スライス / Bambu Studioでクラウド送信',printer=LAST_PRINTER,local=self.local(),
                print_transport='bambu_studio_cloud',studio_available=studio_handoff.available(),studio_queue_url='/studio-queue.html'))
            if path=='/api/studio/queue':
                if not self.local():return self.reply({'error':'印刷待ちはMacの画面で開いてください。'},403)
                return self.reply({'items':studio_handoff.items(),'studio_available':studio_handoff.available()})
            if path=='/api/studio/monitor':
                if not self.local():return self.reply({'error':'体験モニターはMacで開いてください。'},403)
                return self.reply({'sessions':workshop_monitor(),'server_time':time.time()})
            match=re.fullmatch(r'/api/studio/queue/([a-f0-9]{20})/download',path)
            if match:
                if not self.staff():return self.reply({'error':'印刷担当者の接続が必要です。'},403)
                file=studio_handoff.file(match[1]);return self.file(file,'application/zip',file.name)
            if path=='/api/printer/settings':
                if not self.staff():return self.reply({'error':'印刷担当者の接続コードを入力してください。'},403)
                return self.reply({k:PRINTER[k] for k in ('ip','serial','nozzle')}|{'has_access_code':bool(PRINTER['access_code'])})
            match=re.fullmatch(r'/api/workshop/([a-f0-9]{20})',path)
            if match:
                with STATE_LOCK:
                    session=WORKSHOPS.get(match[1])
                    if session:self.touch(session)
                    return self.reply(session.state() if session else {'error':'体験をスタートしてください。'},200 if session else 404)
            match=re.fullmatch(r'/api/jobs/([a-f0-9]{20})',path)
            if match:
                job=JOBS.get(match[1]);return self.reply(job if job else {'error':'処理が見つかりません。'},200 if job else 404)
            match=re.fullmatch(r'/api/models/([a-f0-9]{20})/(stl|recipe)',path)
            if match and match[1] in MODELS:
                key,kind=match.groups();p=RUNTIME/'jobs'/key/('creature.stl' if kind=='stl' else 'recipe.json')
                return self.file(p,'model/stl' if kind=='stl' else 'application/json',('creature_'+key+'.'+('stl' if kind=='stl' else 'json')))
            match=re.fullmatch(r'/api/slices/([a-f0-9]{20})/download',path)
            if match and match[1] in SLICES:return self.file(Path(SLICES[match[1]]['path']),'application/zip','creature_'+match[1]+'.gcode.3mf')
            relative='workshop.html' if path in ('/','/index.html') else path.lstrip('/')
            file=(ROOT/'frontend'/relative).resolve()
            if not file.is_relative_to((ROOT/'frontend').resolve()) or not file.is_file():return self.reply({'error':'見つかりません。'},404)
            mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml','.png':'image/png','.webmanifest':'application/manifest+json'}.get(file.suffix,'application/octet-stream')
            return self.file(file,mime)
        except (OSError,ValueError) as exc:return self.reply({'error':str(exc)},400)
    def do_POST(self):
        try:
            origin=self.headers.get('Origin')
            if origin and urlparse(origin).netloc!=self.headers.get('Host'):return self.reply({'error':'別のサイトからの操作は受け付けません。'},403)
            length=int(self.headers.get('Content-Length','0'))
            if length>65536:return self.reply({'error':'データが大きすぎます。'},413)
            data=json.loads(self.rfile.read(length) or b'{}');path=urlparse(self.path).path
            if path=='/api/session':
                times=PAIR_ATTEMPTS.setdefault(self.client_address[0],[]);now=time.monotonic();times[:]=[t for t in times if now-t<300]
                if len(times)>=8:return self.reply({'error':'少し待ってから再度入力してください。'},429)
                times.append(now)
                if not secrets.compare_digest(str(data.get('code','')),PAIR_CODE):return self.reply({'error':'接続コードが違います。Macの画面を確認してください。'},403)
                token=secrets.token_hex(24);SESSIONS.add(token)
                return self.reply({'staff':True},headers={'Set-Cookie':'creature_staff='+token+'; Path=/; HttpOnly; SameSite=Strict'})
            if path=='/api/models':return self.reply(model_job(data.get('config',{})),202)
            if path=='/api/workshop/start':
                key=secrets.token_hex(10)
                with STATE_LOCK:
                    WORKSHOPS[key]=workshop.Session(key);self.touch(WORKSHOPS[key],'start');state=WORKSHOPS[key].state()
                event('workshop_started',id=key);return self.reply(state,201)
            match=re.fullmatch(r'/api/workshop/([a-f0-9]{20})/(choose|next|preview|prepare)',path)
            if match:
                with STATE_LOCK:
                    session=WORKSHOPS.get(match[1])
                    if session is None:return self.reply({'error':'体験をスタートしてください。'},404)
                    action=match[2]
                    self.touch(session)
                    if action=='choose':
                        before=dict(session.config);state=session.choose(int(data.get('step_index',-1)),str(data.get('key','')),data.get('value'))
                        if before!=session.config:self.touch(session,'choose',key=data['key'],value=data['value'])
                        return self.reply(state)
                    if action=='next':
                        before=session.index;state=session.advance(int(data.get('step_index',-1)))
                        if before!=session.index:self.touch(session,'next',step_index=session.index)
                        return self.reply(state)
                    if action=='preview':
                        result=model_job(session.state()['config']);session.last_preview_job_id=result['id'];return self.reply(result,202)
                    return self.reply(prepare_workshop(session),202)
            if path=='/api/slice':return self.reply(slice_job(str(data.get('model_id','')),str(data.get('nozzle','0.6')),str(data.get('quality','standard'))),202)
            match=re.fullmatch(r'/api/studio/queue/([a-f0-9]{20})/(open|sent)',path)
            if match:
                if not self.local():return self.reply({'error':'この操作はMac側の印刷待ち画面で行ってください。'},403)
                return self.reply(studio_handoff.open_studio(match[1]) if match[2]=='open' else studio_handoff.mark_sent(match[1]))
            if path.startswith('/api/printer') or path=='/api/print':
                if not self.staff():return self.reply({'error':'印刷担当者の接続コードを入力してください。'},403)
            if path=='/api/printer/settings':
                candidate={k:str(data.get(k,PRINTER.get(k,''))).strip() for k in ('ip','serial','access_code','nozzle')}
                if not candidate['access_code']:candidate['access_code']=PRINTER['access_code']
                printer_transport.validate_profile(candidate)
                if candidate['nozzle']!='0.6':raise ValueError('この体験では0.6 mmノズルを使用します。')
                with STATE_LOCK:PRINTER.clear();PRINTER.update(candidate)
                return self.reply({'saved':True,'session_only':True})
            if path=='/api/printer/check':
                return self.reply({'error':'印刷はMacのBambu Studioから送信する方式に変わりました。画面を再読み込みしてください。'},400)
            if path=='/api/print':
                key=str(data.get('slice_id',''))
                if not data.get('confirmed'):raise ValueError('印刷内容を確認してください。')
                if key not in SLICES:raise ValueError('先に印刷ファイルを作成してください。')
                sliced=dict(SLICES[key]);name=str(data.get('name','オリジナル生物'))
                def send(job_id):
                    value=studio_handoff.enqueue(sliced,name,sliced.get('model_id'))
                    return dict(queued=True,started=False,request=value,queue_id=value['id'],
                        message='Macの印刷待ちに追加しました。スタッフがBambu Studioから印刷します。')
                return self.reply(create_job('studio_handoff',send),202)
            return self.reply({'error':'見つかりません。'},404)
        except (ValueError,printer_transport.PrinterError) as exc:return self.reply({'error':str(exc)},400)
        except Exception:
            traceback.print_exc();return self.reply({'error':'処理を開始できませんでした。Macのログを確認してください。'},500)

def main():
    global PORT
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8765);parser.add_argument('--host',default='0.0.0.0');args=parser.parse_args();PORT=args.port
    restore_generated_files()
    server=ThreadingHTTPServer((args.host,args.port),Handler);server.daemon_threads=True
    print('CREATURE LAB READY http://127.0.0.1:'+str(PORT),flush=True)
    for ip in IPS:print('iPad Wi-Fi URL http://'+ip+':'+str(PORT),flush=True)
    event('server_started',port=PORT)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close();GENERATE.shutdown(wait=False,cancel_futures=True);OPERATE.shutdown(wait=False,cancel_futures=True)
if __name__=='__main__':main()
