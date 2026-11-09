"""Local HTTP six-stage workflow and real offline slice. No printer contact."""
from pathlib import Path
import urllib.request,urllib.error,json,time,zipfile,io
ROOT=Path(__file__).resolve().parents[1];BASE='http://127.0.0.1:8765'
def req(path,data=None):
    request=urllib.request.Request(BASE+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json','Origin':BASE})
    return json.load(urllib.request.urlopen(request,timeout=10))
def job(value):
    started=time.monotonic()
    while value['status'] in ('queued','running'):
        if time.monotonic()-started>180:raise AssertionError('job timeout')
        time.sleep(.3);value=req('/api/jobs/'+value['id'])
    assert value['status']=='done',value
    return value['result']
policy=req('/api/catalog')['workshop'];keys=['body','head','limbs','tail','eyes','expression']
assert policy['step_keys']==keys and policy['step_seconds']==60
assert policy['print_settings']==dict(nozzle='0.6',quality='standard',speed_percent=100,layer_height=.30)
state=req('/api/workshop/start',{});url='/api/workshop/'+state['id'];deadline=state['deadline']
state=req(url+'/choose',{'step_index':0,'key':'body','value':'dragon','size':40,'eye_size':1.2})
assert state['deadline']==deadline and state['config']['size']==32
choices=['dragon','horns','six','club','three','surprise']
for i,(key,value) in enumerate(zip(keys,choices)):
    assert state['step_key']==key
    state=req(url+'/choose',{'step_index':i,'key':key,'value':value})
    state=req(url+'/next',{'step_index':i})
    stale=req(url+'/next',{'step_index':i});assert stale['step_index']==i+1
assert state['phase']=='complete' and len(state['selections'])==6
frozen=dict(state['config']);state=req(url+'/choose',{'step_index':5,'key':'expression','value':'happy'})
assert state['config']==frozen
first=req(url+'/prepare',{});again=req(url+'/prepare',{});assert first['id']==again['id']
result=job(first);model=result['model'];sliced=result['slice']
assert all(model['config'][key]==value for key,value in zip(keys,choices))
assert model['config']['eye_size']==.85 and 25<=model['config']['size']<=32
assert model['face_layout']['eye_count']==3
assert (sliced['nozzle'],sliced['quality'],sliced['layer_height'],sliced['speed_percent'])==('0.6','standard',.30,100)
assert sliced['total_seconds']>sliced['model_seconds']>0
assert result['estimated_elapsed_seconds']>=result['selection_seconds']+sliced['total_seconds']
blob=urllib.request.urlopen(BASE+sliced['download_url']).read()
with zipfile.ZipFile(io.BytesIO(blob)) as archive:
    gcode=archive.read(sliced['gcode_entry']).decode()
    assert '\nM220 S100' in gcode and '; FEATURE: Support' not in gcode
report=ROOT/'runtime'/('workshop_integration_'+str(time.time_ns())+'.json')
with report.open('x') as out:json.dump(result,out,ensure_ascii=False,indent=2)
print('WORKSHOP_HTTP_PASS',json.dumps(dict(choices=model['config'],trials=result['size_trials'],selection_seconds=result['selection_seconds'],preparation_seconds=result['preparation_seconds'],total_seconds=sliced['total_seconds'],report=str(report))),flush=True)
