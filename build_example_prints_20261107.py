"""Create six app-achievable exhibit examples and one six-model A1 mini plate."""
from pathlib import Path
import hashlib,html,json,re,shutil,time,unicodedata,zipfile
import xml.etree.ElementTree as ET
import numpy as np
from PIL import Image,ImageDraw,ImageFont
import trimesh as tm
import geometry,workshop,slicer,generate_thumbnails as renderer

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'example_prints_20261107'
WORK=OUT/'_work'
ZIP=ROOT/'creature_examples_A1mini_0p6_20261107.zip'
CHOICES=[
 ('dragon',dict(head='horns',limbs='paws',tail='long',eyes='two',expression='smile')),
 ('armored',dict(head='round',limbs='six',tail='club',eyes='two',expression='flat')),
 ('octopus',dict(head='wide',limbs='tentacles',tail='none',eyes='three',expression='surprise')),
 ('slug',dict(head='horns',limbs='none',tail='curl',eyes='two',expression='smile')),
 ('turtle',dict(head='ears',limbs='flippers',tail='fan',eyes='one',expression='smile')),
 ('axolotl',dict(head='wide',limbs='paws',tail='fork',eyes='three',expression='fangs')),
]

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write_json(path,value):
    with Path(path).open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2)
def copy(src,dst):
    dst=Path(dst)
    with Path(src).open('rb') as a,dst.open('xb') as b:shutil.copyfileobj(a,b)
    assert sha(src)==sha(dst)
def duration(seconds):return f'{int(seconds)//60}分{int(seconds)%60:02d}秒'
def font(size):
    candidates=[p for p in Path('/System/Library/Fonts').glob('*.ttc') if 'ヒラギノ角ゴシック W3' in unicodedata.normalize('NFC',p.name)]
    return ImageFont.truetype(str(candidates[0]) if candidates else '/System/Library/Fonts/Hiragino Sans GB.ttc',size)

def batch_plate(records,config_project):
    work=WORK/'all_six';work.mkdir();pieces=[]
    for i,record in enumerate(records):
        mesh=tm.load_mesh(OUT/record['stl']);lo,hi=mesh.bounds
        mesh.apply_translation([[48,90,132][i%3]-(lo[0]+hi[0])/2,[65,115][i//3]-(lo[1]+hi[1])/2,-lo[2]])
        mesh,_=geometry._clean_mesh(mesh);pieces.append(mesh)
    combined=tm.util.concatenate(pieces);source=work/'all_six.stl'
    with source.open('xb') as f:f.write(tm.exchange.stl.export_stl(combined))
    reread=tm.load_mesh(source);assert reread.is_watertight and reread.is_volume and len(reread.split())==6
    raw=work/'imported.3mf';slicer.run(['--orient','0','--arrange','0','--export-3mf',raw,source],work/'import.log')
    imported=tm.load(raw,force='scene').to_mesh();bodies=imported.split()
    assert len(bodies)==6 and all(p.is_volume for p in bodies)
    assert imported.bounds[0,2]>=-.001
    assert np.all(imported.bounds[0,:2]>=15) and np.all(imported.bounds[1,:2]<=165)
    assert abs(imported.volume-reread.volume)<.01
    # Separate bounding boxes prove the arranged bodies cannot touch/collide.
    for i,a in enumerate(bodies):
        for b in bodies[i+1:]:
            gap=np.maximum(b.bounds[0,:2]-a.bounds[1,:2],a.bounds[0,:2]-b.bounds[1,:2])
            assert np.max(gap)>3,(a.bounds,b.bounds)
    with zipfile.ZipFile(config_project) as z:config=json.loads(z.read('Metadata/project_settings.config'))
    project=work/'all_six.3mf'
    with zipfile.ZipFile(raw) as src,zipfile.ZipFile(project,'x',zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data=src.read(item.filename)
            if item.filename=='Metadata/project_settings.config':data=json.dumps(config,ensure_ascii=False,indent=2).encode()
            if item.filename=='Metadata/model_settings.config':
                tree=ET.fromstring(data)
                for plate in tree.findall('plate'):ET.SubElement(plate,'metadata',key='bed_type',value='Textured PEI Plate')
                data=ET.tostring(tree,encoding='utf-8',xml_declaration=True)
            dst.writestr(item,data)
    sliced=work/'all_six.gcode.3mf'
    slicer.run(['--slice','0','--export-3mf',sliced.name,'--outputdir',work,project],work/'slice.log')
    result=json.loads((work/'result.json').read_text());assert result['return_code']==0 and len(result['sliced_plates'])==1
    plate=result['sliced_plates'][0]
    with zipfile.ZipFile(sliced) as z:
        entry=next(n for n in z.namelist() if n.endswith('.gcode'));gc=z.read(entry).decode()
        actual=json.loads(z.read('Metadata/project_settings.config'))
        assert actual['nozzle_diameter']==['0.6'] and actual['printer_model']=='Bambu Lab A1 mini'
        assert float(actual['layer_height'])==.30 and actual['enable_support']=='0' and actual['print_sequence']=='by layer'
        assert re.search(r'^M220\s+S100(?:\s|;|$)',gc,re.MULTILINE)
        assert '; FEATURE: Support' not in gc
        match=re.search(r'model printing time: (.*?); total estimated time: (.*)',gc)
    files=dict(stl='stl/00_all_six.stl',project='project/00_all_six.3mf',print='print/00_all_six.gcode.3mf')
    for source,key in [(source,'stl'),(project,'project'),(sliced,'print')]:copy(source,OUT/files[key])
    return files|dict(model_seconds=slicer.seconds(match[1]),total_seconds=slicer.seconds(match[2]),
        grams=sum(f['total_used_g'] for f in plate['filaments']),body_count=6,bounds_mm=imported.bounds.tolist(),warnings=plate.get('warning_message',''),gcode_entry=entry)

def main():
    OUT.mkdir(exist_ok=False);WORK.mkdir()
    for name in ['stl','print','project','recipes','previews']:(OUT/name).mkdir()
    with (OUT/'note.txt').open('x') as f:
        f.write('2026-11-07 JST 作例6種類と6体同時print plateの生成。\nTool: existing CAD Python/trimesh/manifold3d/Pillow + installed Bambu Studio CLI02.08.02.61. No installation/network/printer commands.\n')
        f.write('Command: existing CAD Python -u build_example_prints_20261107.py; cwd app root; visible tmux creature_lab_app_20261105:exhibit_samples; log runtime/exhibit_samples_20261107.log.\n')
        f.write('Inputs: app geometry.catalog presets + six selected-part overrides; workshop.automatic_config/next_size; slicer official A1 mini0.6/.30 Standard/PLA Basic/Textured PEI profiles. Output: stl, print G-code3mf, editable project3mf, recipe, preview, overview/manifest and ZIP. Existing files are never renamed/deleted/overwritten.\n')
    catalog=geometry.catalog();presets={p['id']:p for p in catalog['presets']}
    labels={g['key']:{o['id']:o['label'] for o in g['options']} for g in catalog['groups']}
    renderer.SIZE=(640,440);records=[];first_project=None
    for index,(body,overrides) in enumerate(CHOICES,1):
        stem=f'{index:02d}_{body}_modoki';chosen=workshop.automatic_config(presets[body]['config']|overrides)
        trials=[];size=workshop.START_SIZE
        for attempt in range(3):
            trial=WORK/(stem+f'_trial{attempt+1}');trial.mkdir()
            config=chosen|dict(size=size);source=trial/'creature.stl';model=geometry.generate(config,source)
            sliced=slicer.slice_model(source,trial/'slice','0.6','standard')
            trials.append(dict(size=size,model_seconds=sliced['model_seconds'],total_seconds=sliced['total_seconds']))
            newsize=workshop.next_size(size,sliced['model_seconds'])
            if newsize is None:break
            size=newsize
        assert sliced['nozzle']=='0.6' and sliced['quality']=='standard' and sliced['speed_percent']==100
        assert model['geometry']['watertight'] and model['geometry']['connected_components']==1
        assert model['face_layout']['eye_count']=={'one':1,'two':2,'three':3}[config['eyes']]
        if first_project is None:first_project=trial/'slice/creature.3mf'
        paths=dict(stl=f'stl/{stem}.stl',project=f'project/{stem}.3mf',print=f'print/{stem}.gcode.3mf',recipe=f'recipes/{stem}.json',preview=f'previews/{stem}.png')
        copy(source,OUT/paths['stl']);copy(trial/'slice/creature.3mf',OUT/paths['project']);copy(sliced['path'],OUT/paths['print'])
        write_json(OUT/paths['recipe'],model)
        renderer.render(tm.load_mesh(source),model,OUT/paths['preview'],'full')
        record=dict(number=index,name=presets[body]['label'],config=model['config'],geometry=model['geometry'],
            model_seconds=sliced['model_seconds'],total_seconds=sliced['total_seconds'],grams=sliced['grams'],
            warnings=sliced['warning'],size_trials=trials,parts={k:labels[k][config[k]] for k in workshop.STEP_KEYS},**paths)
        records.append(record);print('SAMPLE_READY',record['name'],record['geometry']['dimensions_mm'],duration(record['total_seconds']),flush=True)
    batch=batch_plate(records,first_project);print('ALL_SIX_PLATE_READY',duration(batch['total_seconds']),flush=True)
    sheet=Image.new('RGB',(1500,900),(246,245,239));draw=ImageDraw.Draw(sheet)
    for i,r in enumerate(records):
        pic=Image.open(OUT/r['preview']);pic.thumbnail((480,330));x=i%3*500;y=i//3*450
        sheet.paste(pic,(x+(500-pic.width)//2,y),pic)
        draw.text((x+20,y+330),f"{r['number']:02d}  {r['name']}",font=font(23),fill=(37,59,53))
        draw.text((x+20,y+370),f"約{max(r['geometry']['dimensions_mm']):.0f} mm  /  PLA {r['grams']:.1f} g",font=font(18),fill=(70,91,73))
        draw.text((x+20,y+402),'造形 '+duration(r['model_seconds'])+' / 準備込み '+duration(r['total_seconds']),font=font(17),fill=(70,91,73))
    sheet.save(OUT/'examples_overview.png')
    manifest=dict(date='2026-11-07',printer='Bambu Lab A1 mini',nozzle_mm=.6,layer_height_mm=.30,speed_percent=100,
        material='PLA Basic',bed='Textured PEI Plate',support=False,physical_print_verified=False,examples=records,batch=batch)
    manifest['checksums']={str(p.relative_to(OUT)):sha(p) for sub in ['stl','print','project','recipes','previews'] for p in (OUT/sub).iterdir()}
    write_json(OUT/'manifest.json',manifest)
    lines=['# 展示用作例6種類 — A1 mini / 0.6 mm','',
        '2026-11-07作成。アプリで選べる6つの部位の組み合わせを、実際の自動サイズ調整と同じ条件で生成しました。',
        '**設定：0.6 mmノズル、PLA、標準100%、0.30 mm Standard、Textured PEI、サポートなし。**',
        '実機の仕上がりは未確認です。最初は05のカメもどき、または01を1体刷って細部を確認できます。',
        '', '## 印刷ファイル', '',
        '- `print/*.gcode.3mf`：スライス済み。印刷内容を確認して送信するためのファイル。',
        '- `project/*.3mf`：Bambu Studioで開いて配置・素材設定などを調整できるプロジェクト。',
        '- `stl/*.stl`：形状データ。変更する場合は再スライスします。',
        '- `00_all_six`：6体を1枚のプレートに配置。造形は層ごとにまとめて行います。',
        '- `examples_overview.png` / `catalog.html`：見本一覧。`recipes/`には組み合わせを保存。',
        '', '時間はスライサー見積もりです。準備込みはプリンターの準備を含み、冷却・取り外しは別です。各1体の造形5分以内を目標に、必要に応じて32 mmから25 mmまで自動縮小しました。',
        '', '|番号|作例|最大寸法|造形|準備込み|PLA|', '|---|---|---:|---:|---:|---:|']
    for r in records:lines.append(f"|{r['number']:02d}|{r['name']}|{max(r['geometry']['dimensions_mm']):.1f} mm|{duration(r['model_seconds'])}|{duration(r['total_seconds'])}|{r['grams']:.1f} g|")
    lines+=['',f"**6体まとめ刷り：造形{duration(batch['model_seconds'])} / 準備込み{duration(batch['total_seconds'])} / PLA {batch['grams']:.1f} g。**",'', '## 各作例の選択', '']
    for r in records:lines.append(f"- {r['number']:02d} {r['name']}："+' / '.join(r['parts'].values()))
    lines+=['','この作業ではプリンターへ送信していません。ファイル作成・モデル検査・オフラインスライスまで確認済みです。']
    with (OUT/'README_印刷手順.md').open('x') as f:f.write('\n'.join(lines)+'\n')
    cards=[]
    for r in records:
        text=' / '.join(r['parts'].values())
        cards.append(f'<article><img src="{r["preview"]}"><h2>{r["number"]:02d} {html.escape(r["name"])}</h2><p>{html.escape(text)}</p><small>約{max(r["geometry"]["dimensions_mm"]):.0f} mm · 造形{duration(r["model_seconds"])} · PLA {r["grams"]:.1f} g</small></article>')
    with (OUT/'catalog.html').open('x') as f:f.write('<!doctype html><html lang="ja"><meta charset="utf-8"><title>展示作例 — へんてこ生物研究所</title><style>body{font-family:sans-serif;background:#f6f5ef;color:#253b35;margin:24px}h1{font-size:24px}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:20px}article{background:#fffefa;padding:16px;border:1px solid #dce4d6;border-radius:18px;break-inside:avoid}img{width:100%;height:210px;object-fit:contain}h2{font-size:19px}p{font-size:12px;line-height:1.8}small{font-size:12px;color:#5e745c}@page{size:A4 landscape;margin:10mm}@media print{body{margin:0}h1{font-size:18px}.grid{gap:9px}article{padding:9px}img{height:145px}h2{font-size:16px;margin:6px 0}p{margin:6px 0}}</style><h1>へんてこ生物研究所 — 作例6種類</h1><div class="grid">'+''.join(cards)+'</div></html>')
    with (OUT/'note.txt').open('a') as f:f.write('Completed all6 closed single-volume meshes, automatic1-3 eyes and configured parts, individual standard slices, and one plate containing6 disjoint closed bodies within15..165mm. All print packages verify0.6/A1mini/.30/support OFF/M220 S100. Manifest contains output SHA256; local output copies checksum-verified. No physical print/network submission.\n')
    with zipfile.ZipFile(ZIP,'x',zipfile.ZIP_DEFLATED) as z:
        for p in OUT.rglob('*'):
            if p.is_file() and '_work' not in p.relative_to(OUT).parts and p.name!='run.log':z.write(p,Path(OUT.name)/p.relative_to(OUT))
    print('EXHIBIT_PACKAGE_COMPLETE',str(OUT),str(ZIP),ZIP.stat().st_size,flush=True)

if __name__=='__main__':main()
