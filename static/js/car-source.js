/* GEM scroll-controlled showroom. Model attribution: static/licenses/3d-model.md. */
import * as THREE from 'three';
import {GLTFLoader} from 'three/examples/jsm/loaders/GLTFLoader.js';
import {RoomEnvironment} from 'three/examples/jsm/environments/RoomEnvironment.js';

const section = document.querySelector('[data-car-experience]');
const stage = document.querySelector('#car-stage');
const canvas = document.querySelector('#car-canvas');
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
const saveData = navigator.connection?.saveData || matchMedia('(prefers-reduced-data: reduce)').matches;
function fallback() {
  stage?.classList.remove('is-ready');
  section?.classList.add('g-car-unavailable');
  stage?.setAttribute('aria-label','Automotive inspiration: a sports car on the open road.');
  const cue=document.querySelector('.g-scroll-cue span');
  if(cue)cue.textContent='Meet GEM below';
}
if (saveData) fallback();
if (section && stage && canvas && !saveData) start().catch(fallback);

async function start() {
  const renderer = new THREE.WebGLRenderer({canvas, antialias:true, alpha:true, powerPreference:'low-power'});
  renderer.setPixelRatio(Math.min(devicePixelRatio, innerWidth < 700 ? 1.35 : 1.75));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = .95;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(33, 1, .1, 50);
  const pmrem = new THREE.PMREMGenerator(renderer);
  const room = new RoomEnvironment();
  const env = pmrem.fromScene(room, .04);
  scene.environment = env.texture;
  scene.environmentIntensity = .75;
  room.dispose();
  pmrem.dispose();
  const key = new THREE.DirectionalLight(0xe7f1ff, 2);
  key.position.set(-4,7,-4);
  scene.add(key, new THREE.HemisphereLight(0xc5dcff,0x17212d,.5));
  const rim = new THREE.DirectionalLight(0x72aaff, 1.5);
  rim.position.set(5,3,5);
  scene.add(rim);
  // External same-origin textures keep the existing Content Security Policy intact.
  const gltf = await new GLTFLoader().loadAsync('/static/models/supercar/car.gltf');
  const model = gltf.scene;
  const initialBox = new THREE.Box3().setFromObject(model);
  const initialSize = initialBox.getSize(new THREE.Vector3());
  model.scale.setScalar(4.8 / Math.max(initialSize.x, initialSize.y, initialSize.z));
  const box = new THREE.Box3().setFromObject(model);
  const center = box.getCenter(new THREE.Vector3());
  model.position.set(-center.x, -box.min.y, -center.z);
  const pivot = new THREE.Group();
  pivot.add(model);
  scene.add(pivot);
  const body = new THREE.MeshPhysicalMaterial({color:'#1758bb',metalness:.9,roughness:.22,clearcoat:1,clearcoatRoughness:.08,envMapIntensity:1.1});
  const trim = new THREE.MeshStandardMaterial({color:'#242d38',metalness:.8,roughness:.3});
  const glass = new THREE.MeshPhysicalMaterial({color:'#13232d',metalness:.35,roughness:.09,transparent:true,opacity:.65,envMapIntensity:1.1});
  const rubber = new THREE.MeshStandardMaterial({color:'#080b0e',metalness:0,roughness:.9});
  const wheelMetal = new THREE.MeshStandardMaterial({color:'#424b56',metalness:1,roughness:.27});
  model.traverse(node => {
    if (!node.isMesh) return;
    node.frustumCulled = true;
    const materialName=node.material?.name || '';
    if (materialName.startsWith('Paint 1')) node.material = body;
    if (materialName.startsWith('Paint 2')) node.material = trim;
    if (materialName === 'Glass') node.material = glass;
    if (materialName === 'Tireside' || materialName === 'Tiretread') node.material = rubber;
    if (materialName === 'Rim1' || materialName === 'Rim2') node.material = wheelMetal;
    if (node.name === 'License_Plate' || node.name === 'License Plate' || node.name === 'InteriorSteeringEmblem') node.visible=false;
  });
  const leftDoor=model.getObjectByName('BodyDoorLColor1');
  const rightDoor=model.getObjectByName('BodyDoorRColor1');
  const leftClosed=leftDoor?.rotation.clone();
  const rightClosed=rightDoor?.rotation.clone();
  // A soft contact shadow grounds the geometry without an always-running shadow pass.
  const shadowCanvas = document.createElement('canvas');
  shadowCanvas.width = shadowCanvas.height = 128;
  const ctx = shadowCanvas.getContext('2d');
  const gradient = ctx.createRadialGradient(64,64,8,64,64,64);
  gradient.addColorStop(0,'rgba(0,0,0,.7)');
  gradient.addColorStop(1,'rgba(0,0,0,0)');
  ctx.fillStyle=gradient;ctx.fillRect(0,0,128,128);
  const shadowTexture = new THREE.CanvasTexture(shadowCanvas);
  const shadow = new THREE.Mesh(new THREE.PlaneGeometry(4.8,6.8),new THREE.MeshBasicMaterial({map:shadowTexture,transparent:true,depthWrite:false,opacity:.65}));
  shadow.rotation.x=-Math.PI/2;shadow.position.y=.004;pivot.add(shadow);
  let target = 0, current = 0, frame = 0, visible = true;
  let disposed = false;
  function resize() {
    const {width,height} = stage.getBoundingClientRect();
    renderer.setSize(width,height,false);
    camera.aspect=width/height;
    const mobile=innerWidth<700;
    camera.position.set(mobile?8.4:4.4,mobile?3.4:1.9,mobile?-9.3:-5);
    camera.lookAt(mobile?0:-.8,mobile?.55:.6,0);
    camera.updateProjectionMatrix();
    schedule();
  }
  function readScroll() {
    const rect=section.getBoundingClientRect();
    const distance=section.offsetHeight-innerHeight+parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--nav-h'));
    target=reduced.matches?0:THREE.MathUtils.clamp((-rect.top+parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--nav-h')))/Math.max(1,distance),0,1);
    section.style.setProperty('--car-progress',String(target));
    schedule();
  }
  function draw() {
    frame=0;
    if(disposed||!visible||document.hidden) return;
    current=reduced.matches?target:THREE.MathUtils.lerp(current,target,.13);
    pivot.rotation.y = Math.PI+.05 + current*Math.PI*1.6;
    const doorAngle=THREE.MathUtils.smoothstep(current,.25,.7)*1.05;
    if(leftDoor)leftDoor.rotation.y=leftClosed.y-doorAngle;
    if(rightDoor)rightDoor.rotation.y=rightClosed.y+doorAngle;
    renderer.render(scene,camera);
    if(Math.abs(current-target)>.0002) schedule();
  }
  function schedule(){if(!frame&&!disposed&&visible&&!document.hidden)frame=requestAnimationFrame(draw);}
  const ro=new ResizeObserver(resize);ro.observe(stage);
  const io=new IntersectionObserver(entries=>{visible=entries[0].isIntersecting;if(visible){readScroll();schedule();}},{rootMargin:'100px'});io.observe(section);
  addEventListener('scroll',readScroll,{passive:true});
  addEventListener('resize',resize,{passive:true});
  document.addEventListener('visibilitychange',schedule);
  reduced.addEventListener('change',readScroll);
  canvas.addEventListener('webglcontextlost',event=>{event.preventDefault();stage.classList.remove('is-ready');section.classList.add('g-car-unavailable');document.querySelector('.g-car-controls').hidden=true;});
  canvas.addEventListener('webglcontextrestored',()=>{stage.classList.add('is-ready');section.classList.remove('g-car-unavailable');document.querySelector('.g-car-controls').hidden=false;resize();});
  document.querySelectorAll('[data-paint]').forEach(button=>button.addEventListener('click',()=>{
    body.color.set(button.dataset.paint);
    document.querySelectorAll('[data-paint]').forEach(item=>item.setAttribute('aria-pressed',String(item===button)));
    document.querySelector('#paint-label').textContent=button.dataset.paintName;
    schedule();
  }));
  resize();readScroll();renderer.render(scene,camera);
  stage.classList.add('is-ready');
  document.querySelector('.g-car-controls').hidden=false;
  addEventListener('pagehide',event=>{
    if(event.persisted)return;
    disposed=true;cancelAnimationFrame(frame);ro.disconnect();io.disconnect();
    removeEventListener('scroll',readScroll);removeEventListener('resize',resize);
    document.removeEventListener('visibilitychange',schedule);reduced.removeEventListener('change',readScroll);
    scene.traverse(node=>{if(node.isMesh){node.geometry.dispose();const mats=Array.isArray(node.material)?node.material:[node.material];mats.forEach(m=>m.dispose());}});
    env.dispose();shadowTexture.dispose();renderer.dispose();
  },{once:true});
}
