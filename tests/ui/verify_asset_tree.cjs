const assert=require('node:assert/strict');
const tree=require('../../web/js/asset_tree.js');
const activity=require('../../web/js/activity.js');
const scan={objects:[{name:'Root',parent:''},{name:'Part 2',parent:'Root'},{name:'Part 10',parent:'Root'}]};
const assets=[
  {kind:'collections',name:'Set',children:['Parts'],members:['Root','Part 2','Part 10'],direct_members:['Part 2'],objects:3},
  {kind:'collections',name:'Parts',children:[],members:['Root','Part 2','Part 10'],direct_members:['Root','Part 2','Part 10'],objects:3},
  ...scan.objects.map(o=>({kind:'objects',name:o.name})),
  {kind:'materials',name:'Copper'}, {kind:'meshes',name:'Geometry'}
];
const built=tree.build(scan,assets),expanded=new Set(['collections','collections/'+tree.key(assets[0])]);
let rows=tree.rows(built,{expanded});
assert(rows.some(r=>r.name==='Parts'));
assert(rows.some(r=>r.name==='Part 2'),'direct multi-membership must not be removed as a recursive duplicate');
assert(!rows.some(r=>r.name==='Root'),'collapsed collections hide their members');
function expand(nodes){for(const n of nodes){expanded.add(n.id);expand(n.children);}}expand(built);
rows=tree.rows(built,{expanded});
const root=rows.find(r=>r.name==='Root'),nested=rows.filter(r=>r.name==='Part 2').find(r=>r.depth>root.depth);
assert(nested,'empty parenting is preserved inside the collection');
assert.equal(rows.filter(r=>r.name==='Part 2').length,2);
assert.equal(new Set(rows.filter(r=>r.name==='Part 2').map(r=>tree.key(r.asset))).size,1,'selection remains one datablock across repeated rows');
const search=tree.rows(built,{expanded:new Set(),query:'Part 10'});
assert(search.some(r=>r.name==='Set')&&search.some(r=>r.name==='Parts')&&search.some(r=>r.name==='Root'));
assert(!search.some(r=>r.name==='Copper')||!search.find(r=>r.name==='Copper').match);
assert(!search.some(r=>r.name==='Part 2'));
assert(search.filter(r=>r.asset&&r.match).every(r=>r.name==='Part 10'),'context ancestors must not be bulk-selected');
const onlyMaterials=tree.rows(built,{kind:'materials'});
assert.equal(onlyMaterials.filter(r=>r.asset).length,1);
assert.equal(onlyMaterials.find(r=>r.asset).name,'Copper');
assert(!tree.rows(built,{expanded,allowedKinds:new Set(['collections','objects','materials'])}).some(r=>r.name==='Geometry'));
const oldAssets=assets.map(a=>({...a}));oldAssets.forEach(a=>delete a.direct_members);
assert(tree.build(scan,oldAssets).length,'existing scans remain browsable before refreshing');
const cycle=tree.build({objects:[{name:'A',parent:'B'},{name:'B',parent:'A'}]},[{kind:'objects',name:'A'},{kind:'objects',name:'B'},{kind:'collections',name:'Loop',children:['Loop'],members:[]}]);
assert(tree.rows(cycle,{query:'A'}).length<10,'malformed cyclic metadata cannot recurse forever');
const now=Date.parse('2026-10-04T10:00:20Z');
const pending=new Map([['new',{action:'link_batch',args:{source_id:'source',target_id:'shot'},created:'2026-10-04T10:00:00Z'}]]);
let jobs=activity.jobs([],pending,now);
assert.equal(jobs[0].node_id,'shot');assert.equal(jobs[0].label,'Linking assets');assert.equal(jobs[0].seconds,20);
jobs=activity.jobs([{id:'new',action:'link_batch',node_id:'shot',args:pending.get('new').args,status:'Running',created:'2026-10-04T10:00:00Z'}],pending,now);
assert.equal(jobs.length,1,'accepted jobs must not disappear or appear twice before polling');
assert.equal(jobs[0].status,'Running');
assert.equal(activity.jobs([{id:'done',action:'link_batch',status:'Complete'},{id:'layout',action:'graph_edit',status:'Running'}],[],now).length,0);
assert.equal(activity.elapsed(65),'1m 5s');
const project={renders:[{id:'run',operation_id:'render-node',node_id:'shot',name:'Scene / Beauty',status:'Preparing',created:'2026-10-04T10:00:00Z'}]};
const first=activity.renderJobs(project)[0];assert.deepEqual(first.args.node_ids,['shot','render-node']);
project.renders[0].status='Rendering';project.renders[0].phase='Rendering';project.renders[0].current_frame=1;
project.renders[0].render_device={effective:'GPU',backend:'OPTIX'};
const ongoing=activity.jobs([{id:'submission',action:'queue_render_node',status:'Complete'},...activity.renderJobs(project)],[],now);
assert.equal(ongoing.length,1,'finishing submission must not clear the active render indicator');
assert.equal(ongoing[0].id,first.id);assert.equal(ongoing[0].seconds,20);assert.equal(ongoing[0].label,'Rendering');
assert(ongoing[0].renderDetail.includes('GPU · OPTIX'));assert(ongoing[0].renderDetail.includes('frame 1'));
project.renders[0].status='Failed';assert.equal(activity.renderJobs(project).length,0);
console.log('PASS: nested asset hierarchy, search/selection, immediate operation feedback and persistent render activity through submission completion');
