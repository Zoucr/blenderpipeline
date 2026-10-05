// Latest saved results, variant identity and physical/graph folder scope.
const assert=require('node:assert/strict'),model=require('../../web/js/output_browser_model.js');
const project={nodes:[{id:'main',type:'folder',path:'Outputs',name:'Outputs'},
  {id:'child',type:'folder',path:'Outputs/Scene',group:'main'},
  {id:'frame',type:'frame',group:'main'},
  {id:'grouped',type:'folder',path:'Elsewhere',group:'frame'},
  {id:'unrelated',type:'folder',path:'Other'},
  {id:'file',type:'blend',name:'Shot'}, {id:'file2',type:'blend',name:'Another file'}],renders:[]};
const run=(id,number,status='Complete',extra={})=>({id,number,status,node_id:'file',name:'Shot',output:'Outputs/Scene/'+id,config:{scene:'Scene',view_layer:'Beauty',start:1,end:5},...extra});
project.renders=[run('old',1),run('partial',2,'Cancelled'),run('failed',3,'Failed'),run('deleted',4,'Deleted'),
  run('another-file',1,'Complete',{node_id:'file2'}),
  run('variant1',1,'Complete',{operation_id:'render',target_id:'one'}),
  run('variant2',1,'Complete',{operation_id:'render',target_id:'two'}),
  run('graph',1,'Complete',{output:'Elsewhere/graph',config:{scene:'Other scene'}}),
  run('outside',1,'Complete',{output:'Other/outside'})];
const sequence=(run_id,images,sample)=>({run_id,images,frame_count:images,kind:'final',sample,scene:'Scene'});
const shared=sequence('old',5,'old/0001.png');
const info={main:{sequences:[{...shared,sample:'Scene/'+shared.sample},sequence('partial',3,'Scene/partial/0001.png')]},
  child:{sequences:[shared,sequence('partial',3,'partial/0001.png')]},
  grouped:{sequences:[sequence('graph',1,'graph/0001.png')]}};
let rows=model.groups(project,'main',info),file=rows.find(g=>g.key===model.setupKey(project.renders[0]));
assert.equal(file.latest.run.id,'partial','newest partial saved version is shown');
assert.equal(file.attempt.run.id,'failed','empty failed attempt must not hide saved outputs');
assert.equal(file.latest.images,3,'overlapping folder scopes must not duplicate counts');
assert.equal(file.latest.partial,true);assert.equal(file.versions.length,3,'deleted versions are hidden');
assert.equal(rows.length,5,'sources, render variants and grouped folders remain separate');
assert.deepEqual(model.scopedFolders(project,'main').map(n=>n.id),['main','child','grouped']);
assert.equal(model.groups(project,'unrelated',info).length,1);
assert.equal(model.groups(project,'missing',info).length,0);
assert.equal(model.hasOutputs({...project,renders:[]},'main',{child:{images:5}}),true);
assert.equal(model.hasOutputs({...project,renders:[]},'unrelated',info),false);
const signature=model.signature(rows);project.renders[1].status='Complete';
assert.notEqual(model.signature(model.groups(project,'main',info)),signature,'live state changes refresh the list');
project.renders[1].status='Failed';info.main.sequences.pop();info.child.sequences.pop();
file=model.groups(project,'main',info).find(g=>g.key===model.setupKey(project.renders[0]));
assert.equal(file.latest.run.id,'old','failed attempts without images fall back to latest saved result');
const overview=require('../../web/js/render_overview.js');
const stable=[{...sequence('old',5,'old/a.png'),directory:'old',node_id:'file',operation_id:'render',target_id:'one',version:1},
  {...sequence('partial',3,'new/a.png'),directory:'renamed/path',node_id:'file',operation_id:'render',target_id:'one',version:2},
  {...sequence('variant2',5,'variant/a.png'),directory:'same',node_id:'file',operation_id:'render',target_id:'two',version:1}];
assert.deepEqual(overview.latestSequences({sequences:stable}).map(s=>s.run_id),['partial','variant2'],'folder nodes use stable setup IDs instead of version directory names');
console.log('PASS: output scope, latest saved/partial versions, source/variant identity, deduplication and live signatures');
