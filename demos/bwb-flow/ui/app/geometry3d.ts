import * as THREE from 'three';

export type Station = {y: number; c: number; x: number};
export const THICKNESS_RATIO = 0.14;

// Integral from 0 to 1 is 0.6: the loft uses the engine's volume coefficient.
// This is an illustrative symmetric section, not an aerodynamic airfoil model.
export function sectionHeight(u: number, chord: number) {
  return THICKNESS_RATIO * chord * 4*u*(1-u)*(1-0.5*(2*u-1)**2);
}
export function stationAt(stations: Station[], y: number): Station {
  const abs = Math.abs(y);
  const j = Math.max(1, stations.findIndex(s=>s.y >= abs));
  const a=stations[j-1], b=stations[j];
  const f=(abs-a.y)/(b.y-a.y);
  return {y, c:a.c+f*(b.c-a.c), x:a.x+f*(b.x-a.x)};
}
// Engine axes (aft, right, up) map to Three.js (right, up, aft), in metres.
export function surfacePoint(stations: Station[], y: number, u: number, side=1) {
  const s=stationAt(stations,y);
  return new THREE.Vector3(y, side*sectionHeight(u,s.c)/2, s.x+u*s.c);
}
export function buildSurface(stations: Station[], spanSteps=16, chordSteps=60) {
  const half:number[]=[0];
  for(let j=1;j<stations.length;j++) for(let i=1;i<=spanSteps;i++)
    half.push(stations[j-1].y+(stations[j].y-stations[j-1].y)*i/spanSteps);
  const ys=[...half.slice(1).reverse().map(v=>-v),...half];
  const positions:number[]=[], indices:number[]=[], ring=2*chordSteps;
  for(const y of ys) {
    for(let i=0;i<=chordSteps;i++) positions.push(...surfacePoint(stations,y,i/chordSteps).toArray());
    for(let i=chordSteps-1;i>=1;i--) positions.push(...surfacePoint(stations,y,i/chordSteps,-1).toArray());
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

export function buildSkeleton(stations: Station[]) {
  const group=new THREE.Group(), half=stations.at(-1)!.y;
  const ribMat=new THREE.MeshStandardMaterial({color:0xb68548,metalness:.28,roughness:.5,side:THREE.DoubleSide});
  const sparMat=new THREE.MeshStandardMaterial({color:0x467ba3,metalness:.3,roughness:.43,side:THREE.DoubleSide});
  // Ribs are layout cues only; they are not an FE mesh or separately sized parts.
  for(let i=-10;i<=10;i++) {
    const y=i*half/10, s=stationAt(stations,y), pos:number[]=[], idx:number[]=[];
    const n=40, count=2*n;
    for(let k=0;k<count;k++) {
      const u=k<=n?k/n:(2*n-k)/n, side=k<=n?1:-1;
      const p=surfacePoint(stations,y,u,side);
      pos.push(...p.toArray(),y,p.y*.66,s.x+s.c*.5+(p.z-s.x-s.c*.5)*.88);
    }
    for(let k=0;k<count;k++) {const a=2*k,b=2*((k+1)%count);idx.push(a,b,b+1,a,b+1,a+1);}
    const geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.Float32BufferAttribute(pos,3));geo.setIndex(idx);geo.computeVertexNormals();
    group.add(new THREE.Mesh(geo,ribMat));
  }
  for(const u of [.2,.55]) {
    const pos:number[]=[],idx:number[]=[];
    const ys=[...stations.slice(1).reverse().map(s=>-s.y),...stations.map(s=>s.y)];
    for(const y of ys) pos.push(...surfacePoint(stations,y,u).toArray(),...surfacePoint(stations,y,u,-1).toArray());
    for(let i=0;i<ys.length-1;i++){const a=i*2;idx.push(a,a+2,a+3,a,a+3,a+1);}
    const geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.Float32BufferAttribute(pos,3));geo.setIndex(idx);geo.computeVertexNormals();group.add(new THREE.Mesh(geo,sparMat));
  }
  return group;
}
