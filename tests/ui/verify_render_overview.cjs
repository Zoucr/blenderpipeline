const assert=require('node:assert/strict'),overview=require('../../web/js/render_overview.js');
const project={nodes:[],render_queue:[0,1,2,3].map(i=>({id:'q'+i,batch_id:'batch',status:i?'Queued':'Complete',run_id:i?'':'first',effective_settings:{scene:'Scene',start:1,end:1},created:'2026-10-04T10:00:00Z'})),renders:[{id:'first',status:'Complete',config:{start:1,end:1},written_frames:[1]}]};
let batch=overview.batches(project)[0];assert(batch.active);assert.equal(batch.saved,1);assert.equal(batch.total,4);assert.equal(batch.progress,25);
assert.equal(batch.current.q.id,'q1','batch stays active while the next Blender setup is starting');
project.render_queue[1].status='Preparing';project.render_queue[1].node_id='source';project.render_queue[1].target_id='target';
project.renders.push({id:'preparing',status:'Preparing',batch_id:'batch',node_id:'source',target_id:'target',config:{start:1,end:1}});
batch=overview.batches(project)[0];assert.equal(batch.jobs.length,4);assert.equal(batch.total,4,'preparation must not briefly count the same setup twice');
assert.equal(batch.current.run.id,'preparing');project.renders.pop();
project.render_queue[1].status='Rendering';project.render_queue[1].run_id='second';project.renders.push({id:'second',status:'Rendering',config:{start:1,end:1},written_frames:[1]});
batch=overview.batches(project)[0];assert.equal(batch.saved,2);assert.equal(batch.progress,50);assert.equal(batch.id,'batch');
project.render_queue[1].status='Complete';project.renders[1].status='Complete';batch=overview.batches(project)[0];assert(batch.active);assert.equal(batch.done,2);assert.equal(batch.current.q.id,'q2');
project.render_queue[2].status='Failed';project.render_queue[3].status='Cancelled';batch=overview.batches(project)[0];assert(!batch.active);assert.equal(batch.failed,1);assert.equal(batch.cancelled,1);assert.equal(batch.saved,2,'cancelled/failed frames do not inflate completion');
assert.equal(overview.frameCount({mode:'STILL',start:3,end:250}),1);assert.equal(overview.frameCount({start:1,end:10,step:3}),4);
const sequences=overview.latestSequences({sequences:[{scene:'Main',view_layer:'Beauty',kind:'final',version:1,directory:'File/Main/Beauty/File_r001',images:500},{scene:'Main',view_layer:'Beauty',kind:'final',version:2,directory:'File/Main/Beauty/File_r002',images:1},{scene:'Main',kind:'compositor',images:100},{scene:'Main',view_layer:'Mask',kind:'final',version:1,directory:'File/Main/Mask/File_r001',images:500}]});
assert.equal(sequences.length,2);assert.equal(sequences[0].images,1,'the newest version is represented independently from historical frames');
const direct=overview.latestSequences({sequences:[{node_id:'a',scene:'Scene',kind:'final',version:1,directory:'Shot_r001'},{node_id:'a',scene:'Scene',kind:'final',version:2,directory:'Shot_r002'},{node_id:'b',scene:'Scene',kind:'final',version:1,directory:'Other_r001'}]});
assert.equal(direct.length,2);assert.equal(direct[0].version,2,'root-level versions consolidate without combining different source files');
assert.equal(overview.rangeLabel([[1,500]]),'1–500');assert.equal(overview.rangeLabel([[1,3],[7,7]],2),'1–3, 7 · step 2');
const sceneRows=overview.sceneSummaries({sequences:[
  {node_id:'a',scene:'Main',view_layer:'Beauty',kind:'final',version:1,directory:'A/Main/Beauty/A_r001',images:500,frame_count:500,ranges:[[1,500]],step:1,expected_frames:500},
  {node_id:'a',scene:'Main',view_layer:'Beauty',kind:'final',version:2,directory:'A/Main/Beauty/A_r002',images:1,frame_count:1,ranges:[[1,1]],step:1,expected_frames:500},
  {node_id:'a',scene:'Main',view_layer:'Beauty',kind:'final',version:1,directory:'A/Main/Beauty_02/A_r001',images:1,frame_count:1,ranges:[[1,1]],step:1,expected_frames:1},
  {node_id:'a',scene:'Main',view_layer:'Mask',kind:'final',version:1,directory:'A/Main/Mask/A_r001',images:3,frame_count:3,ranges:[[2,4]],step:1,expected_frames:3},
  {node_id:'b',scene:'Main',view_layer:'Beauty',kind:'final',version:1,directory:'B/Main/Beauty/B_r001',images:1,frame_count:1,ranges:[[1,1]],step:1,expected_frames:1},
  {node_id:'a',scene:'Main',kind:'compositor',images:10,directory:'A/compositor',prefix:'Mist_'}
]});
assert.equal(sceneRows.length,2,'equal scene names in separate files remain separate');
assert.equal(sceneRows[0].images,5,'only newest versions contribute to the scene preview');
assert.equal(sceneRows[0].layers,2,'duplicate variants do not count as extra view layers');
assert(sceneRows[0].partial);assert(!sceneRows[0].same,'unequal layer frame ranges should show actual image totals');
assert(!sceneRows[1].partial);assert(sceneRows[1].same);
global.RenderOverview=overview;
const activity=require('../../web/js/activity.js');project.nodes=[{id:'folder',type:'folder',group:'parent'},{id:'parent',type:'folder'}];project.render_queue[3].status='Queued';project.render_queue[3].operation_id='render';project.render_queue[3].node_id='shot';project.render_queue[3].effective_settings.folder_id='folder';
const job=activity.renderJobs(project)[0];assert.equal(job.id,'render-batch:batch');assert(job.args.node_ids.includes('folder'));assert(job.args.node_ids.includes('parent'));assert(job.args.node_ids.includes('render'));assert(job.label.includes('2/4 frames'));
console.log('PASS: continuous batch progress, frame counts, cancellation, newest scene/layer sequence summaries and folder activity through setup transitions');
