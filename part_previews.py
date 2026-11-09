"""Choice-card geometry: isolated parts, without a dragon or other torso.

These are illustrations assembled from the same CAD primitives as the print
model. Disconnected feet are intentional; these meshes are not print jobs.
"""
import numpy as np
import trimesh as tm
import geometry

GROUPS={'head','limbs','tail','eyes','expression'}
VIEWS={'head':'head','limbs':'limbs','tail':'part_tail','eyes':'eyes','expression':'face'}

def display_config(value,group):
    if group not in GROUPS:raise ValueError(group)
    # A neutral host supplies attachment spacing/surface normals only. Its
    # body is always excluded from the displayed part mesh.
    config=geometry.catalog()['default_config']|dict(body='axolotl',head='round',limbs='none',back='smooth',tail='none',
        texture='plain',eyes='two',expression='smile',size=34,roundness=1,tail_length=1,eye_size=1)
    config[group]=value[group]
    return geometry.normalize_config(config)

def _mesh(value,group):
    config=display_config(value,group)
    counts={'paws':4,'six':6,'eight':8,'flippers':4,'tentacles':8,'none':0}
    meta=dict(scope={'head':'isolated head and its face; no animal torso',
        'limbs':'isolated actual legs/arms only; no body, head, wings or tail',
        'tail':'isolated actual tail only; no body, head, limbs or wings',
        'eyes':'isolated actual eyes and pupil grooves only; no head or torso',
        'expression':'plain neutral face illustrating the actual mouth; no animal torso or ornaments'}[group],
        host_visible=False,view=VIEWS[group])
    if group in ('limbs','tail') and config[group]=='none':
        return None,meta|dict(scope='absence symbol; no animal geometry',anatomical_part_count=0)
    parts,cuts,head=geometry._anatomy(config)
    scale=config['size']/max(tm.boolean.union(parts,engine='manifold').extents[:2])
    selected=[];selected_cuts=[]
    if group in ('limbs','tail'):
        baseline=geometry._anatomy(config|{group:'none'})
        selected=parts[len(baseline[0]):]
        selected_cuts=cuts[len(baseline[1]):]
        assert selected and len(baseline[0])==2
        meta['anatomical_part_count']=counts[config[group]] if group=='limbs' else 1
        for part in selected:part.apply_scale(scale)
        for cut in selected_cuts:cut.apply_scale(scale)
    else:
        for part in parts:part.apply_scale(scale)
        eyes,face_cuts,layout=geometry._auto_face(head,config)
        if group=='eyes':
            count=layout['eye_count'];selected=eyes[:count];selected_cuts=face_cuts[:count]
            meta['anatomical_part_count']=count
        else:
            # Neutral anatomy has exactly the torso, then head and optional
            # ear/horn primitives; all other categories were disabled above.
            selected=parts[1:]+eyes;selected_cuts=face_cuts
            meta['anatomical_part_count']=1
        meta['face_layout']=layout
    result=tm.boolean.union(selected,engine='manifold')
    if selected_cuts:result=tm.boolean.difference([result,tm.boolean.union(selected_cuts,engine='manifold')],engine='manifold')
    assert len(result.faces)>0 and np.isfinite(result.vertices).all()
    return result,meta

def mesh(value,group):
    # Empty Boolean intersections in the face-clearance check have no centroid.
    with np.errstate(invalid='ignore',divide='ignore'):
        return _mesh(value,group)
