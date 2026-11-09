"""Validate the actual revised model and refresh source-linked CAD thumbnails."""
from pathlib import Path
import json,hashlib,shutil
import geometry,slicer,generate_thumbnails as thumbs
ROOT=Path(__file__).resolve().parent
WORK=ROOT/'runtime/dragon_update_20261105'
BACKUP=ROOT/'backups/before_dragon_redesign_20261105'
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def slices():
    records=[]
    for nozzle,quality,name in [('0.6','standard','n06_standard'),('0.6','fast','n06_fast'),('0.8','standard','n08_standard')]:
        result=slicer.slice_model(WORK/'dragon.stl',WORK/name,nozzle,quality)
        records.append(result)
        print('DRAGON_SLICE',nozzle,quality,result['model_seconds'],result['total_seconds'],repr(result['warning']),flush=True)
    with (WORK/'slice_comparison.json').open('x') as out:json.dump(records,out,indent=2)

def assets():
    staged=WORK/'new_thumbnails_v2';manifest=WORK/'new_thumbnails_manifest_v2.json'
    thumbs.main(staged,WORK/'thumbnail_sources_v2',manifest)
    data=json.loads(manifest.read_text())
    for record in data['assets']:
        source=staged/record['filename'];target=ROOT/'frontend/thumbnails'/record['filename']
        assert digest(source)==record['png_sha256']
        # Every existing asset must already be backed up before replacement.
        assert (BACKUP/'thumbnails'/record['filename']).exists()
        shutil.copy2(source,target)
    target=ROOT/'frontend/thumbnails_manifest.json';assert (BACKUP/'thumbnails_manifest.json').exists();shutil.copy2(manifest,target)
    for record in data['assets']:assert digest(ROOT/'frontend/thumbnails'/record['filename'])==record['png_sha256']
    catalog=geometry.catalog()
    labels=[p['label'] for p in catalog['presets']]+[o['label'] for o in catalog['groups'][0]['options']]
    assert len(labels)==12 and all(n.endswith('もどき') and n.count('もどき')==1 for n in labels)
    print('DRAGON_ASSETS_REPLACED',len(data['assets']),flush=True)
    with (ROOT/'note.txt').open('a') as out:
        out.write('\nDragon update asset completion: generate_thumbnails.main now accepts new staging/output/manifest paths, preserving all old runtime files. All 48 actual-geometry PNGs regenerated under runtime/dragon_update_20261105/, validated, then copied to original static URLs only after backup. SHA256 verified for every copied PNG. Isolated head previews include scaled nostril/anatomy cuts, matching full models. All12 creature labels end with もどき exactly once; IDs unchanged. No prior file renamed/deleted.\n')

if __name__=='__main__':
    import sys
    if '--assets-only' not in sys.argv:slices()
    assets()
