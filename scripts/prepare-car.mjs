// Rebuild the self-hosted CC BY 4.0 concept asset. See static/licenses/3d-model.txt.
import {mkdir,writeFile} from 'node:fs/promises';
import {spawnSync} from 'node:child_process';
import {resolve} from 'node:path';
const root=resolve(import.meta.dirname,'..');
await mkdir(resolve(root,'.tools'),{recursive:true});
await mkdir(resolve(root,'static/models/supercar'),{recursive:true});
const url='https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/main/Models/CarConcept/glTF-Binary/CarConcept.glb';
const response=await fetch(url);
if(!response.ok)throw new Error('Model download failed: '+response.status);
const source=resolve(root,'.tools/concept-car.glb');
const compact=resolve(root,'.tools/compact-car.glb');
await writeFile(source,Buffer.from(await response.arrayBuffer()));
const cli=resolve(root,'node_modules/@gltf-transform/cli/bin/cli.js');
function run(args){const result=spawnSync(process.execPath,[cli,...args],{cwd:root,stdio:'inherit'});if(result.status!==0)throw new Error('Asset optimization failed');}
run(['optimize',source,compact,'--compress','quantize','--flatten','false','--join','false','--palette','false','--instance','false','--simplify-error','0.001','--simplify-ratio','0.5','--texture-size','1024','--texture-compress','webp']);
run(['copy',compact,resolve(root,'static/models/supercar/car.gltf')]);
