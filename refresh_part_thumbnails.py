"""Render the 25 current part choices, validate, then replace backed-up PNGs."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import json,time
from PIL import Image,ImageDraw,ImageFont
import trimesh as tm
import geometry,part_previews,generate_thumbnails as renderer

ROOT=Path(__file__).resolve().parent
WORK=ROOT/'runtime/isolated_parts_20261106'

def main(work=WORK):
    global WORK
    WORK=Path(work).resolve()
    WORK.mkdir(exist_ok=False);stage=WORK/'images';stage.mkdir();sources=WORK/'source';sources.mkdir()
    manifest_path=ROOT/'frontend/thumbnails_manifest.json';manifest=json.loads(manifest_path.read_text())
    records=[];cache={};started=time.monotonic()
    for record in manifest['assets']:
        group=record.get('group')
        if group not in part_previews.GROUPS:continue
        config,key=renderer.canonical(part_previews.display_config(record['config'],group))
        if key not in cache:
            source=sources/(record['id']+'.stl');result=geometry.generate(config,source)
            with source.with_suffix('.json').open('x') as out:json.dump(result,out,ensure_ascii=False,indent=2)
            cache[key]=(source,result)
        source,result=cache[key]
        mesh,scope=part_previews.mesh(config,group);destination=stage/record['filename']
        if mesh is None:rendered=renderer.render_absence(destination)
        else:
            isolated=sources/(record['id']+'_isolated.stl')
            with isolated.open('xb') as out:out.write(tm.exchange.stl.export_stl(mesh))
            rendered=renderer.render(mesh,result,destination,scope['view'],minimum_coverage=.015,contact_shadow=False)
            rendered.update(preview_stl=str(isolated),preview_stl_sha256=renderer.digest(isolated),
                preview_dimensions_mm=mesh.extents.tolist(),preview_components=len(mesh.split(only_watertight=False)))
        rendered.update({k:v for k,v in scope.items() if k not in ('face_layout','view')})
        updated=record|dict(config=config,config_sha256=key,source_stl=str(source),stl_sha256=renderer.digest(source),
            dimensions_mm=result['geometry']['dimensions_mm'],png_sha256=renderer.digest(destination),render=rendered)
        records.append(updated)
        print('ISOLATED_PART_READY',record['id'],rendered['scope'],flush=True)
    assert len(records)==25
    # A contact sheet of all feet and tails makes torso/wings contamination easy to inspect.
    chosen=[r for r in records if r['group'] in ('limbs','tail')]
    sheet=Image.new('RGB',(960,1000),(246,248,241));draw=ImageDraw.Draw(sheet)
    font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',20)
    for i,record in enumerate(chosen):
        picture=Image.open(stage/record['filename']);x=i%3*320;y=i//3*250
        sheet.paste(picture,(x,y),picture);draw.text((x+15,y+220),record['id'],font=font,fill=(37,59,53))
    sheet.save(WORK/'limbs_tails_contact_sheet.png')
    sheet2=Image.new('RGB',(960,1250),(246,248,241));draw2=ImageDraw.Draw(sheet2)
    for i,record in enumerate(r for r in records if r['group'] not in ('limbs','tail')):
        picture=Image.open(stage/record['filename']);x=i%3*320;y=i//3*250
        sheet2.paste(picture,(x,y),picture);draw2.text((x+15,y+220),record['id'],font=font,fill=(37,59,53))
    sheet2.save(WORK/'head_eyes_expressions_contact_sheet.png')
    # Stage every asset and manifest first; installation is a separate reviewed step.
    byid={r['id']:r for r in records};manifest['assets']=[byid.get(r['id'],r) for r in manifest['assets']]
    manifest.update(part_only_updated_at=datetime.now(ZoneInfo('Asia/Tokyo')).isoformat(),
        part_only_groups=sorted(part_previews.GROUPS),part_only_asset_count=len(records),
        unique_source_models=len({r['source_stl'] for r in manifest['assets']}),
        part_only_elapsed_seconds=round(time.monotonic()-started,2))
    with (WORK/'thumbnails_manifest.json').open('x') as out:json.dump(manifest,out,ensure_ascii=False,indent=2)
    print('ISOLATED_PARTS_STAGED',len(records),'seconds',round(time.monotonic()-started,2),flush=True)

if __name__=='__main__':main()
