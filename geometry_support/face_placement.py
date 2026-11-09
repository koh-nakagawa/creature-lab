"""Place a two-eyed face from a semantic head mesh, not model-specific XYZ values.

The generator supplies a head mesh and forward/up vectors. This module does not
try to recognize an arbitrary unlabelled STL's head or species.
"""
from dataclasses import dataclass
import numpy as np
import trimesh as tm


def unit(v):
    a=np.asarray(v,dtype=float)
    return a/np.linalg.norm(a)


def uv_sphere(radius=1.0):
    return tm.creation.uv_sphere(radius=radius,count=[24,40])


def dome(radius,height):
    mesh=uv_sphere()
    mesh.apply_scale([radius,radius,height])
    return mesh.slice_plane([0,0,0],[0,0,1],cap=True)


def cylinder(radius,bottom,top):
    mesh=tm.creation.cylinder(radius=radius,height=top-bottom,sections=40)
    mesh.apply_translation([0,0,(bottom+top)/2])
    return mesh


def orient(mesh,origin,normal,right):
    z=unit(normal)
    x=unit(np.asarray(right)-z*np.dot(right,z))
    y=unit(np.cross(z,x))
    matrix=np.eye(4);matrix[:3,:3]=np.column_stack([x,y,z]);matrix[:3,3]=origin
    out=mesh.copy();out.apply_transform(matrix)
    return out


@dataclass
class SurfacePoint:
    point: np.ndarray
    normal: np.ndarray


class HeadSurface:
    def __init__(self,mesh,forward=(0,-1,0),up=(0,0,1)):
        self.mesh=mesh
        self.up=unit(up)
        self.forward=unit(np.asarray(forward)-self.up*np.dot(forward,self.up))
        self.right=unit(np.cross(self.up,self.forward))
        self.axes=np.array([self.right,self.forward,self.up])
        local=mesh.vertices@self.axes.T
        self.bounds=np.array([local.min(axis=0),local.max(axis=0)])
        self.center=self.bounds.mean(axis=0)
        self.half=(self.bounds[1]-self.bounds[0])/2
        self.height=float(self.bounds[1,2]-self.bounds[0,2])
        self.tri=local[mesh.faces]
        self.normals=mesh.vertex_normals[mesh.faces]
        a,b,c=self.tri[:,0,:2],self.tri[:,1,:2],self.tri[:,2,:2]
        self.a=a;self.ab=b-a;self.ac=c-a
        self.det=self.ab[:,0]*self.ac[:,1]-self.ab[:,1]*self.ac[:,0]

    def project(self,u,v):
        """Project a normalized right/forward head position onto its upper skin."""
        xy=self.center[:2]+np.array([u,v])*self.half[:2]
        delta=xy-self.a
        valid=np.abs(self.det)>1e-12
        beta=np.zeros(len(self.det));gamma=beta.copy()
        beta[valid]=(delta[valid,0]*self.ac[valid,1]-delta[valid,1]*self.ac[valid,0])/self.det[valid]
        gamma[valid]=(self.ab[valid,0]*delta[valid,1]-self.ab[valid,1]*delta[valid,0])/self.det[valid]
        valid &= (beta>=-1e-7)&(gamma>=-1e-7)&(beta+gamma<=1+1e-7)
        idx=np.flatnonzero(valid)
        if not len(idx):raise ValueError('Facial point is outside head surface')
        weights=np.column_stack([1-beta[idx]-gamma[idx],beta[idx],gamma[idx]])
        heights=np.sum(self.tri[idx,:,2]*weights,axis=1)
        best=int(np.argmax(heights));face=idx[best];w=weights[best]
        local=np.array([*xy,heights[best]])
        normal=unit(np.sum(self.normals[face]*w[:,None],axis=0))
        if np.dot(normal,self.up)<.05:raise ValueError('Head surface faces away from build up direction')
        return SurfacePoint(local@self.axes,normal)


def place_face(head_mesh,forward=(0,-1,0),up=(0,0,1),minimum_gap=.65):
    surface=HeadSurface(head_mesh,forward,up)
    # Sizes and search positions are shared ratios of head dimensions.
    # No species/slug branching or per-model facial XYZ coordinates.
    nominal_radius=float(np.clip(min(surface.half[0]*.265,surface.height*.30),1.60,2.25))
    mouth_radius=float(np.clip(surface.half[0]*.095,.60,.73))
    candidates=[]
    for shrink in [1.0,.94,.88]:
        eye_radius=nominal_radius*shrink
        separation=(eye_radius+.52)/surface.half[0]
        if separation>.56:continue
        for eye_v in [.36,.30,.42,.24]:
            try:eyes=[surface.project(-separation,eye_v),surface.project(separation,eye_v)]
            except ValueError:continue
            if min(np.dot(p.normal,surface.up) for p in eyes)<.35:continue
            for mouth_v in [.74,.80,.86,.68]:
                width=surface.half[0]*.54
                coords=[]
                try:
                    for t in np.linspace(-1,1,23):
                        coords.append(surface.project(t*.27,mouth_v+.055*(1-t*t)))
                except ValueError:continue
                if min(np.dot(p.point,surface.up)-surface.bounds[0,2] for p in coords)<1.3:continue
                # Conservative gap in each eye's local tangent plane.
                clearance=float('inf')
                for eye in eyes:
                    for mouth in coords:
                        d=mouth.point-eye.point
                        tangent=np.linalg.norm(d-eye.normal*np.dot(d,eye.normal))
                        clearance=min(clearance,tangent-eye_radius-mouth_radius)
                if clearance<minimum_gap:continue
                score=(1-shrink)*10+abs(eye_v-.36)+abs(mouth_v-.76)+.025*abs(clearance-1)
                candidates.append((score,eyes,coords,eye_radius,clearance,eye_v,mouth_v,width))
        if candidates:break
    if not candidates:raise ValueError('No facial layout meets head-surface and spacing constraints')
    _,eyes,mouth,eye_radius,clearance,eye_v,mouth_v,width=min(candidates,key=lambda x:x[0])
    height=float(np.clip(surface.height*.25,1.50,2.05))
    embed=float(np.clip(eye_radius*.30,.48,.75))
    additions=[];cutters=[];eye_metadata=[]
    for eye in eyes:
        origin=eye.point-eye.normal*embed
        eye_mesh=orient(dome(eye_radius,height),origin,eye.normal,surface.right)
        ring=tm.boolean.difference([cylinder(eye_radius*.65,height*.56,height+1),
                                   cylinder(eye_radius*.34,height*.56-.1,height+1.1)],engine='manifold')
        ring=orient(ring,origin,eye.normal,surface.right)
        attachment=tm.boolean.intersection([head_mesh,eye_mesh],engine='manifold')
        assert attachment.volume>.20,'Eye has insufficient attachment to head'
        additions.append(eye_mesh);cutters.append(ring)
        eye_metadata.append(dict(anchor=eye.point.tolist(),normal=eye.normal.tolist(),base_origin=origin.tolist(),
                                 radius_mm=eye_radius,height_mm=height,embedding_mm=embed,attachment_volume_mm3=float(attachment.volume)))
    depth=float(np.clip(surface.height*.12,.68,.85))
    spheres=[]
    for point in mouth:
        sphere=uv_sphere(mouth_radius)
        sphere.apply_translation(point.point+point.normal*(mouth_radius-depth))
        spheres.append(sphere)
    mouth_cut=tm.boolean.union(spheres,engine='manifold')
    for eye in additions:
        intersection=tm.boolean.intersection([mouth_cut,eye],engine='manifold')
        assert abs(intersection.volume)<1e-6,'Mouth intersects eye'
    cutters.append(mouth_cut)
    metadata=dict(head_bounds_local=surface.bounds.tolist(),forward=surface.forward.tolist(),up=surface.up.tolist(),
        eyes=eye_metadata,mouth_surface_points=[p.point.tolist() for p in mouth],mouth_normals=[p.normal.tolist() for p in mouth],
        mouth_radius_mm=mouth_radius,mouth_depth_mm=depth,mouth_width_mm=width,
        eye_mouth_tangent_clearance_mm=clearance,normalized_eye_forward=eye_v,normalized_mouth_forward=mouth_v,
        minimum_gap_mm=minimum_gap,eye_mouth_intersection_mm3=0.0)
    return additions,cutters,metadata
