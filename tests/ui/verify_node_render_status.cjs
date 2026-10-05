// Exercise the production polling handler across transitions and a cold page load.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const RenderOverview=require('../../web/js/render_overview.js');
const source=fs.readFileSync(path.join(__dirname,'../../web/js/render_nodes.js'),'utf8');
const start=source.indexOf("PipelineUI.use('paintTasks','render-batches'");
const end=source.indexOf("PipelineUI.use('render','render-operation-nodes'",start);
let paint;
const slot={dataset:{},children:[],replaceChildren(){this.children=[];},append(child){this.children.push(child);}};
const markers=['t0','t1','t2','t3'].map(id=>({dataset:{targetState:id},classList:{toggle(){}}}));
const card={querySelector:()=>slot,querySelectorAll:()=>markers};
const project={nodes:[{id:'render',type:'render'}],renders:[{id:'r0',status:'Complete',written_frames:[1],config:{start:1,end:1}},{id:'r1',status:'Complete',written_frames:[1],config:{start:1,end:1}}],
  render_queue:[0,1,2,3].map(i=>({id:'q'+i,batch_id:'old',operation_id:'render',target_id:'t'+i,status:i<2?'Complete':i===2?'Cancelled':'Queued',run_id:i<2?'r'+i:'',effective_settings:{start:1,end:i<2?1:250}}))};
const context=vm.createContext({RenderOverview,state:{project},document:{querySelector:()=>card},$:()=>({querySelectorAll:()=>[]}),
  renderBatchCard:batch=>batch,PipelineUI:{use:(_stage,_name,_priority,handler)=>paint=handler}});
vm.runInContext(source.slice(start,end),context);
function poll(){paint(()=>{});}
poll();assert.equal(slot.children.length,1);assert.equal(slot.children[0].total,502);assert(slot.children[0].active);
project.render_queue[3].status='Preparing';poll();assert.equal(slot.children.length,1,'progress stays visible between queued and running setups');
project.render_queue[3].status='Cancelled';poll();assert.equal(slot.children.length,0,'cancelled terminal batches clear the graph progress strip');
assert.equal(markers[0].textContent,'✓');assert.equal(markers[2].textContent,'');
assert.equal(RenderOverview.batches(project)[0].status,'Cancelled','the cancelled result remains accurate in history');
context.state.project=JSON.parse(JSON.stringify(project));slot.dataset={};poll();assert.equal(slot.children.length,0,'a cold load cannot replay the historical cancellation as live progress');
context.state.project.render_queue.push({id:'new',batch_id:'new',operation_id:'render',target_id:'t2',status:'Queued',effective_settings:{start:1,end:2}});
poll();assert.equal(slot.children[0].id,'new');assert.equal(markers[2].textContent,'◷');
context.state.project.render_queue.at(-1).status='Complete';poll();assert.equal(slot.children.length,0,'completed batches also release the active display');
console.log('PASS: graph batch progress clears after cancellation/completion and stays clear after restart while history and subsequent batches remain usable');
