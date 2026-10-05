// Execute graph creation and export-drop behavior from the shipped UI.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../../web/js/graph_nodes.js'),'utf8');
function part(start,end){const a=source.indexOf(start),b=source.indexOf(end,a);assert(a>=0&&b>a);return source.slice(a,b);}
const calls=[],nodes=[{id:'frame',type:'frame',x:0,y:0,width:600,height:400,name:'Frame'},
  {id:'source',type:'blend',name:'Product',group:'frame',x:50,y:80,scan:{scenes:[{name:'Scene'}]}},
  {id:'other',type:'blend',group:'frame',x:350,y:100},
  {id:'export',type:'export',export_config:{source_id:null,folder_id:'folder',format:'FBX',scene:'',scope:'SCENE',collections:[]}}];
const c=vm.createContext({state:{project:{nodes}},calls,window:{},visibleNodes:()=>nodes,frameAncestors:()=>[],
  topSelection:()=>nodes.filter(n=>['source','other'].includes(n.id)),
  document:{querySelector:()=>({offsetWidth:244,offsetHeight:220})},
  error:message=>{throw Error(message);},run:async(action,args)=>calls.push({action,args})});
vm.runInContext(part('  const containers=','  const outputFormats=')+part('  function activeGroup','  function removeNode'),c);
vm.runInContext(part('  window.pipelineExportDrop=','  const previousMove='),c);
(async()=>{
  await c.addFrame({x:80,y:100},true);const frame=calls.pop();assert.equal(frame.action,'frame');
  assert.deepEqual(Array.from(frame.args.node_ids),['source','other']);assert.equal(frame.args.group,'frame');
  assert.equal(frame.args.x,22);assert.equal(frame.args.y,18);assert(frame.args.width>=600);assert.equal(frame.args.height,330);
  await c.addFrame({x:200,y:200});const empty=calls.pop();assert.equal(empty.action,'frame');assert.equal(empty.args.group,'frame');assert.equal(empty.args.node_ids.length,0);
  await c.addExport({x:100,y:150},'source');const exp=calls.pop();assert.equal(exp.action,'export_node');assert.equal(exp.args.source_id,'source');assert.equal(exp.args.group,'frame');
  const hit={closest:selector=>selector==='.node.export'?{dataset:{id:'export'}}:null};
  assert(c.window.pipelineExportDrop('source',hit,{kind:'collections',name:'Product'}));
  const drop=calls.pop();assert.equal(drop.action,'export_config');assert.equal(drop.args.config.format,'FBX');assert.equal(drop.args.config.folder_id,'folder');assert.equal(drop.args.config.source_id,'source');assert.equal(drop.args.config.scene,'Scene');assert.equal(drop.args.config.scope,'COLLECTIONS');assert.deepEqual(Array.from(drop.args.config.collections),['Product']);
  assert.equal(c.window.pipelineExportDrop('source',{closest:()=>null}),false);
  assert(!calls.some(call=>call.action==='folder'||call.action==='link_batch'));
  console.log('PASS: frame bounds and shared parent, graph-only creation, export source placement, content drops and preserved independent export settings');
})().catch(error=>{console.error(error);process.exitCode=1;});
