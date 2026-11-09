"""Validate visible two-fang geometry at the smallest app size and stage previews."""
from pathlib import Path
import json,time
import trimesh as tm
from PIL import Image,ImageDraw,ImageFont
import geometry,workshop,part_previews,generate_thumbnails as renderer,slicer

ROOT=Path(__file__).resolve().parent;OUT=ROOT/'runtime/fangs_v2_20261107'

def main():
    OUT.mkdir(exist_ok=False);records=[]
    for expression in ['smile','fangs']:
        cfg=part_previews.display_config({'expression':expression},'expression')
        full=geometry.generate(cfg,OUT/(expression+'_source.stl'))
        mesh,meta=part_previews.mesh(cfg,'expression')
        renderer.render(mesh,full,OUT/(expression+'.png'),'face',minimum_coverage=.015,contact_shadow=False)
        with (OUT/(expression+'_source.json')).open('x') as f:json.dump(full,f,ensure_ascii=False,indent=2)
    sheet=Image.new('RGB',(640,310),(246,245,239));draw=ImageDraw.Draw(sheet)
    font=ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf',18)
    for i,expression in enumerate(['smile','fangs']):
        img=Image.open(OUT/(expression+'.png'));sheet.paste(img,(i*320,0),img);draw.text((i*320+15,220),expression,font=font,fill=(37,59,53))
        small=img.resize((86,59),Image.Resampling.LANCZOS);sheet.paste(small,(i*320+120,248),small)
    sheet.save(OUT/'smile_fangs_comparison.png');print('FANGS_COMPARISON_READY',flush=True)
    for body in ['axolotl','dragon']:
        for option in geometry.catalog()['groups'][1]['options']:
            for eyes in ['one','two','three']:
                cfg=geometry.normalize_config(dict(body=body,head=option['id'],eyes=eyes,expression='fangs',size=25,back='smooth',texture='plain',tail='none',limbs='paws',eye_size=1.15))
                name=body+'_'+option['id']+'_'+eyes;result=geometry.generate(cfg,OUT/(name+'.stl'));layout=result['face_layout']
                assert layout['fang_count']==2 and layout['eye_mouth_clearance_mm']>=.45
                assert all(t['base_width_mm']>=1.3-.0001 and t['attachment_volume_mm3']>=.12 for t in layout['fangs'])
                mesh=tm.load_mesh(OUT/(name+'.stl'));assert mesh.is_volume and mesh.is_watertight and len(mesh.split())==1
                records.append(dict(name=name,fangs=layout['fangs'],eye_mouth_clearance_mm=layout['eye_mouth_clearance_mm']))
                print('MINIMUM_SIZE_FANGS_PASS',name,flush=True)
    # A real standard slice proves these are the actual printable features.
    cfg=workshop.automatic_config(geometry.catalog()['presets'][-1]['config']|dict(head='wide',limbs='paws',tail='fork',eyes='three',expression='fangs'))
    model=geometry.generate(cfg,OUT/'print_example.stl');result=slicer.slice_model(OUT/'print_example.stl',OUT/'print_slice','0.6','standard')
    with (OUT/'validation.json').open('x') as f:json.dump(dict(cases=records,print_model=model,slice=result),f,ensure_ascii=False,indent=2)
    print('FANGS_MINIMUM_CASES_AND_STANDARD_SLICE_PASS',len(records),result['model_seconds'],result['total_seconds'],flush=True)

if __name__=='__main__':main()
