(() => {
  'use strict';
  const toggle = document.querySelector('.menu-toggle');
  const nav = document.querySelector('#main-nav');
  if (toggle && nav) {
    toggle.addEventListener('click', () => {
      const open = toggle.getAttribute('aria-expanded') !== 'true';
      toggle.setAttribute('aria-expanded', String(open));
      nav.classList.toggle('open', open);
    });
    nav.querySelectorAll('a').forEach((a) => a.addEventListener('click', () => {
      nav.classList.remove('open'); toggle.setAttribute('aria-expanded', 'false');
    }));
  }
  document.querySelectorAll('[data-confirm]').forEach(el => el.addEventListener('click',e => {
    if (!window.confirm(el.dataset.confirm)) e.preventDefault();
  }));
  const form = document.querySelector('#booking-form');
  if (!form) return;
  const service = document.querySelector('#service-choice');
  const day = document.querySelector('#appointment-day');
  const slots = document.querySelector('#slots');
  const label = document.querySelector('#slots-label');
  const selected = document.querySelector('#at-time');
  let controller;
  function reset(text) {
    slots.replaceChildren();
    const p=document.createElement('p');p.className='muted';p.textContent=text;slots.appendChild(p);
    selected.value='';
  }
  async function refresh() {
    if (controller) controller.abort();
    reset('Select a service and date to see available slots.');
    label.textContent='';
    if (!service.value || !day.value) return;
    controller=new AbortController();
    reset('Loading available times...');
    try {
      const response=await fetch(`/api/availability?service_id=${encodeURIComponent(service.value)}&day=${encodeURIComponent(day.value)}`,{signal:controller.signal});
      if (!response.ok) throw Error('Unable to fetch availability');
      const result=await response.json();
      label.textContent=`${result.slots.length} available`;
      slots.replaceChildren();
      if (!result.slots.length) {reset('No open times for this date. Please try another date.');return;}
      result.slots.forEach(time=>{
        const b=document.createElement('button');
        b.type='button'; b.className='slot-button';b.textContent=time;
        b.setAttribute('aria-pressed','false');
        b.addEventListener('click',()=>{
          slots.querySelectorAll('button').forEach(x=>{x.classList.remove('selected');x.setAttribute('aria-pressed','false');});
          b.classList.add('selected');b.setAttribute('aria-pressed','true');selected.value=time;
        });
        slots.appendChild(b);
      });
    } catch(e) {
      if (e.name !== 'AbortError') reset('Could not load availability. Please try again.');
    }
  }
  service.addEventListener('change',refresh);
  day.addEventListener('change',refresh);
  form.addEventListener('submit',e => {
    if (!selected.value) {e.preventDefault(); slots.scrollIntoView({behavior:'smooth',block:'center'});label.textContent='Please choose an available time';}
  });
  if (service.value && day.value) refresh();
})();
