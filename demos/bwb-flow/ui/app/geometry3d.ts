import * as THREE from 'three';
import type {Section} from './types';

export type Station = {y: number; c: number; x: number};
export const THICKNESS_RATIO = 0.14;

// Integral from 0 to 1 is 0.6: the loft uses the engine's volume coefficient.
// This is an illustrative symmetric section, not an aerodynamic airfoil model.
export function sectionHeight(u: number, chord: number, thicknessRatio=THICKNESS_RATIO) {
  return thicknessRatio * chord * 4*u*(1-u)*(1-0.5*(2*u-1)**2);
}
export function stationAt(stations: Station[], y: number): Station {
  const abs = Math.abs(y);
  const j = Math.max(1, stations.findIndex(s=>s.y >= abs));
  const a=stations[j-1], b=stations[j];
  const f=(abs-a.y)/(b.y-a.y);
  return {y, c:a.c+f*(b.c-a.c), x:a.x+f*(b.x-a.x)};
}
// Engine axes (aft, right, up) map to Three.js (right, up, aft), in metres.
export function surfacePoint(stations: Station[], y: number, u: number, side=1, thicknessRatio=THICKNESS_RATIO) {
  const s=stationAt(stations,y);
  return new THREE.Vector3(y, side*sectionHeight(u,s.c,thicknessRatio)/2, s.x+u*s.c);
}
export function buildSurface(stations: Station[], spanSteps=16, chordSteps=60, thicknessRatio=THICKNESS_RATIO) {
  const half:number[]=[0];
  for(let j=1;j<stations.length;j++) for(let i=1;i<=spanSteps;i++)
    half.push(stations[j-1].y+(stations[j].y-stations[j-1].y)*i/spanSteps);
  const ys=[...half.slice(1).reverse().map(v=>-v),...half];
  const positions:number[]=[], indices:number[]=[], ring=2*chordSteps;
  for(const y of ys) {
    for(let i=0;i<=chordSteps;i++) positions.push(...surfacePoint(stations,y,i/chordSteps,1,thicknessRatio).toArray());
    for(let i=chordSteps-1;i>=1;i--) positions.push(...surfacePoint(stations,y,i/chordSteps,-1,thicknessRatio).toArray());
  }
  for(let j=0;j<ys.length-1;j++) for(let i=0;i<ring;i++) {
    const a=j*ring+i, d=j*ring+(i+1)%ring, b=a+ring, c=d+ring;
    indices.push(a,c,b,a,d,c);
  }
  for(let i=1;i<ring-1;i++) {
    indices.push(0,i+1,i);
    const end=(ys.length-1)*ring;
    indices.push(end,end+i,end+i+1);
  }
  const mesh=new THREE.BufferGeometry();
  mesh.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));
  mesh.setIndex(indices); mesh.computeVertexNormals(); mesh.computeBoundingBox();
  return mesh;
}

/** Display exactly the polygons used for EI. No decorative ribs or FE stress field. */
export function buildSkeleton(sections: Section[]) {
  const group=new THREE.Group();
  if(sections.length<2)return group;
  const ordered=[...sections].sort((a,b)=>a.y_m-b.y_m);
  const shellMaterial=new THREE.MeshStandardMaterial({color:0x2d789e,metalness:.22,roughness:.5,side:THREE.DoubleSide,transparent:true,opacity:.64});
  for(const sign of [-1,1]) {
    const pos:number[]=[],idx:number[]=[],count=ordered[0].corners.length;
    for(const section of ordered)for(const point of section.corners)pos.push(sign*section.y_m,point.z_m,point.x_m);
    for(let i=0;i<ordered.length-1;i++)for(let j=0;j<count;j++){
      const a=i*count+j,b=i*count+(j+1)%count,c=a+count,d=b+count;idx.push(a,b,d,a,d,c);
    }
    const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(pos,3));geometry.setIndex(idx);geometry.computeVertexNormals();group.add(new THREE.Mesh(geometry,shellMaterial));
    for(let i=0;i<ordered.length;i++){
      const section=ordered[i],points=section.corners.map(p=>new THREE.Vector3(sign*section.y_m,p.z_m,p.x_m));
      points.push(points[0].clone());
      group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),new THREE.LineBasicMaterial({color:i===0?0xb86f27:0x286889})));
    }
  }
  return group;
}
