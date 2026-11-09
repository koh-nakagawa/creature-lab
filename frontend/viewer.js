import * as THREE from 'three';
import {OrbitControls} from './vendor/three-0.180.0/examples/jsm/controls/OrbitControls.js';
import {STLLoader} from './vendor/three-0.180.0/examples/jsm/loaders/STLLoader.js';

export class CreatureViewer {
  constructor(element){
    this.element=element;this.mesh=null;this.loader=new STLLoader();
    this.renderer=new THREE.WebGLRenderer({antialias:true,alpha:true,preserveDrawingBuffer:true});
    this.renderer.setPixelRatio(Math.min(devicePixelRatio,1.7));this.renderer.setClearColor(0,0);
    this.renderer.shadowMap.enabled=true;this.renderer.shadowMap.type=THREE.PCFSoftShadowMap;
    this.renderer.toneMapping=THREE.ACESFilmicToneMapping;this.renderer.toneMappingExposure=1.22;
    element.appendChild(this.renderer.domElement);this.scene=new THREE.Scene();
    this.camera=new THREE.PerspectiveCamera(35,1,.1,1000);this.camera.position.set(35,30,55);
    this.controls=new OrbitControls(this.camera,this.renderer.domElement);
    Object.assign(this.controls,{enableDamping:true,dampingFactor:.08,minDistance:20,maxDistance:180,maxPolarAngle:Math.PI*.49,enablePan:false});
    this.material=new THREE.MeshStandardMaterial({color:'#73bba6',roughness:.5,metalness:.025});
    this.scene.add(new THREE.HemisphereLight(0xfff9e8,0x8aab93,2.1));
    const key=new THREE.DirectionalLight(0xfff8e3,3.8);key.position.set(-28,65,45);key.castShadow=true;
    key.shadow.mapSize.set(1024,1024);Object.assign(key.shadow.camera,{left:-40,right:40,top:40,bottom:-40,near:1,far:180});
    key.shadow.normalBias=.08;key.shadow.bias=-.0001;this.scene.add(key);
    const fill=new THREE.DirectionalLight(0xd7e7ff,1.5);fill.position.set(35,20,-25);this.scene.add(fill);
    const ground=new THREE.Mesh(new THREE.PlaneGeometry(200,200),new THREE.ShadowMaterial({opacity:.13}));
    ground.rotation.x=-Math.PI/2;ground.position.y=-.02;ground.receiveShadow=true;this.scene.add(ground);
    new ResizeObserver(()=>this.resize()).observe(element);this.resize();
    this.renderer.setAnimationLoop(()=>{if(!document.hidden&&element.clientWidth){this.controls.update();this.renderer.render(this.scene,this.camera);}});
  }
  resize(){const w=this.element.clientWidth,h=this.element.clientHeight;if(!w||!h)return;
    this.camera.aspect=w/h;this.camera.updateProjectionMatrix();this.renderer.setSize(w,h,false);
    if(this.mesh)this.frame(this.camera.position.clone().sub(this.controls.target));}
  frame(direction=new THREE.Vector3(.55,.55,.90)){
    if(!this.mesh)return;direction.normalize();const box=new THREE.Box3().setFromObject(this.mesh),target=box.getCenter(new THREE.Vector3());
    const right=new THREE.Vector3().crossVectors(new THREE.Vector3(0,1,0),direction).normalize();
    const up=new THREE.Vector3().crossVectors(direction,right).normalize();
    const tanV=Math.tan(THREE.MathUtils.degToRad(this.camera.fov)/2),tanH=tanV*this.camera.aspect;let distance=20;
    for(const x of [box.min.x,box.max.x])for(const y of [box.min.y,box.max.y])for(const z of [box.min.z,box.max.z]){
      const p=new THREE.Vector3(x,y,z).sub(target);
      distance=Math.max(distance,p.dot(direction)+Math.abs(p.dot(right))/tanH,p.dot(direction)+Math.abs(p.dot(up))/tanV);
    }
    distance*=1.12;this.camera.position.copy(direction.multiplyScalar(distance).add(target));
    this.controls.target.copy(target);this.controls.maxDistance=Math.max(160,distance*2);this.controls.update();
  }
  clear(){
    this.loadRevision=(this.loadRevision||0)+1;
    if(this.mesh){this.scene.remove(this.mesh);this.mesh.geometry.dispose();this.mesh=null;}
  }
  async load(url,reset=false){
    const revision=this.loadRevision=(this.loadRevision||0)+1;
    const geometry=await this.loader.loadAsync(url);
    if(revision!==this.loadRevision){geometry.dispose();return;}
    geometry.computeBoundingBox();const b=geometry.boundingBox;
    geometry.translate(-(b.min.x+b.max.x)/2,-(b.min.y+b.max.y)/2,-b.min.z);geometry.computeVertexNormals();
    const first=!this.mesh;if(this.mesh){this.scene.remove(this.mesh);this.mesh.geometry.dispose();}
    this.mesh=new THREE.Mesh(geometry,this.material);this.mesh.rotation.x=-Math.PI/2;
    this.mesh.castShadow=true;this.mesh.receiveShadow=true;this.scene.add(this.mesh);if(first||reset)this.frame();
  }
  image(){this.renderer.render(this.scene,this.camera);return this.renderer.domElement.toDataURL('image/png');}
}
