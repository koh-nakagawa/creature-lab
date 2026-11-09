import json,numpy as np,trimesh as tm
import geometry as g
c=g.normalize_config({'body':'dragon','head':'long','limbs':'six','tail':'club','back':'plates','texture':'scales','eye_size':1.15})
parts,cuts,head=g._anatomy(c);base=tm.boolean.union(parts,engine='manifold');scale=c['size']/max(base.extents[:2])
for part in parts:part.apply_scale(scale)
for cut in cuts:cut.apply_scale(scale)
eyes,facecuts,layout=g._auto_face(head,c)
mesh=tm.boolean.difference([tm.boolean.union(parts+eyes,engine='manifold'),tm.boolean.union(cuts+facecuts,engine='manifold')],engine='manifold')
for name,a in [('raw',mesh),('float32',mesh.copy())]:
 if name=='float32':a.vertices=np.asarray(a.vertices,dtype=np.float32).astype(float);a.process(validate=False)
 print(name,'closed',a.is_watertight,'volume',a.is_volume,'faces',len(a.faces),flush=True)
 for piece in a.split(only_watertight=False):print('PIECE',float(piece.volume),piece.bounds.tolist(),len(piece.faces),piece.is_watertight,flush=True)
