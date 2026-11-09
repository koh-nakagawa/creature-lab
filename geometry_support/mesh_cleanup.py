import numpy as np
import trimesh as tm

def clean(mesh):
    original_volume=float(mesh.volume)
    raw=mesh.copy();raw.vertices=np.asarray(raw.vertices,dtype=np.float32).astype(float)
    for digits in [None,7,6,5,4,3]:
        candidate=raw.copy()
        if digits is not None:candidate.merge_vertices(digits_vertex=digits)
        candidate.process(validate=True)
        if not candidate.is_watertight:tm.repair.fill_holes(candidate)
        if candidate.is_volume and candidate.is_watertight and len(candidate.split())==1:
            assert abs(candidate.volume-original_volume)<.04,(original_volume,candidate.volume)
            return candidate,dict(weld_digits=digits,volume_delta_mm3=float(candidate.volume-original_volume),faces=len(candidate.faces))
    raise ValueError('No precision-only repair produced one watertight volume')
