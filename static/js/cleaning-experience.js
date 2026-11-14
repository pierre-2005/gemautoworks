/* Native-scroll storyboard. Generated illustration, not footage of GEM staff or customer work. */
const root=document.querySelector('[data-car-experience]');
const canvas=document.querySelector('#cleaning-canvas');
const reduced=matchMedia('(prefers-reduced-motion: reduce)');
if(root&&canvas){
 const context=canvas.getContext('2d',{alpha:false});
 const sheet=new Image();let frame=0,progress=0;
 function paint(){
  frame=0;if(!sheet.complete||!sheet.naturalWidth)return;
  const rect=canvas.getBoundingClientRect(),ratio=Math.min(devicePixelRatio,2);
  canvas.width=Math.round(rect.width*ratio);canvas.height=Math.round(rect.height*ratio);
  const fw=sheet.naturalWidth/2,fh=sheet.naturalHeight/4;
  const step=reduced.matches?7:progress*7,first=Math.floor(step),blend=step-first;
  context.fillStyle='#0b1116';context.fillRect(0,0,canvas.width,canvas.height);
  const scale=Math.min(canvas.width/fw,canvas.height/fh),w=fw*scale,h=fh*scale,x=(canvas.width-w)/2,y=(canvas.height-h)/2;
  function draw(index,alpha){context.globalAlpha=alpha;context.drawImage(sheet,(index%2)*fw,Math.floor(index/2)*fh,fw,fh,x,y,w,h);}
  draw(Math.round(step),1);context.globalAlpha=1;
  document.querySelector('#cleaning-phase').textContent=reduced.matches?'Finish':progress<.2?'Prepare':progress<.55?'Wash':progress<.9?'Wipe':'Finish';
 }
 function update(){const top=parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--nav-h'));const rect=root.getBoundingClientRect();progress=Math.max(0,Math.min(1,(top-rect.top)/Math.max(1,root.offsetHeight-innerHeight+top)));if(!frame)frame=requestAnimationFrame(paint);}
 sheet.onload=()=>{canvas.classList.add('is-ready');update();};sheet.src='/static/img/cleaning-sequence.png';
 new ResizeObserver(update).observe(canvas);
 addEventListener('scroll',update,{passive:true});reduced.addEventListener('change',update);
}

