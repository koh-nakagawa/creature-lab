import numpy as np,trimesh as tm,manifold3d as manifold
import geometry as g
c=g.normalize_config({'limbs':'six'})
parts,cuts,head=g._anatomy(c);scale=c['size']/max(tm.boolean.union(parts,engine='manifold').extents[:2])
for part in parts:part.apply_scale(scale)
for cut in cuts:cut.apply_scale(scale)
eyes,facecuts,_=g._auto_face(head,c)
mesh=tm.boolean.difference([tm.boolean.union(parts+eyes,engine='manifold'),tm.boolean.union(cuts+facecuts,engine='manifold')],engine='manifold')
print('RAW',mesh.is_watertight,mesh.is_volume,len(mesh.split(only_watertight=False)),len(mesh.faces),flush=True)
for part in mesh.split(only_watertight=False):print('COMPONENT',part.volume,len(part.faces),part.is_watertight,flush=True)
solid=manifold.Manifold(manifold.Mesh64(vert_properties=np.asarray(mesh.vertices,dtype=np.float64),tri_verts=np.asarray(mesh.faces,dtype=np.uint64)))
print('KERNEL',solid.status(),flush=True)
for tolerance in [1e-5,1e-4,1e-3,.005]:
 data=solid.simplify(tolerance).to_mesh64();a=tm.Trimesh(vertices=np.asarray(data.vert_properties)[:,:3],faces=data.tri_verts,process=False)
 a.vertices=np.asarray(a.vertices,dtype=np.float32).astype(float);a.process(validate=False)
 print('SIMPLIFY',tolerance,a.is_watertight,a.is_volume,len(a.split(only_watertight=False)),float(a.volume-mesh.volume),flush=True)
