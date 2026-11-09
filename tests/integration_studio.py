"""Pilot-only HTTP flow; never opens Studio or starts a physical print."""
from pathlib import Path
import hashlib,json,time,urllib.request

ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:8766'
def req(path,data=None):
    r=urllib.request.Request(BASE+path,data=json.dumps(data).encode() if data is not None else None,
        headers={'Content-Type':'application/json','Origin':BASE})
    return json.load(urllib.request.urlopen(r,timeout=15))
def wait(value):
    deadline=time.monotonic()+180
    while value['status'] in ('queued','running'):
        assert time.monotonic()<deadline,'job timeout'
        time.sleep(.25);value=req('/api/jobs/'+value['id'])
    assert value['status']=='done',value
    return value['result']
def monitor(sid):return next(s for s in req('/api/studio/monitor')['sessions'] if s['id']==sid)

boot=req('/api/bootstrap');assert boot['print_transport']=='bambu_studio_cloud' and boot['studio_available']
s=req('/api/workshop/start',{});sid=s['id'];base='/api/workshop/'+sid
choices=dict(body='turtle',head='ears',limbs='flippers',tail='fan',eyes='three',expression='surprise')
for index,(key,value) in enumerate(choices.items()):
    s=req(base+'/choose',dict(step_index=index,key=key,value=value))
    m=monitor(sid);assert m['step_index']==index and m['config'][key]==value and not m['model_ready']
    if index==0:
        preview=wait(req(base+'/preview',{}))
        assert monitor(sid)['preview_url']==preview['stl_url']
    s=req(base+'/next',dict(step_index=index))
assert s['phase']=='complete'
result=wait(req(base+'/prepare',{}));m=monitor(sid)
assert m['stage']=='ready' and m['model_ready'] and m['preview_url']==result['model']['stl_url']
assert any(e['action']=='choose' for e in m['activity'])
assert all(result['model']['config'][k]==v for k,v in choices.items())
sliced=result['slice'];assert (sliced['nozzle'],sliced['quality'],sliced['speed_percent'])==('0.6','standard',100)
request=wait(req('/api/print',dict(slice_id=sliced['id'],name='モニター連動テスト',confirmed=True)))
assert request['queued'] and request['started'] is False
duplicate=wait(req('/api/print',dict(slice_id=sliced['id'],name='モニター連動テスト',confirmed=True)))
assert duplicate['queue_id']==request['queue_id']
queued=next(v for v in req('/api/studio/queue')['items'] if v['id']==request['queue_id'])
original=urllib.request.urlopen(BASE+sliced['download_url']).read()
copy=urllib.request.urlopen(BASE+queued['download_url']).read()
assert hashlib.sha256(copy).digest()==hashlib.sha256(original).digest()
m=monitor(sid);assert m['stage']=='queued' and m['request_id']==queued['id'] and m['model_ready']
dest=ROOT/'runtime'/('studio_integration_'+str(time.time_ns())+'.json')
with dest.open('x') as out:json.dump(dict(workshop_id=sid,queue_id=queued['id'],model_id=result['model']['id'],slice=sliced,
    bytes=len(copy),sha256=hashlib.sha256(copy).hexdigest(),checks=['six_stage_monitor','actual_preview','model_ready','queue_handoff','idempotence','copy_checksum','no_print_start']),out,ensure_ascii=False,indent=2)
print('STUDIO_MONITOR_HTTP_PASS',sid,queued['id'],len(copy),flush=True)
