"""Headless, local A1 mini slicing. Networking is independent of Bambu Studio."""
from pathlib import Path
import sys,json,subprocess,zipfile,re
import xml.etree.ElementTree as ET
import trimesh as tm
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'geometry_support'))
from geometry import _clean_mesh as clean
APP=Path('/Applications/BambuStudio.app/Contents/MacOS/BambuStudio')
PRO=APP.parents[1]/'Resources/profiles/BBL'

def available():return APP.is_file()
def resolve(cat,name):
    d=json.loads((PRO/cat/(name+'.json')).read_text());r=resolve(cat,d['inherits']) if d.get('inherits') else {}
    for inc in d.get('include',[]):r.update(resolve(cat,inc))
    r.update({k:v for k,v in d.items() if k not in ('inherits','include','from','type','setting_id','instantiation','description','name')});return r
def seconds(t):return sum(int(n)*{'h':3600,'m':60,'s':1}[u] for n,u in re.findall(r'(\d+)([hms])',t))
def run(args,log):
    with log.open('x') as out:r=subprocess.run([str(APP),'--debug','2',*map(str,args)],stdout=out,stderr=subprocess.STDOUT,timeout=150)
    if r.returncode:raise RuntimeError('自動スライスに失敗しました。Mac側のログを確認してください。')

def slice_model(stl,work,nozzle='0.6',quality='standard'):
    if not available():raise RuntimeError('このMacにBambu Studioのスライサーが見つかりません。')
    if nozzle not in ('0.6','0.8') or quality not in ('standard','fast'):raise ValueError('対応していない印刷設定です。')
    work=Path(work);work.mkdir()
    process=('0.30mm Standard @BBL A1M 0.6 nozzle' if quality=='standard' else '0.42mm Extra Draft @BBL A1M 0.6 nozzle') if nozzle=='0.6' else '0.40mm Standard @BBL A1M 0.8 nozzle'
    mesh=tm.load_mesh(stl);lo,hi=mesh.bounds
    if max(mesh.extents)>170:raise ValueError('A1 miniの造形範囲を超えています。')
    # Keep the validated local coordinates. Baking +90 mm into float32 STL
    # can collapse microscopic Boolean closure facets; 3MF transforms avoid it.
    mesh,_=clean(mesh);placed=work/'placed.stl';mesh.export(placed)
    machine='Bambu Lab A1 mini '+nozzle+' nozzle'
    config=json.loads((ROOT/'slicer_seed.json').read_text())
    for cat,name in [('machine',machine),('process',process),('filament','Bambu PLA Basic @BBL A1M')]:config.update(resolve(cat,name))
    config.update(printer_settings_id=machine,print_settings_id='Creature Lab '+process,
        filament_settings_id=['Bambu PLA Basic @BBL A1M'],filament_colour=['#70BBA4'],nozzle_type=['hardened_steel'],
        wall_loops='2',top_shell_layers='3',bottom_shell_layers='3',top_shell_thickness='0.9',bottom_shell_thickness='0.9',
        sparse_infill_density='10%',sparse_infill_pattern='grid',enable_support='0',raft_layers='0',brim_type='no_brim',
        enable_prime_tower='0',print_sequence='by layer',curr_bed_type='Textured PEI Plate',print_compatible_printers=[machine])
    config['filament_ids']=[config['filament_id']]
    raw=work/'imported.3mf';run(['--orient','0','--arrange','1','--ensure-on-bed','--export-3mf',raw,placed],work/'import.log')
    positioned=tm.load(raw,force='scene').to_mesh()
    if positioned.bounds[0,2]<-.001 or any(positioned.bounds[0,:2]<0) or any(positioned.bounds[1,:2]>180):
        raise ValueError('A1 miniのプレート内に配置できませんでした。')
    if abs(positioned.volume-mesh.volume)>.04:raise ValueError('配置後の形状確認に失敗しました。')
    project=work/'creature.3mf'
    with zipfile.ZipFile(raw) as src,zipfile.ZipFile(project,'x',zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data=src.read(item.filename)
            if item.filename=='Metadata/project_settings.config':data=json.dumps(config,indent=2).encode()
            if item.filename=='Metadata/model_settings.config':
                tree=ET.fromstring(data)
                for plate in tree.findall('plate'):ET.SubElement(plate,'metadata',key='bed_type',value='Textured PEI Plate')
                data=ET.tostring(tree,encoding='utf-8',xml_declaration=True)
            dst.writestr(item,data)
    sliced=work/'creature.gcode.3mf'
    run(['--slice','0','--export-3mf',sliced.name,'--outputdir',work,project],work/'slice.log')
    res=json.loads((work/'result.json').read_text());assert res['return_code']==0
    plate=res['sliced_plates'][0]
    with zipfile.ZipFile(sliced) as archive:
        names=[n for n in archive.namelist() if n.endswith('.gcode')]
        if len(names)!=1:raise RuntimeError('単一プレートの印刷ファイルが必要です。')
        gc=archive.read(names[0]).decode()
        actual=json.loads(archive.read('Metadata/project_settings.config'))
        assert actual['nozzle_diameter']==[nozzle] and actual['printer_model']=='Bambu Lab A1 mini'
    if any(l.startswith('; FEATURE: Support') for l in gc.splitlines()):raise RuntimeError('サポート材が必要な形です。')
    if not re.search(r'^M220\s+S100(?:\s|;|$)',gc,re.MULTILINE):raise RuntimeError('標準速度（100%）の開始設定を確認できません。')
    header=next(l for l in gc.splitlines() if l.startswith('; model printing time:'))
    match=re.search(r'model printing time: (.*?); total estimated time: (.*)',header)
    result=dict(model_seconds=seconds(match[1]),total_seconds=seconds(match[2]),grams=sum(f['total_used_g'] for f in plate['filaments']),
        nozzle=nozzle,quality=quality,layer_height=float(config['layer_height']),warning=plate.get('warning_message',''),
        path=str(sliced),gcode_entry=names[0],backend='Bambu Studio CLI (画面操作なし)',filament='PLA Basic',bed_type='Textured PEI Plate',speed_percent=100)
    with (work/'verified.json').open('x') as out:json.dump(result,out,indent=2)
    return result
