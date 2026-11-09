from pathlib import Path
import sys,json
R=Path(__file__).resolve().parent;APP=R.parent;sys.path.insert(0,str(APP))
import trimesh as tm
import generate_thumbnails as render
render.SIZE=(1800,1240);render.SUPERSAMPLE=1
for stem in ['01_dragon_modoki','03_octopus_modoki','05_turtle_modoki']:
 source=APP/'example_prints_fangs_v2_20261107'
 result=json.loads((source/'recipes'/f'{stem}.json').read_text())
 render.render(tm.load_mesh(source/'stl'/f'{stem}.stl'),result,R/'assets'/f'{stem}.png','full')
 print('HIGH_RES_READY',stem,flush=True)
