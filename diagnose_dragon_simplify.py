import contextlib,io,numpy as np,trimesh as tm,manifold3d as manifold
with contextlib.redirect_stdout(io.StringIO()):import diagnose_dragon_cross as sample
raw=sample.mesh
solid=manifold.Manifold(manifold.Mesh64(vert_properties=np.asarray(raw.vertices,dtype=np.float64),tri_verts=np.asarray(raw.faces,dtype=np.uint64)))
for tolerance in [1e-5,1e-4,1e-3]:
 data=solid.simplify(tolerance).to_mesh64()
 candidate=tm.Trimesh(vertices=np.asarray(data.vert_properties)[:,:3],faces=data.tri_verts,process=False)
 candidate.vertices=np.asarray(candidate.vertices,dtype=np.float32).astype(float);candidate.process(validate=False)
 print('SIMPLIFY',tolerance,'closed',candidate.is_watertight,'volume',candidate.is_volume,'parts',len(candidate.split(only_watertight=False)),
       'volume_delta',float(candidate.volume-raw.volume),'faces',len(candidate.faces),flush=True)
