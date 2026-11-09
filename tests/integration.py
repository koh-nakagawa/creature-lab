from pathlib import Path
import urllib.request,urllib.error,json,time,zipfile,io,sys
ROOT=Path(__file__).resolve().parents[1];BASE='http://127.0.0.1:8765'
def req(path,data=None):
    request=urllib.request.Request(BASE+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json','Origin':BASE})
    return json.load(urllib.request.urlopen(request,timeout=10))
def job(value):
    start=time.monotonic()
    while value['status'] in ('queued','running'):
        if time.monotonic()-start>150:raise AssertionError('job timeout')
        time.sleep(.2);value=req('/api/jobs/'+value['id'])
    assert value['status']=='done',value
    return value['result']
cat=req('/api/catalog');assert len(cat['groups'])>=8
models=[]
for preset in [cat['presets'][0],cat['presets'][3]]:
    value=job(req('/api/models',{'config':preset['config']}));models.append(value)
    stl=urllib.request.urlopen(BASE+value['stl_url']).read();assert len(stl)>1000
    assert value['face_layout']['eye_count']==len(value['face_layout']['eyes'])
    print('HTTP_MODEL_PASS',preset['id'],value['geometry']['dimensions_mm'],flush=True)
cached=req('/api/models',{'config':models[0]['config']});assert cached['status']=='done' and cached['result']['id']==models[0]['id']
sliced=job(req('/api/slice',{'model_id':models[0]['id'],'nozzle':'0.6','quality':'standard'}))
assert sliced['quality']=='standard' and sliced['layer_height']==.30 and sliced['speed_percent']==100
assert sliced['model_seconds']>0 and sliced['total_seconds']>sliced['model_seconds']
blob=urllib.request.urlopen(BASE+sliced['download_url']).read()
with zipfile.ZipFile(io.BytesIO(blob)) as archive:
    assert sliced['gcode_entry'] in archive.namelist()
    settings=json.loads(archive.read('Metadata/project_settings.config'))
    assert settings['nozzle_diameter']==['0.6'] and settings['printer_model']=='Bambu Lab A1 mini'
    assert '\nM220 S100' in archive.read(sliced['gcode_entry']).decode()
print('HTTP_SLICE_EXPORT_PASS',sliced['model_seconds'],sliced['total_seconds'],len(blob),flush=True)
try:req('/api/print',{'slice_id':sliced['id'],'confirmed':True})
except urllib.error.HTTPError as exc:
    assert exc.code==400 and 'IP' in json.load(exc)['error']
else:raise AssertionError('Unconfigured printer accepted a print')
try:req('/api/models',{'config':{'body':'not-a-part'}})
except urllib.error.HTTPError as exc:assert exc.code==400
else:raise AssertionError('Unknown geometry accepted')
for nozzle,quality in [('0.8','standard'),('0.6','fast')]:
    try:req('/api/slice',{'model_id':models[0]['id'],'nozzle':nozzle,'quality':quality})
    except urllib.error.HTTPError as exc:assert exc.code==400
    else:raise AssertionError('Non-standard print setting accepted')
report={'models':[v['id'] for v in models],'slice':sliced,'checks':['catalog','two_distinct_models','actual_stl','automatic_eye_count','model_cache','headless_slice','3mf_download','unconfigured_print_rejected','invalid_part_rejected']}
dest=ROOT/'runtime'/('integration_'+str(int(time.time()))+'.json')
with dest.open('x') as out:json.dump(report,out,indent=2)
print('ALL_HTTP_INTEGRATION_TESTS_PASSED',flush=True)
