const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
const base=process.env.FORMLAB_URL||'http://127.0.0.1:8000';
const result=await(await fetch(base+'/api/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:'pcb'})})).json();
const fixtures=[];
for(const [name,path] of [['part.stp',result.files['model.step']],['mesh.stl',result.files['model.stl']],['board.kicad_pcb',result.files['board.kicad_pcb']]])fixtures.push({name,mimeType:'application/octet-stream',buffer:Buffer.from(await(await fetch(base+path)).arrayBuffer())});
fixtures.push({name:'mesh.obj',mimeType:'text/plain',buffer:Buffer.from('v 0 0 0\nv 30 0 0\nv 0 30 0\nf 1 2 3\n')});
const binary=Buffer.from(new Float32Array([0,0,0,30,0,0,0,30,0]).buffer);
const manifest={asset:{version:'2.0'},scene:0,scenes:[{nodes:[0]}],nodes:[{mesh:0}],meshes:[{primitives:[{attributes:{POSITION:0}}]}],buffers:[{byteLength:36,uri:'data:application/octet-stream;base64,'+binary.toString('base64')}],bufferViews:[{buffer:0,byteOffset:0,byteLength:36}],accessors:[{bufferView:0,componentType:5126,count:3,type:'VEC3',min:[0,0,0],max:[30,30,0]}]};
fixtures.push({name:'mesh.gltf',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(manifest))});
delete manifest.buffers[0].uri;let json=Buffer.from(JSON.stringify(manifest));json=Buffer.concat([json,Buffer.alloc((4-json.length%4)%4,32)]);const head=Buffer.alloc(20);head.writeUInt32LE(0x46546c67,0);head.writeUInt32LE(2,4);head.writeUInt32LE(20+json.length+8+binary.length,8);head.writeUInt32LE(json.length,12);head.writeUInt32LE(0x4e4f534a,16);const bh=Buffer.alloc(8);bh.writeUInt32LE(binary.length,0);bh.writeUInt32LE(0x004e4942,4);fixtures.push({name:'mesh.glb',mimeType:'model/gltf-binary',buffer:Buffer.concat([head,json,bh,binary])});
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH,args:['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader']});
const page=await browser.newPage({viewport:{width:1440,height:960}});const errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto(base);
for(const file of fixtures){
await page.getByRole('link',{name:'↓ STEP',exact:true}).waitFor({timeout:60000});
await page.locator('#import-file').setInputFiles(file);
await page.locator('#exit-import').waitFor();await page.waitForFunction(()=>document.querySelector('#loading').hidden);
assert.equal(await page.locator('#project-name').textContent(),file.name);
assert.equal(await page.locator('#width').isDisabled(),true);
assert.equal(await page.locator('#error').textContent(),'');
if(file.name.endsWith('kicad_pcb'))assert.equal(await page.locator('#pcb-view img').evaluate(img=>img.complete&&img.naturalWidth>0),true);
await page.locator('#prompt').fill('宽 100');await page.locator('#send').click();assert.equal(await page.locator('#project-name').textContent(),file.name);

await page.locator('#exit-import').click();
console.log('Imported and restored:',file.name);
}
await page.getByRole('link',{name:'↓ STEP',exact:true}).waitFor();
manifest.buffers[0].uri='https://example.com/forbidden.bin';
await page.locator('#import-file').setInputFiles({name:'external.gltf',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(manifest))});
await page.waitForFunction(()=>document.querySelector('#error').textContent.includes('不支持外部'));
await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
assert.deepEqual(errors,[]);console.log('6 import formats, exit/reset, chat guard, external-resource rejection, mobile layout passed.');await browser.close();
})().catch(error=>{console.error(error);process.exit(1)});
