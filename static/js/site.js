/* GEM Autoworks V2 | keyboard-friendly, progressive interactions. */
(() => {
  'use strict';
  document.body.classList.add('js-ready');
  const navToggle = document.querySelector('.menu-toggle');
  const nav = document.querySelector('#main-nav');
  const closeNav = () => {
    if (!navToggle || !nav) return;
    nav.classList.remove('open');
    navToggle.setAttribute('aria-expanded','false');
    navToggle.setAttribute('aria-label','Open navigation menu');
  };
  if (navToggle && nav) {
    navToggle.addEventListener('click', () => {
      const open = navToggle.getAttribute('aria-expanded') !== 'true';
      nav.classList.toggle('open',open);
      navToggle.setAttribute('aria-expanded',String(open));
      navToggle.setAttribute('aria-label',open?'Close navigation menu':'Open navigation menu');
    });
    nav.querySelectorAll('a').forEach(link => link.addEventListener('click',closeNav));
    document.addEventListener('keydown',event => {if(event.key==='Escape') closeNav();});
    document.addEventListener('click',event => {
      if(!nav.contains(event.target) && !navToggle.contains(event.target)) closeNav();
    });
  }

  document.querySelectorAll('[data-confirm]').forEach(el => {
    el.addEventListener('click',event => {
      if(!window.confirm(el.dataset.confirm)) event.preventDefault();
    });
  });

  // An actual section navigation experience, keeping every admin form server-rendered.
  const workspace = document.querySelector('.admin-workspace');
  if (workspace) {
    const links = [...workspace.querySelectorAll('[data-admin-section]')];
    const panels = [...workspace.querySelectorAll('.admin-section[id]')];
    const valid = new Set(panels.map(p => p.id));
    const show = (id,scroll=false) => {
      const activeId=valid.has(id)?id:'appointments';
      panels.forEach(panel => {
        const active=panel.id===activeId;
        panel.classList.toggle('is-active',active);
        panel.hidden=!active;
      });
      links.forEach(link => {
        const active=link.dataset.adminSection===activeId;
        link.classList.toggle('is-active',active);
        if (active) link.setAttribute('aria-current','page');
        else link.removeAttribute('aria-current');
      });
      if(scroll && window.innerWidth<=920) workspace.scrollIntoView({behavior:'smooth',block:'start'});
    };
    workspace.classList.add('admin-enhanced');
    show(location.hash.slice(1));
    links.forEach(link => link.addEventListener('click',event => {
      event.preventDefault();
      const id=link.dataset.adminSection;
      history.replaceState(null,'','#'+id);
      show(id,true);
    }));
    window.addEventListener('hashchange',()=>show(location.hash.slice(1)));
    const query=workspace.querySelector('#customer-table-search');
    if(query) {
      const rows=[...workspace.querySelectorAll('[data-customer-row]')];
      const filter=()=>rows.forEach(row=>{row.hidden=!row.textContent.toLowerCase().includes(query.value.trim().toLowerCase());});
      query.addEventListener('input',filter);
    }
  }

  // Customer registration lets each visitor incrementally describe their garage.
  const addVehicle=document.querySelector('#add-signup-vehicle');
  if(addVehicle){
    addVehicle.addEventListener('click',()=>{
      const list=document.querySelector('#signup-vehicles');
      if(!list || list.children.length>=6) return;
      const row=list.firstElementChild.cloneNode(true);
      row.querySelectorAll('input').forEach(input=>input.value='');
      list.appendChild(row);
      addVehicle.disabled=list.children.length>=6;
    });
  }


  // Customer self-service rescheduling reuses the authoritative server availability endpoint.
  document.querySelectorAll('.customer-reschedule').forEach(form => {
    const day=form.querySelector('[name=day]');
    const times=form.querySelector('[name=at_time]');
    const feedback=form.querySelector('[data-reschedule-feedback]');
    let controller=null;
    async function update(){
      controller?.abort();
      const next=new AbortController();
      controller=next;
      times.replaceChildren(new Option('Checking availability...', ''));
      feedback.textContent='Loading available times...';
      if(!day.value)return;
      try{
        const url='/api/availability?service_id='+encodeURIComponent(form.dataset.serviceId)+'&day='+encodeURIComponent(day.value);
        const response=await fetch(url,{signal:next.signal});
        if(!response.ok)throw new Error('Unavailable');
        const payload=await response.json();
        if(controller!==next)return;
        times.replaceChildren(new Option(payload.slots.length?'Select an available time':'No available times',''));
        payload.slots.forEach(time=>times.add(new Option(time,time)));
        feedback.textContent=payload.slots.length?'Choose one of '+payload.slots.length+' available times.':'No slots available. Select a different date.';
      }catch(error){
        if(error.name!=='AbortError'){
          times.replaceChildren(new Option('Unable to load times',''));
          feedback.textContent='Could not check availability. Please retry.';
        }
      }
    }
    day.addEventListener('change',update);
    form.addEventListener('submit',event=>{
      if(!times.value){event.preventDefault();times.focus();}
    });
    update();
  });

  const booking=document.querySelector('#booking-form');
  if(!booking) return;
  const service=booking.querySelector('#service-choice');
  const date=booking.querySelector('#appointment-day');
  const slots=booking.querySelector('#slots');
  const slotLabel=booking.querySelector('#slots-label');
  const selected=booking.querySelector('#at-time');
  const stages=[...booking.querySelectorAll('[data-book-step]')];
  const steps=[...document.querySelectorAll('[data-progress]')];
  const submit=booking.querySelector('#book-submit');
  let currentStep=0, controller=null;

  function showStep(index) {
    currentStep=Math.min(3,Math.max(0,index));
    stages.forEach((stage,i)=>{
      const active=i===currentStep;
      stage.classList.toggle('is-current',active);
      stage.setAttribute('aria-hidden',String(!active));
    });
    steps.forEach((step,i)=>{
      step.classList.toggle('is-current',i===currentStep);
      step.classList.toggle('is-done',i<currentStep);
      if(i===currentStep) step.setAttribute('aria-current','step');
      else step.removeAttribute('aria-current');
    });
    if(currentStep===3) refreshReview();
    document.querySelector('.booking-heading')?.scrollIntoView({behavior:'smooth',block:'start'});
  }

  function resetSlots(message) {
    selected.value='';
    slots.replaceChildren();
    const msg=document.createElement('p');
    msg.className='muted';
    msg.textContent=message;
    slots.appendChild(msg);
  }
  async function loadSlots(){
    controller?.abort();
    controller=null;
    resetSlots('Select a service and date to see available times.');
    slotLabel.textContent='Select a service and date';
    if(!service.value || !date.value) return;
    controller=new AbortController();
    const myController=controller;
    resetSlots('Checking available times...');
    slotLabel.textContent='Loading...';
    try{
      const response=await fetch('/api/availability?service_id='+encodeURIComponent(service.value)+'&day='+encodeURIComponent(date.value),{signal:myController.signal});
      if(!response.ok) throw Error('Availability unavailable');
      const result=await response.json();
      if(controller!==myController) return;
      slotLabel.textContent=result.slots.length+' time'+(result.slots.length===1?'':'s')+' available';
      slots.replaceChildren();
      if(!result.slots.length){resetSlots('No available times on this date. Choose another day.');return;}
      result.slots.forEach(time=>{
        const button=document.createElement('button');
        button.type='button';
        button.className='slot-button';
        button.textContent=time;
        button.setAttribute('aria-pressed','false');
        button.addEventListener('click',()=>{
          slots.querySelectorAll('button').forEach(b=>{
            b.classList.remove('selected');
            b.setAttribute('aria-pressed','false');
          });
          button.classList.add('selected');
          button.setAttribute('aria-pressed','true');
          selected.value=time;
          slotLabel.textContent='Selected '+time;
        });
        slots.appendChild(button);
      });
    }catch(error){
      if(error.name!=='AbortError') {
        resetSlots('We could not load availability. Please retry or choose a different day.');
        slotLabel.textContent='Unable to load';
      }
    }
  }

  function validateStep(index){
    if(index===1 && !selected.value){
      slotLabel.textContent='Choose an available time before continuing';
      slots.focus?.();
      return false;
    }
    const fields=[...stages[index].querySelectorAll('input, select, textarea')];
    for(const field of fields){
      if(field.type==='hidden') continue;
      if(!field.checkValidity()){
        field.reportValidity();
        field.focus();
        return false;
      }
    }
    return true;
  }
  function refreshReview() {
    const get=(q)=>booking.querySelector(q);
    const selection=service.options[service.selectedIndex];
    const saved=get('#saved-vehicle-choice');
    const vehicle=get('[name=vehicle]');
    const parts={
      service:selection?.textContent||'Not selected',
      day:date.value||'Not selected',
      time:selected.value||'Not selected',
      name:get('[name=name]')?.value||'Not provided',
      vehicle:(saved?.selectedOptions[0]?.value?saved.selectedOptions[0].textContent:vehicle?.value)||'Not provided'
    };
    for(const [key,value] of Object.entries(parts)){
      const target=get('[data-review="'+key+'"]');
      if(target) target.textContent=value;
    }
  }
  booking.querySelectorAll('[data-book-next]').forEach(button=>button.addEventListener('click',()=>{
    if(validateStep(currentStep)) showStep(currentStep+1);
  }));
  booking.querySelectorAll('[data-book-back]').forEach(button=>button.addEventListener('click',()=>showStep(currentStep-1)));
  service.addEventListener('change',loadSlots);
  date.addEventListener('change',loadSlots);
  const saved=booking.querySelector('#saved-vehicle-choice');
  if(saved)saved.addEventListener('change',()=>{
    const vehicle=booking.querySelector('[name=vehicle]');
    vehicle.disabled=Boolean(saved.value);
    document.querySelector('#vehicle-text-field')?.classList.toggle('is-disabled',Boolean(saved.value));
    if(saved.value)vehicle.value='';
  });
  booking.addEventListener('submit',event=>{
    if(![0,1,2].every(validateStep)){
      event.preventDefault();
      for(let i=0;i<3;i++){if(!validateStep(i)){showStep(i);break;}}
      return;
    }
    submit.disabled=true;
    submit.textContent='Submitting...';
  });
  showStep(0);
  if(service.value && date.value)loadSlots();
})();
