"""Procedural, combinatorial printable creature geometry for Creature Lab.

All options generate real joined geometry.  Head metadata is supplied by the
generator, while face anchors and orientation are solved from its skin mesh.
No printer credentials or network actions belong in this module.
"""
from __future__ import annotations
from pathlib import Path
import copy
import hashlib
import json
import math
import sys
import time
import numpy as np
import trimesh as tm
import manifold3d as manifold
from shapely.geometry import Polygon

ROOT=Path(__file__).resolve().parent
MODEL_REVISION='20261107_fangs_v2'
sys.path.insert(0,str(ROOT/'geometry_support'))
from face_placement import HeadSurface, orient
from mesh_cleanup import clean


def _clean_mesh(mesh):
    # Manifold can encode a collinear face at a planar T-junction. Removing that
    # face creates an artificial topological hole although its area is zero.
    # Prefer its already-watertight topology, including STL quantization; use
    # the prior precision repair only if the round-trip topology needs it.
    candidate=mesh.copy()
    candidate.vertices=np.asarray(candidate.vertices,dtype=np.float32).astype(float)
    candidate.process(validate=False)
    if candidate.is_volume and candidate.is_watertight and len(candidate.split())==1:
        return candidate,dict(mode='preserve_manifold_topology',volume_delta_mm3=float(candidate.volume-mesh.volume),
                              zero_area_faces=int(np.sum(candidate.area_faces<1e-12)))
    if mesh.is_volume and mesh.is_watertight and len(mesh.split())==1:
        # Contract sub-micron Boolean slivers inside the geometry kernel before
        # STL float32 rounding can collapse them into open edges. The maximum
        # surface movement is far below any printable feature.
        solid=manifold.Manifold(manifold.Mesh64(vert_properties=np.asarray(mesh.vertices,dtype=np.float64),
                                               tri_verts=np.asarray(mesh.faces,dtype=np.uint64)))
        for tolerance in [1e-5,1e-4]:
            data=solid.simplify(tolerance).to_mesh64()
            simplified=tm.Trimesh(vertices=np.asarray(data.vert_properties)[:,:3],faces=data.tri_verts,process=False)
            simplified.vertices=np.asarray(simplified.vertices,dtype=np.float32).astype(float)
            simplified.process(validate=False)
            if not simplified.is_watertight:
                simplified.process(validate=True)
                tm.repair.fill_holes(simplified)
            if simplified.is_volume and simplified.is_watertight and len(simplified.split())==1:
                delta=float(simplified.volume-mesh.volume)
                if abs(delta)<.04:
                    return simplified,dict(mode='kernel_precision_simplification',tolerance_mm=tolerance,volume_delta_mm3=delta)
    try:
        return clean(mesh)
    except ValueError:
        # STL welding can remove zero-area closure faces at planar T-junctions.
        # Restore only triangular holes with mathematically zero area. This
        # changes topology, not the rendered/printed surface or volume.
        for digits in [None,7,6,5,4]:
            candidate=mesh.copy();candidate.vertices=np.asarray(candidate.vertices,dtype=np.float32).astype(float)
            if digits is not None:candidate.merge_vertices(digits_vertex=digits)
            candidate.process(validate=True);tm.repair.fill_holes(candidate)
            pieces=candidate.split(only_watertight=False)
            solids=[p for p in pieces if abs(p.volume)>1e-7]
            fragments=[p for p in pieces if abs(p.volume)<=1e-7]
            if len(solids)==1 and all(np.ptp(p.vertices[:,2])<1e-5 and abs(p.volume)<1e-7 for p in fragments):
                candidate=solids[0]
            edges=candidate.edges
            _,inverse,counts=np.unique(np.sort(edges,axis=1),axis=0,return_inverse=True,return_counts=True)
            boundary=edges[counts[inverse]==1]
            graph={}
            for a,b in boundary:
                graph.setdefault(int(a),set()).add(int(b));graph.setdefault(int(b),set()).add(int(a))
            remaining=set(graph);patches=[]
            while remaining:
                stack=[remaining.pop()];component=set(stack)
                while stack:
                    for n in graph[stack.pop()]-component:
                        component.add(n);remaining.discard(n);stack.append(n)
                if len(component)<3 or any(len(graph[x])!=2 for x in component):continue
                a,b=next((int(a),int(b)) for a,b in boundary if int(a) in component)
                loop=[a,b]
                while len(loop)<len(component):
                    following=graph[loop[-1]]-{loop[-2]}
                    nxt=next(iter(following))
                    if nxt in loop:break
                    loop.append(nxt)
                if len(loop)!=len(component):continue
                triangles=[[loop[0],loop[j+1],loop[j]] for j in range(1,len(loop)-1)]
                points=candidate.vertices[np.asarray(triangles)]
                area=float(np.sum(np.linalg.norm(np.cross(points[:,1]-points[:,0],points[:,2]-points[:,0]),axis=1))*.5)
                if area<1e-5:patches.extend(triangles)
            if patches:
                candidate=tm.Trimesh(vertices=candidate.vertices,faces=np.vstack([candidate.faces,patches]),process=False)
            if candidate.is_volume and candidate.is_watertight and len(candidate.split())==1:
                return candidate,dict(mode='flat_closure_repair',weld_digits=digits,flat_closure_faces=len(patches),
                    volume_delta_mm3=float(candidate.volume-mesh.volume))
        raise


def _option(id,label,hint=''):
    return dict(id=id,label=label,hint=hint)


_GROUPS=[
 dict(key='body',label='からだ',default='dragon',options=[_option('dragon','ドラゴンもどき'),_option('armored','ダンゴムシもどき'),_option('octopus','タコもどき'),_option('slug','ナメクジもどき'),_option('turtle','カメもどき'),_option('axolotl','ウーパールーパーもどき')]),
 dict(key='head',label='あたま',default='horns',options=[_option('round','まるがお'),_option('wide','よこなが'),_option('long','ながいかお'),_option('flat','ぺたんこ'),_option('ears','みみつき'),_option('horns','つのつき')]),
 dict(key='limbs',label='あし・うで',default='paws',options=[_option('paws','4ほんあし'),_option('six','6ぽんあし'),_option('eight','8ぽんあし'),_option('flippers','ひれ'),_option('tentacles','まきうで'),_option('none','あしなし')]),
 dict(key='back',label='せなか',default='spines',options=[_option('spines','とげ'),_option('plates','せびれ'),_option('gills','えら'),_option('bumps','こぶ'),_option('shell','こうら'),_option('smooth','つるつる')]),
 dict(key='tail',label='しっぽ',default='long',options=[_option('long','ながい'),_option('curl','くるん'),_option('fork','ふたまた'),_option('fan','おうぎ'),_option('club','こんぼう'),_option('none','しっぽなし')]),
 dict(key='texture',label='もよう',default='scales',options=[_option('plain','なめらか'),_option('dots','つぶつぶ'),_option('stripes','しましま'),_option('scales','うろこ'),_option('ridges','すじ')]),
 dict(key='eyes',label='め',default='two',options=[_option('one','1つめ'),_option('two','2つめ'),_option('three','3つめ')]),
 dict(key='expression',label='ひょうじょう',default='smile',options=[_option('smile','にっこり'),_option('surprise','びっくり'),_option('flat','まじめ'),_option('fangs','きば')]),
]
_PARAMETERS=[
 dict(key='size',label='おおきさ',min=25,max=40,step=1,default=34,unit='mm'),
 dict(key='roundness',label='ふっくら',min=.80,max=1.20,step=.05,default=1,unit=''),
 dict(key='tail_length',label='しっぽのながさ',min=.60,max=1.40,step=.10,default=1,unit=''),
 dict(key='eye_size',label='めのおおきさ',min=.80,max=1.15,step=.05,default=1,unit=''),
]
_DEFAULT={g['key']:g['default'] for g in _GROUPS}|{p['key']:p['default'] for p in _PARAMETERS}
_PRESETS=[
 dict(id='dragon',label='ドラゴンもどき',config={'body':'dragon','head':'horns','limbs':'paws','back':'spines','tail':'long','texture':'scales','eyes':'two','expression':'smile'}),
 dict(id='armored',label='ダンゴムシもどき',config={'body':'armored','head':'round','limbs':'eight','back':'shell','tail':'fork','texture':'dots','eyes':'two','expression':'smile'}),
 dict(id='octopus',label='タコもどき',config={'body':'octopus','head':'wide','limbs':'tentacles','back':'bumps','tail':'none','texture':'plain','eyes':'two','expression':'smile','size':30}),
 dict(id='slug',label='ナメクジもどき',config={'body':'slug','head':'horns','limbs':'none','back':'gills','tail':'curl','texture':'scales','eyes':'three','expression':'surprise'}),
 dict(id='turtle',label='カメもどき',config={'body':'turtle','head':'long','limbs':'flippers','back':'shell','tail':'club','texture':'stripes','eyes':'one','expression':'smile'}),
 dict(id='axolotl',label='ウーパールーパーもどき',config={'body':'axolotl','head':'ears','limbs':'six','back':'plates','tail':'fan','texture':'ridges','eyes':'two','expression':'fangs'}),
]


def catalog():
    return copy.deepcopy(dict(title='へんてこ生物研究所',version=1,groups=_GROUPS,parameters=_PARAMETERS,
        default_config=_DEFAULT,presets=[p|{'config':_DEFAULT|p['config']} for p in _PRESETS],
        model_revision=MODEL_REVISION,notes=['1体ずつ、実際の形状を生成します。','印刷時間はスライスして確認します。']))


def normalize_config(config):
    if not isinstance(config,dict):raise ValueError('config must be an object')
    unknown=set(config)-set(_DEFAULT)
    if unknown:raise ValueError('Unknown configuration keys: '+', '.join(sorted(unknown)))
    result=dict(_DEFAULT)
    for group in _GROUPS:
        key=group['key'];value=config.get(key,result[key])
        if value not in {o['id'] for o in group['options']}:raise ValueError('Unknown '+key+' option')
        result[key]=value
    for parameter in _PARAMETERS:
        key=parameter['key']
        try:value=float(config.get(key,result[key]))
        except (TypeError,ValueError):raise ValueError(key+' must be numeric')
        if not math.isfinite(value):raise ValueError(key+' must be finite')
        if not parameter['min']<=value<=parameter['max']:raise ValueError(key+' is outside allowed range')
        value=parameter['min']+round((value-parameter['min'])/parameter['step'])*parameter['step']
        result[key]=round(value,3)
    return result


def dome(x,y,rx,ry,h,z=0):
    mesh=tm.creation.uv_sphere(count=[20,32]);mesh.apply_scale([rx,ry,h])
    mesh=mesh.slice_plane([0,0,0],[0,0,1],cap=True);mesh.apply_translation([x,y,z]);return mesh


def sphere(radius,point):
    mesh=tm.creation.uv_sphere(radius=radius,count=[16,24]);mesh.apply_translation(point);return mesh


def capsule(a,b,width,height,z=0):
    a=np.array(a,dtype=float);b=np.array(b,dtype=float)
    mesh=dome(0,0,float(np.linalg.norm(b-a))/2+width/2,width/2,height,z)
    mesh.apply_transform(tm.transformations.rotation_matrix(math.atan2((b-a)[1],(b-a)[0]),[0,0,1]))
    mesh.apply_translation([*((a+b)/2),0]);return mesh


def cylinder(x,y,r,z0,z1):
    mesh=tm.creation.cylinder(radius=r,height=z1-z0,sections=28);mesh.apply_translation([x,y,(z0+z1)/2]);return mesh


def _surface_z(x,y,body):
    return body['h']*math.sqrt(max(.03,1-(x/body['rx'])**2-((y-body['cy'])/body['ry'])**2))


def _dragon_wings():
    """Low bat-wing membranes and ribs, all starting on the build plane."""
    pieces=[]
    outline=np.array([[4.6,-.7],[8.9,.8],[15.1,6.6],[11.2,5.4],
                      [13.5,10.1],[9.6,7.8],[10.1,11.9],[6.0,7.0],[4.6,3.0]])
    for side in [-1,1]:
        polygon=Polygon(outline*np.array([side,1])).buffer(.30,join_style=1)
        membrane=tm.creation.extrude_polygon(polygon,height=1.12,engine='manifold')
        pieces.append(membrane)
        root=np.array([side*4.8,-.3]);elbow=np.array([side*8.8,1.0])
        pieces.append(capsule(root,elbow,1.75,2.5))
        for tip in [(15.1,6.6),(13.5,10.1),(10.1,11.9)]:
            pieces.append(capsule(elbow,[side*tip[0],tip[1]],1.35,1.95))
        pieces.append(dome(side*5.5,.6,1.9,2.2,3.0))
    return pieces


def _anatomy(config):
    profiles={
      'dragon':(6.6,8.6,6.4,3),'armored':(7.4,9,6.7,3),
      'octopus':(7.0,7.3,7.2,2),'slug':(5.9,10.5,5.8,3.6),
      'turtle':(8.7,8.8,7.0,2.6),'axolotl':(6.3,8.9,5.9,3),
    }
    rx,ry,h,cy=profiles[config['body']];rx*=config['roundness']
    body=dict(rx=rx,ry=ry,h=h,cy=cy)
    parts=[dome(0,cy,rx,ry,h)];cuts=[]
    heads={'round':(7.7,6.2,7),'wide':(8.8,5.8,6.7),'long':(7.2,7.0,7.1),
           'flat':(8.2,6,5.8),'ears':(7.8,6.1,7),'horns':(7.8,6.1,7)}
    hx,hy,hh=heads[config['head']]
    head=dome(0,-5.8,hx,hy,hh)
    if config['body']=='dragon':
        # A projecting muzzle changes the real semantic head surface, so face
        # anchors automatically follow it rather than remaining on the skull.
        muzzle_y=-5.8-hy*.86
        muzzle=dome(0,muzzle_y,hx*.43,3.25,3.0)
        head=tm.boolean.union([head,muzzle],engine='manifold')
        for side in [-1,1]:cuts.append(cylinder(side*1.25,muzzle_y-.65,.64,1.45,hh+2))
    parts.append(head)
    if config['body']=='octopus':parts.append(dome(0,cy+4,4.4,5,7.1))
    if config['body']=='slug':parts.append(dome(0,cy+ry-1,3.2,4.3,3.5))
    if config['body']=='armored':
        for yy in [1,4.3,7.6,10.5]:
            cut=tm.creation.box(extents=[rx*2+3,1.25,12]);cut.apply_translation([0,yy,8]);cuts.append(cut)
    if config['head']=='ears':
        for side in [-1,1]:parts.append(dome(side*5,-2.3,2.3,2.4,3.5,3.9))
    elif config['head']=='horns':
        for side in [-1,1]:
            cone=tm.creation.cone(radius=1.7,height=4.1 if config['body']=='dragon' else 3,sections=28);cone.apply_translation([side*3.4,-2.6,4.7]);parts.append(cone)
    # Append intrinsic dragon wings after head ornaments; their semantic part
    # indices therefore remain compatible with isolated-head thumbnails.
    if config['body']=='dragon':parts.extend(_dragon_wings())
    limb=config['limbs']
    if limb in ['paws','six','eight']:
        count={'paws':2,'six':3,'eight':4}[limb]
        for side in [-1,1]:
            for yy in np.linspace(-1.5,cy+ry*.68,count):
                parts.append(capsule([side*rx*.63,yy],[side*(rx+2.7),yy-1.3],3.5 if limb=='paws' else 2.7,2.3))
    elif limb=='flippers':
        for side in [-1,1]:
            for yy in [-1.0,cy+ry*.6]:parts.append(capsule([side*rx*.6,yy],[side*(rx+3.5),yy-2],4.0,1.9))
    elif limb=='tentacles':
        for i,angle in enumerate(np.linspace(0,2*np.pi,8,endpoint=False)):
            radii=np.array([3.8,6,8.6,11.0,12.3,12.3])
            theta=angle+np.array([0,.02,.08,.23,.48,.80])*(-1 if i%2 else 1)
            xy=np.c_[radii*np.cos(theta),cy+radii*np.sin(theta)]
            for j in range(len(xy)-1):parts.append(capsule(xy[j],xy[j+1],3.6-.25*j,2.5-.16*j))
            for j in [3,4]:
                x,y=xy[j]
                if (x/hx)**2+((y+5.8)/hy)**2>1.18:
                    cuts.append(cylinder(x,y,.88,.85,18))
    if config['back']=='gills':
        for side in [-1,1]:
            for yy in [-7.9,-4.9,-1.9]:
                parts.append(capsule([side*(hx-2),yy],[side*(hx+4),yy-1.5],2.6,2.3))
                parts.append(capsule([side*(hx+1),yy-.6],[side*(hx+3),yy+1.0],2,1.8))
    elif config['back'] in ['spines','plates']:
        for yy in [1.2,4.4,7.6,10.0]:
            z=_surface_z(0,yy,body)-.7
            if config['back']=='spines':
                piece=tm.creation.cone(radius=1.5,height=3.0,sections=28);piece.apply_translation([0,yy,z]);parts.append(piece)
            else:parts.append(dome(0,yy,1.4,2.2,3.1,z))
    elif config['back']=='bumps':
        for side in [-1,1]:
            for yy in [1.5,4.6,7.7]:
                xx=side*rx*.35;parts.append(dome(xx,yy,1.6,1.6,1.8,_surface_z(xx,yy,body)-.75))
    elif config['back']=='shell':
        for yy in [1.5,5,8.5]:
            cut=tm.creation.box(extents=[rx*2+3,1.15,12]);cut.apply_translation([0,yy,8.6]);cuts.append(cut)
        for xx in [-rx*.3,rx*.3]:
            cut=tm.creation.box(extents=[1.0,ry*1.2,10]);cut.apply_translation([xx,cy+1,8.8]);cuts.append(cut)
    tail=config['tail'];length=6.0*config['tail_length'];start=cy+ry*.75
    if tail!='none':
        if tail=='long' and config['body']=='dragon':
            points=[[0,start],[.3,start+length*.35],[1.7,start+length*.75],
                    [3.2,start+length*1.15],[4.7,start+length*1.48]]
            for j in range(len(points)-1):
                parts.append(capsule(points[j],points[j+1],[4.0,3.25,2.45,1.7][j],[2.7,2.2,1.65,1.15][j]))
            tip=np.array(points[-1]);parts.append(dome(tip[0],tip[1],1.15,1.65,1.15))
        elif tail=='curl':
            pts=[[0,start],[0,start+2],[1.5,start+4],[4,start+4.4],[5.5,start+2.8],[4.6,start+1.2]]
            pts=np.array(pts);pts[:,1]=start+(pts[:,1]-start)*config['tail_length']
            for i in range(len(pts)-1):parts.append(capsule(pts[i],pts[i+1],3.6-.3*i,2.5-.2*i))
        else:
            parts.append(capsule([0,start],[0,start+length],3.8,2.5))
            end=start+length
            if tail=='long':parts.append(dome(0,end,1.8,3.0,1.6))
            elif tail=='fork':
                for side in [-1,1]:parts.append(capsule([0,end-1],[side*3.6,end+2.4],2.6,1.7))
            elif tail=='fan':
                for side in [-1,0,1]:parts.append(capsule([0,end-1],[side*3.7,end+2.6],3,1.7))
            elif tail=='club':parts.append(dome(0,end+1,3.1,3.5,2.8))
    texture=config['texture']
    if texture in ['dots','scales']:
        for side in [-1,1]:
            for yy in [1,4.3,7.6]:
                xx=side*rx*.42
                parts.append(dome(xx,yy,1.1 if texture=='dots' else 1.8,1.1 if texture=='dots' else 2.1,1.35,_surface_z(xx,yy,body)-.55))
    elif texture=='stripes':
        for yy in [2.8,6.2,9.6]:
            cut=tm.creation.box(extents=[rx*2+2,.85,10]);cut.apply_translation([0,yy,8.6]);cuts.append(cut)
    elif texture=='ridges':
        for xx in [-rx*.35,rx*.35]:
            low=min(_surface_z(xx,yy,body) for yy in [2,5,8])-.7
            parts.append(capsule([xx,2],[xx,8],1.7,2,low))
    return parts,cuts,head


def _auto_face(head,config):
    surface=HeadSurface(head)
    count={'one':1,'two':2,'three':3}[config['eyes']]
    nominal=min(surface.half[0]*(.29 if count==1 else .265 if count==2 else .205),surface.height*.30)
    nominal=float(np.clip(nominal*config['eye_size'],1.05 if count==3 else 1.35,2.6))
    radius_mouth=float(np.clip(surface.half[0]*.09,.55,.72))
    choices=[]
    for shrink in [1,.92,.84,.76]:
        radius=nominal*shrink
        eye_x=(np.arange(count)-(count-1)/2)*(2*radius+.62)
        normalized=eye_x/surface.half[0]
        if max(abs(normalized))>.70:continue
        for ev in [.30,.24,.36,.18]:
            try:eyes=[surface.project(float(u),ev) for u in normalized]
            except ValueError:continue
            if min(np.dot(p.normal,surface.up) for p in eyes)<.40:continue
            for mv in [.78,.84,.90,.72]:
                for mouth_width in ([.68,.60,.52] if config['expression']=='fangs' else [.50,.42,.34]):
                    try:
                        if config['expression']=='fangs':
                            path=[surface.project(mouth_width/2*math.cos(a),mv+.085*math.sin(a)) for a in np.linspace(0,2*np.pi,33)]
                        elif config['expression']=='surprise':
                            path=[surface.project(.13*math.cos(a),mv+.052*math.sin(a)) for a in np.linspace(0,2*np.pi,25)]
                        else:
                            curve=.055 if config['expression']!='flat' else 0
                            path=[surface.project(t*mouth_width/2,mv+curve*(1-t*t)) for t in np.linspace(-1,1,21)]
                    except ValueError:continue
                    if min(p.point[2] for p in path)<1.15:continue
                    gap=float('inf')
                    for eye in eyes:
                        for mouth in path:
                            delta=mouth.point-eye.point
                            tangent=np.linalg.norm(delta-eye.normal*np.dot(delta,eye.normal))
                            gap=min(gap,tangent-radius-radius_mouth)
                    if gap<.45:continue
                    score=10*(1-shrink)+abs(ev-.30)+abs(mv-.80)+((.68 if config['expression']=='fangs' else .50)-mouth_width)
                    choices.append((score,eyes,path,radius,gap,ev,mv,mouth_width))
        if choices:break
    if not choices:raise ValueError('この頭では顔が入りません。目を小さくするか、頭を大きくしてください。')
    _,eyes,path,radius,gap,ev,mv,mouth_width=min(choices,key=lambda x:x[0])
    height=float(np.clip(surface.height*.25,1.25,2.0));embed=max(.42,radius*.30)
    additions=[];cuts=[];details=[]
    for eye in eyes:
        origin=eye.point-eye.normal*embed
        eye_mesh=orient(dome(0,0,radius,radius,height),origin,eye.normal,surface.right)
        outer=cylinder(0,0,radius*.66,height*.54,height+1)
        inner=cylinder(0,0,radius*.33,height*.54-.1,height+1.1)
        ring=orient(tm.boolean.difference([outer,inner],engine='manifold'),origin,eye.normal,surface.right)
        attachment=tm.boolean.intersection([head,eye_mesh],engine='manifold')
        if attachment.volume<.12:raise ValueError('目と頭の接続を作れませんでした。')
        additions.append(eye_mesh);cuts.append(ring)
        details.append(dict(anchor=eye.point.tolist(),normal=eye.normal.tolist(),radius_mm=radius,attachment_volume_mm3=float(attachment.volume)))
    depth=float(np.clip(surface.height*.12,.63,.83))
    cavity_points=list(path)
    if config['expression']=='fangs':
        # Fill the oval instead of leaving a thin ring groove.
        cavity_points += [surface.project(t*mouth_width/2,mv) for t in np.linspace(-1,1,17)]
    mouth=tm.boolean.union([sphere(radius_mouth,p.point+p.normal*(radius_mouth-depth)) for p in cavity_points],engine='manifold')
    # Do not carve eyes, even when selecting a larger eye or a surprise mouth.
    for eye in additions:
        overlap=tm.boolean.intersection([mouth,eye],engine='manifold')
        if abs(overlap.volume)>1e-5:raise ValueError('目と口が重なります。目を小さくしてください。')
    teeth=[];tooth_details=[]
    if config['expression']=='fangs':
        base_width=max(1.3,min(1.8,surface.half[0]*.20))
        half_u=base_width/(2*surface.half[0])
        carved_head=tm.boolean.difference([head,mouth],engine='manifold')
        for center_u in [-.18,.18]:
            points=[surface.project(center_u-half_u,mv-.14),surface.project(center_u+half_u,mv-.14),surface.project(center_u,mv+.07)]
            vertices=np.array([p.point-p.normal*1.10 for p in points]+[p.point+p.normal*.35 for p in points])
            tooth=tm.convex.convex_hull(vertices)
            attachment=tm.boolean.intersection([carved_head,tooth],engine='manifold')
            if attachment.volume<.12:raise ValueError('牙と口の接続を作れませんでした。')
            teeth.append(tooth);tooth_details.append(dict(base_width_mm=float(np.linalg.norm(points[1].point-points[0].point)),
                attachment_volume_mm3=float(attachment.volume),tip=points[2].point.tolist(),relief_mm=.35))
        additions.extend(teeth)
        # Preserve the teeth when the final model subtracts this mouth cutter.
        mouth=tm.boolean.difference([mouth,tm.boolean.union(teeth,engine='manifold')],engine='manifold')
    cuts.append(mouth)
    return additions,cuts,dict(eyes=details,eye_count=count,mouth_points=[p.point.tolist() for p in path],
        mouth_normals=[p.normal.tolist() for p in path],eye_mouth_clearance_mm=gap,minimum_clearance_mm=.45,
        normalized_eye_forward=ev,normalized_mouth_forward=mv,expression=config['expression'],head_bounds_local=surface.bounds.tolist(),
        fang_count=len(teeth),fangs=tooth_details,mouth_style='open_with_two_triangular_fangs' if teeth else config['expression'])


def _generate(config,output_stl_path):
    started=time.monotonic();config=normalize_config(config)
    output=Path(output_stl_path)
    if output.exists():raise FileExistsError('Existing model output is preserved: '+str(output))
    parts,cuts,head=_anatomy(config)
    base=tm.boolean.union(parts,engine='manifold')
    scale=config['size']/max(base.extents[:2])
    for part in parts:part.apply_scale(scale)
    for cut in cuts:cut.apply_scale(scale)
    # head is one of parts, already scaled above.
    eyes,face_cuts,layout=_auto_face(head,config)
    joined=tm.boolean.union(parts+eyes,engine='manifold')
    mesh=tm.boolean.difference([joined,tm.boolean.union(cuts+face_cuts,engine='manifold')],engine='manifold')
    mesh,cleanup=_clean_mesh(mesh)
    if not mesh.is_watertight or not mesh.is_volume or len(mesh.split())!=1:raise ValueError('生物をひとつの立体にできませんでした。別の組み合わせを選んでください。')
    mesh.apply_translation([0,0,-mesh.bounds[0,2]])
    mesh,roundtrip_cleanup=_clean_mesh(mesh)
    output.parent.mkdir(parents=True,exist_ok=True)
    # Exclusive output creation; no user file is overwritten.
    with output.open('xb') as f:f.write(tm.exchange.stl.export_stl(mesh))
    reread=tm.load_mesh(output)
    if not reread.is_watertight or not reread.is_volume or len(reread.split())!=1:raise ValueError('STLの形状確認に失敗しました。')
    warnings=[]
    if mesh.extents[2]>12:warnings.append('高さがあるため、5分を超える可能性があります。印刷準備で時間を確認します。')
    if config['size']<29:warnings.append('小さいサイズでは目や模様が粗くなることがあります。')
    if config['eyes']=='three':warnings.append('3つ目の細部は、0.6 mmノズルで実物を確認してください。')
    geometry=dict(dimensions_mm=mesh.extents.tolist(),volume_mm3=float(mesh.volume),faces=len(mesh.faces),
        watertight=True,connected_components=1,estimated_solid_grams=float(mesh.volume*.00126),sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        generation_seconds=round(time.monotonic()-started,3),cleanup=cleanup,roundtrip_cleanup=roundtrip_cleanup)
    return dict(config=config,geometry=geometry,face_layout=layout,warnings=warnings,model_revision=MODEL_REVISION)


def generate(config,output_stl_path):
    # Empty temporary Boolean intersections have zero volume; trimesh's center
    # of mass calculation emits a benign divide warning while inspecting them.
    # Validation of every final body and face attachment remains unchanged.
    with np.errstate(invalid='ignore',divide='ignore'):
        return _generate(config,output_stl_path)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--catalog',action='store_true');parser.add_argument('--config');parser.add_argument('--output')
    args=parser.parse_args()
    if args.catalog:print(json.dumps(catalog(),ensure_ascii=False,indent=2))
    elif args.output:
        config=json.loads(Path(args.config).read_text()) if args.config else {}
        print(json.dumps(generate(config,args.output),ensure_ascii=False,indent=2))
    else:parser.error('--catalog or --output is required')
