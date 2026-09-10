import assert from 'node:assert/strict';
import fs from 'node:fs';
import {buildSurface} from '../app/geometry3d.ts';

const cases=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const results=[];
for(const r of cases) {
  const mesh=buildSurface(r.geometry.stations), p=mesh.attributes.position.array, index=mesh.index.array;
  assert.ok([...p].every(Number.isFinite));
  assert.ok([...mesh.attributes.normal.array].every(Number.isFinite));
  const width=mesh.boundingBox.max.x-mesh.boundingBox.min.x;
  assert.ok(Math.abs(width-r.inputs.span_m)<1e-6);
  assert.ok(Math.abs(mesh.boundingBox.max.y-mesh.boundingBox.min.y-.14*r.inputs.root_chord_m)<1e-6);
  const edges=new Map();let volume=0;
  for(let i=0;i<index.length;i+=3) {
    const [ai,bi,ci]=[index[i],index[i+1],index[i+2]], a=ai*3,b=bi*3,c=ci*3;
    volume+=(p[a]*(p[b+1]*p[c+2]-p[b+2]*p[c+1])+p[a+1]*(p[b+2]*p[c]-p[b]*p[c+2])+p[a+2]*(p[b]*p[c+1]-p[b+1]*p[c]))/6;
    for(const [x,y] of [[ai,bi],[bi,ci],[ci,ai]]) {const key=[Math.min(x,y),Math.max(x,y)].join(',');edges.set(key,(edges.get(key)??0)+1);}
  }
  assert.ok([...edges.values()].every(v=>v===2),'Each closed surface edge must have two incident faces');
  assert.ok(volume>0,'Triangle winding must face outward');
  const relative=Math.abs(volume/r.geometry.gross_volume_m3-1);
  assert.ok(relative<.001,'Rendered mesh volume must match engine envelope within 0.1%');
  results.push({span_m:width,mesh_volume_m3:volume,engine_volume_m3:r.geometry.gross_volume_m3,relative_volume_error:relative,vertices:p.length/3,triangles:index.length/3,closed_edges:true});
  mesh.dispose();
}
console.log(JSON.stringify({status:'passed',checks:['finite vertices and normals','full span','section maximum thickness','closed topology','outward winding','volume agreement below 0.1%'],cases:results},null,2));
