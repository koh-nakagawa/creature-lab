"""Render local, actual Creature Lab meshes into transparent choice thumbnails.

No external imagery or generative image model is used. Presets are emitted
first. Every asset records its exact configuration and source STL checksum.
Existing files are preserved; run once in a new task-owned output directory.
"""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import json
import shutil
import sys
import time
import numpy as np
from PIL import Image,ImageDraw,ImageFilter,ImageFont
import trimesh as tm
import geometry
import part_previews

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'frontend/thumbnails'
WORK=ROOT/'runtime/thumbnail_assets_20261105'
SIZE=(320,220)
SUPERSAMPLE=2
CAMERAS={
    'full':(.32,-.65,.70),
    'face':(.08,-.75,.66),
    'head':(.22,-.66,.72),
    'tail':(.38,.64,.67),
    'back':(.34,.20,.92),
    'texture':(.18,-.12,.98),
    'limbs':(.25,-.24,.94),
    'eyes':(.08,-.75,.66),
    'part_tail':(.10,.14,.985),
}


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(config):
    config=geometry.normalize_config(config)
    encoded=json.dumps(config,sort_keys=True,separators=(',',':')).encode()
    return config,hashlib.sha256(encoded).hexdigest()


def focus_vertices(mesh,result,view):
    if view!='face':return mesh.vertices
    bounds=np.asarray(result['face_layout']['head_bounds_local'],dtype=float)
    # HeadSurface's right/forward/up frame is (+X,-Y,+Z) for these generated assets.
    xmin,xmax=bounds[0,0],bounds[1,0]
    ymin,ymax=-bounds[1,1],-bounds[0,1]
    zmin,zmax=bounds[0,2],bounds[1,2]
    center_y=(ymin+ymax)/2
    if view=='face':
        xmin*=.90;xmax*=.90
        ymax=center_y+(ymax-ymin)*.08
    else:
        xmin-=1.3;xmax+=1.3;ymax-=.3;zmax+=1.8
    selected=mesh.vertices[
        (mesh.vertices[:,0]>=xmin-.5)&(mesh.vertices[:,0]<=xmax+.5)&
        (mesh.vertices[:,1]>=ymin-.6)&(mesh.vertices[:,1]<=ymax)&
        (mesh.vertices[:,2]>=zmin)&(mesh.vertices[:,2]<=zmax+.6)]
    return selected if len(selected)>10 else mesh.vertices


def render(mesh,result,destination,view='full',minimum_coverage=.10,contact_shadow=True):
    width,height=[v*SUPERSAMPLE for v in SIZE]
    camera=np.asarray(CAMERAS[view],dtype=float);camera/=np.linalg.norm(camera)
    right=np.cross([0,0,1],camera);right/=np.linalg.norm(right)
    up=np.cross(camera,right)
    matrix=np.array([right,-up,camera])
    vertices=mesh.vertices@matrix.T
    focused=focus_vertices(mesh,result,view)@matrix.T
    low,high=focused[:,:2].min(axis=0),focused[:,:2].max(axis=0)
    midpoint=(low+high)/2
    scale=min((width-36*SUPERSAMPLE)/(high[0]-low[0]),(height-30*SUPERSAMPLE)/(high[1]-low[1]))
    if view=='head':scale*=.94  # Head-only part preview preserves ear/horn silhouettes.
    center=np.array([width/2,height/2-3*SUPERSAMPLE])
    canvas=Image.new('RGBA',(width,height),(0,0,0,0))
    if contact_shadow and view not in ['face','head']:
        # Soft contact shadow is transparent outside its small grounded area.
        shadow=Image.new('RGBA',canvas.size,(0,0,0,0));draw=ImageDraw.Draw(shadow)
        ground=mesh.vertices[mesh.vertices[:,2]<.12]@matrix.T
        if len(ground):
            pixels=(ground[:,:2]-midpoint)*scale+center
            x0,y0=pixels.min(axis=0);x1,y1=pixels.max(axis=0)
            margin=4*SUPERSAMPLE
            draw.ellipse((x0-margin,y0+margin,x1+margin,y1+margin),fill=(19,60,47,36))
            canvas=Image.alpha_composite(canvas,shadow.filter(ImageFilter.GaussianBlur(5*SUPERSAMPLE)))
    draw=ImageDraw.Draw(canvas)
    face_vertices=vertices[mesh.faces]
    depths=face_vertices[:,:,2].mean(axis=1)
    light=np.array([-.42,-.68,1.0]);light/=np.linalg.norm(light)
    # Constant mint material; anatomy comes only from the source geometry.
    base=np.array([91,184,155],dtype=float)
    normals=mesh.face_normals
    for face_index in np.argsort(depths):
        normal=normals[face_index]
        if np.dot(normal,camera)<-.005:continue
        screen=(face_vertices[face_index,:,:2]-midpoint)*scale+center
        if screen[:,0].max()<0 or screen[:,0].min()>width or screen[:,1].max()<0 or screen[:,1].min()>height:continue
        diffuse=max(0.,float(np.dot(normal,light)))
        shade=.42+.58*diffuse
        rgb=np.clip(base*shade,0,255).astype(int)
        draw.polygon([tuple(p) for p in screen],fill=(*rgb.tolist(),255))
    canvas=canvas.resize(SIZE,Image.Resampling.LANCZOS)
    alpha=np.asarray(canvas.getchannel('A'))
    assert alpha.max()==255 and np.count_nonzero(alpha)>SIZE[0]*SIZE[1]*minimum_coverage
    assert np.count_nonzero(alpha==0)>SIZE[0]*SIZE[1]*.05
    if destination.exists():raise FileExistsError(destination)
    canvas.save(destination)
    return dict(size=list(SIZE),view=view,camera=camera.tolist(),alpha_occupied_pixels=int(np.count_nonzero(alpha)))


def render_absence(destination):
    """A code-drawn absence mark; never show a creature for 'no part'."""
    canvas=Image.new('RGBA',(640,440),(0,0,0,0));draw=ImageDraw.Draw(canvas)
    draw.ellipse((225,100,415,290),outline=(93,135,112,230),width=14)
    draw.line((252,263,388,127),fill=(93,135,112,230),width=14)
    canvas=canvas.resize(SIZE,Image.Resampling.LANCZOS)
    if destination.exists():raise FileExistsError(destination)
    canvas.save(destination)
    return dict(size=list(SIZE),view='absence',scope='absence symbol; no geometry')


def head_preview_mesh(config):
    """Plain isolated head/face, independent of a dragon or other torso."""
    preview,_=part_previews.mesh(config,'head')
    return preview


def contact_sheet(records,destination):
    cellw,cellh=320,250
    sheet=Image.new('RGB',(cellw*3,cellh*2),(245,248,246))
    draw=ImageDraw.Draw(sheet)
    font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',19)
    for index,record in enumerate(records):
        thumb=Image.open(OUT/record['filename'])
        x=(index%3)*cellw;y=(index//3)*cellh
        sheet.paste(thumb,(x,y),thumb)
        draw.text((x+12,y+221),record['id'],font=font,fill=(27,57,45))
    if destination.exists():raise FileExistsError(destination)
    sheet.save(destination)


def main(output=None,work=None,manifest_destination=None):
    global OUT,WORK
    if output is not None:OUT=Path(output)
    if work is not None:WORK=Path(work)
    started=time.monotonic()
    OUT.mkdir(exist_ok=False)
    WORK.mkdir(exist_ok=False)
    catalog=geometry.catalog();cache={};records=[]
    presets={p['id']:p for p in catalog['presets']}

    def asset(id,config,view,kind,group=None,option=None):
        if group in part_previews.GROUPS:config=part_previews.display_config(config,group)
        normalized,key=canonical(config)
        if key not in cache:
            path=WORK/(id+'.stl')
            result=geometry.generate(normalized,path)
            meta_path=WORK/(id+'.json')
            with meta_path.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
            cache[key]=(path,result)
        source,result=cache[key]
        filename=id+'.png';destination=OUT/filename
        if group in part_previews.GROUPS:
            thumbnail_mesh,scope=part_previews.mesh(normalized,group)
            view=scope['view']
            rendered=render_absence(destination) if thumbnail_mesh is None else render(thumbnail_mesh,result,destination,view,minimum_coverage=.015,contact_shadow=False)
            if thumbnail_mesh is not None:
                preview_stl=WORK/(id+'_isolated.stl')
                with preview_stl.open('xb') as out:out.write(tm.exchange.stl.export_stl(thumbnail_mesh))
                rendered.update(preview_stl=str(preview_stl),preview_stl_sha256=digest(preview_stl))
            rendered.update({k:v for k,v in scope.items() if k not in ('face_layout','view')})
        else:rendered=render(tm.load_mesh(source),result,destination,view)
        record=dict(id=id,kind=kind,group=group,option=option,filename=filename,url='/thumbnails/'+filename,
            config=normalized,config_sha256=key,source_stl=str(source),stl_sha256=digest(source),png_sha256=digest(destination),
            dimensions_mm=result['geometry']['dimensions_mm'],render=rendered)
        records.append(record)
        print('THUMBNAIL_READY',filename,rendered['view'],flush=True)

    for preset in catalog['presets']:
        asset('preset_'+preset['id'],preset['config'],'full','preset')
    contact_sheet(records,WORK/'presets_contact_sheet.png')
    print('PRESETS_READY',len(records),flush=True)

    for group in catalog['groups']:
        for option in group['options']:
            key=group['key']
            if key=='body':
                # Use the matching creature's canonical anatomy, never a dragon
                # with only its body switched (e.g. a slug must have no legs).
                config=presets[option['id']]['config']
            else:config=catalog['default_config']|{key:option['id']}
            view='head' if key=='head' else 'face' if key in ['eyes','expression'] else key if key in ['tail','back','texture','limbs'] else 'full'
            asset(key+'_'+option['id'],config,view,'option',key,option['id'])

    expected={'preset_'+p['id']+'.png' for p in catalog['presets']}
    expected|={g['key']+'_'+o['id']+'.png' for g in catalog['groups'] for o in g['options']}
    actual={p.name for p in OUT.glob('*.png')}
    assert actual==expected,(expected-actual,actual-expected)
    assert len(records)==48
    manifest=dict(version=1,generated_at=datetime.now(ZoneInfo('Asia/Tokyo')).isoformat(),renderer='CPU orthographic CAD triangles, constant mint material',
        source='geometry.generate + part_previews.mesh for isolated active-part choices; no external images or emoji',asset_count=len(records),unique_source_models=len(cache),
        width=SIZE[0],height=SIZE[1],elapsed_seconds=round(time.monotonic()-started,2),assets=records)
    manifest_path=Path(manifest_destination) if manifest_destination else ROOT/'frontend/thumbnails_manifest.json'
    with manifest_path.open('x') as f:json.dump(manifest,f,ensure_ascii=False,indent=2);f.write('\n')
    with (ROOT/'note.txt').open('a') as f:
        f.write('\nThumbnail assets completed '+manifest['generated_at']+'\n')
        f.write('Tool: existing CAD Python + geometry.generate + trimesh/Pillow CPU rendering; source generate_thumbnails.py. No imagegen, network, external image or emoji sources.\n')
        f.write('Inputs: current geometry.catalog presets/body matching full creature; head/limbs/tail/eyes/expression use part_previews.display_config and isolated actual geometry on a neutral host whose body is excluded. Back/texture retain full-creature examples. No-parts choices use an absence symbol.\n')
        f.write('Outputs: '+str(OUT)+' (48 RGBA,320x220), manifest '+str(manifest_path)+', source/isolated STL and preset contact sheet under '+str(WORK)+'. Unique source model count '+str(len(cache))+'.\n')
        f.write('Generator: generate_thumbnails.main(output,work,manifest_destination). All48 filenames validated; opaque preview/symbol pixels with transparent background. Elapsed '+str(manifest['elapsed_seconds'])+' s. Prior files preserved by exclusive output creation.\n')
    print('ALL_THUMBNAILS_COMPLETE',json.dumps({k:manifest[k] for k in ['asset_count','unique_source_models','elapsed_seconds']}),flush=True)


def refresh_heads():
    """Reframe existing head assets with backup and updated provenance."""
    manifest_path=ROOT/'frontend/thumbnails_manifest.json'
    manifest=json.loads(manifest_path.read_text())
    backup=ROOT/'backups/thumbnail_heads_before_isolation_20261105';backup.mkdir(exist_ok=False)
    shutil.copy2(manifest_path,backup/manifest_path.name)
    refreshed=[]
    for record in manifest['assets']:
        if record.get('group')!='head':continue
        target=OUT/record['filename'];shutil.copy2(target,backup/target.name)
        source=Path(record['source_stl'])
        result=json.loads(source.with_suffix('.json').read_text())
        with np.errstate(invalid='ignore',divide='ignore'):
            preview=head_preview_mesh(record['config'])
        preview_stl=WORK/(record['id']+'_isolated_head.stl')
        with preview_stl.open('xb') as f:f.write(tm.exchange.stl.export_stl(preview))
        rendered_png=WORK/(record['id']+'_isolated_head.png')
        rendered=render(preview,result,rendered_png,'head')
        rendered.update(scope='actual selected head, eyes, mouth and ear/horn geometry; torso excluded',
            preview_stl=str(preview_stl),preview_stl_sha256=digest(preview_stl))
        shutil.copy2(rendered_png,target)
        record.update(png_sha256=digest(target),render=rendered)
        refreshed.append(record['id'])
        print('HEAD_REFRAMED',record['filename'],flush=True)
    manifest['head_framing_updated_at']=datetime.now(ZoneInfo('Asia/Tokyo')).isoformat()
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    assert len(list(OUT.glob('*.png')))==48
    for record in manifest['assets']:
        assert digest(OUT/record['filename'])==record['png_sha256']
    with (ROOT/'note.txt').open('a') as f:
        f.write('\nHead thumbnail visual QA: full-creature crops allowed torso spines to hide head horns. New head_preview_mesh() renders the actual selected head/face/ear-or-horn primitives at the exact generated scale, excluding unrelated torso geometry. Source generator/catalog/name files unchanged.\n')
        f.write('Backups before overwrite: backups/thumbnail_heads_before_isolation_20261105/ stores original six head PNGs and manifest; source backup backups/generate_thumbnails_before_head_padding.py. New isolated-head preview STL/PNGs under runtime/thumbnail_assets_20261105/ retain provenance and SHA256 in the updated manifest. Only six head PNGs were replaced; all 48 image checksums revalidated. Command existing Python generate_thumbnails.py --refresh-heads in visible tmux thumbs.\n')
    print('ALL_HEAD_FRAMING_COMPLETE',len(refreshed),flush=True)


if __name__=='__main__':
    if '--refresh-heads' in sys.argv:refresh_heads()
    else:main()
