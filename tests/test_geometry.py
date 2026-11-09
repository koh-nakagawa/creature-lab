"""Meaningful mesh/face regression checks; run with existing CAD Python."""
from pathlib import Path
import sys,json,time,random
import trimesh as tm
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import geometry


def run(destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=False)
    cases=[(p['id'],p['config']) for p in geometry.catalog()['presets']]
    # Cross archetype/part boundaries and exercise three-eye placement/large head.
    cases += [('cross_one',{'body':'slug','head':'wide','limbs':'eight','tail':'fan','back':'spines','texture':'dots','eyes':'three'}),
              ('cross_two',{'body':'turtle','head':'flat','limbs':'tentacles','tail':'curl','back':'gills','eyes':'one','expression':'surprise'}),
              ('cross_three',{'body':'dragon','head':'long','limbs':'six','tail':'club','back':'plates','texture':'scales','eye_size':1.15})]
    rng=random.Random(1105)
    for i in range(12):
        config={group['key']:rng.choice(group['options'])['id'] for group in geometry.catalog()['groups']}
        config.update(size=rng.choice([28,34,38]),roundness=rng.choice([.85,1,1.15]),eye_size=rng.choice([.85,1,1.15]),tail_length=rng.choice([.7,1,1.3]))
        cases.append(('random_'+str(i+1),config))
    records=[]
    for name,config in cases:
        started=time.monotonic();result=geometry.generate(config,destination/(name+'.stl'))
        mesh=tm.load_mesh(destination/(name+'.stl'))
        assert mesh.is_watertight and mesh.is_volume and len(mesh.split())==1
        assert result['face_layout']['eye_count']==len(result['face_layout']['eyes'])
        assert result['face_layout']['eye_mouth_clearance_mm']>=.45
        assert max(mesh.extents[:2])<=result['config']['size']+.1
        records.append({'case':name,'seconds':round(time.monotonic()-started,3),'geometry':result['geometry']})
        print('GEOMETRY_PASS',name,records[-1]['seconds'],flush=True)
    with (destination/'report.json').open('x') as f:json.dump(records,f,indent=2)
    try:geometry.generate({},destination/(cases[0][0]+'.stl'))
    except FileExistsError:pass
    else:raise AssertionError('Existing output was overwritten')
    print('ALL_GEOMETRY_TESTS_PASSED',flush=True)


if __name__=='__main__':run(sys.argv[1])
