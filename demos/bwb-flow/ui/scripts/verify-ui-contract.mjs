import assert from 'node:assert/strict';
import fs from 'node:fs';
import {comparisonDifferences,activeConstraint,resultOf} from '../app/types.ts';

const cases=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const baseline=cases.baseline;
assert.deepEqual(comparisonDifferences(baseline,cases.design),[],'Different hardware with identical frozen task/model can be compared');
for(const key of ['mission','model','solver'])assert.ok(comparisonDifferences(baseline,cases[key]).length>0,`${key} change must disable ranking and deltas`);
assert.equal(resultOf({analysis:baseline}),baseline);
assert.equal(resultOf(baseline),baseline);
const tightest=activeConstraint(baseline);
assert.ok(tightest);
assert.equal(tightest.normalized_margin,Math.min(...baseline.constraints.map(c=>c.normalized_margin)));
assert.ok(baseline.module_records.every(m=>m.name&&m.formula&&m.method&&m.limitation),'UI can use actual module metadata');
assert.equal(baseline.geometry.sections[0].y_m,baseline.geometry.section_layout.root_y_m);
assert.ok(baseline.mission.initial_state.time_s<baseline.mission.trace[0].time_s,'Plot begins with actual initial state');
const phases=baseline.mission.phases;
assert.ok(phases[1].duration_s>phases[0].duration_s*10,'Unequal phase lengths must retain physical-time axis');
console.log(JSON.stringify({status:'passed',checks:['same-task different-design comparison allowed','mission/model/solver changes block comparisons','actual closest constraint','metadata supplied by execution records','3D root matches backend','time origin and unequal physical phase durations'],case_analysis_ids:Object.fromEntries(Object.entries(cases).map(([key,value])=>[key,value.analysis_id]))},null,2));
