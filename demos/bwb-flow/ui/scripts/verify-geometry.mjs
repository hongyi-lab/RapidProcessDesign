import assert from 'node:assert/strict';
import fs from 'node:fs';
import {buildSurface,buildSkeleton,sectionHeight} from '../app/geometry3d.ts';

const cases=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const results=[];
for(const r of cases) {
  const tc=r.geometry.section_layout.thickness_ratio;
  const mesh=buildSurface(r.geometry.stations,16,60,tc), p=mesh.attributes.position.array, index=mesh.index.array;
  assert.ok([...p].every(Number.isFinite));
  assert.ok([...mesh.attributes.normal.array].every(Number.isFinite));
  const width=mesh.boundingBox.max.x-mesh.boundingBox.min.x;
  assert.ok(Math.abs(width-r.inputs.span_m)<1e-6);
  assert.ok(Math.abs(mesh.boundingBox.max.y-mesh.boundingBox.min.y-tc*r.inputs.root_chord_m)<1e-6);
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
  const skeleton=buildSkeleton(r.geometry.sections);
  assert.ok(skeleton.children.length>0,'Actual sections must produce a structure view');
  let boxVertices=0;
  for(const object of skeleton.children){
    const array=object.geometry.attributes.position.array;
    assert.ok([...array].every(Number.isFinite));
    for(let i=0;i<array.length;i+=3){
      const y=Math.abs(array[i]),z=array[i+1],x=array[i+2];
      assert.ok(y>=r.geometry.section_layout.root_y_m-1e-6,'No central-body structure is invented');
      const section=r.geometry.sections.find(s=>Math.abs(s.y_m-y)<1e-6);
      assert.ok(section,'Every rendered section comes from the analysis geometry');
      assert.ok(section.corners.some(p=>Math.abs(p.x_m-x)<1e-6&&Math.abs(p.z_m-z)<1e-6),'Rendered section coordinates equal the EI input');
      const u=(x-section.leading_edge_x_m)/section.chord_m;
      assert.ok(Math.abs(z)<=sectionHeight(u,section.chord_m,tc)/2+1e-6,'Section must lie inside the displayed envelope');
      boxVertices++;
    }
    object.geometry.dispose();
  }
  results.push({span_m:width,thickness_ratio:tc,mesh_volume_m3:volume,engine_volume_m3:r.geometry.gross_volume_m3,relative_volume_error:relative,vertices:p.length/3,triangles:index.length/3,closed_edges:true,exact_section_vertices:boxVertices,central_structure_invented:false});
  mesh.dispose();
}
console.log(JSON.stringify({status:'passed',checks:['finite vertices and normals','full span','configured section maximum thickness','closed topology','outward winding','volume agreement below 0.1%','exact backend section corners','sections inside surface','outer-wing scope only'],cases:results},null,2));
