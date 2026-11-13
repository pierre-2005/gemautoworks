(() => {
'use strict';
const reduced = matchMedia('(prefers-reduced-motion: reduce)');
const toggle = document.querySelector('.menu-toggle');
const nav = document.querySelector('#main-nav');
function setMenu(open, restoreFocus = false) {
  if (!toggle || !nav) return;
  toggle.setAttribute('aria-expanded', String(open));
  toggle.setAttribute('aria-label', open ? 'Close navigation menu' : 'Open navigation menu');
  nav.classList.toggle('open', open);
  document.body.classList.toggle('g-menu-open', open);
  if (open) nav.querySelector('a')?.focus({preventScroll:true});
  else if (restoreFocus) toggle.focus({preventScroll:true});
}
if (toggle && nav) {
  toggle.addEventListener('click', () => setMenu(toggle.getAttribute('aria-expanded') !== 'true'));
  nav.querySelectorAll('a').forEach(link => link.addEventListener('click', () => setMenu(false)));
  document.addEventListener('click', event => {
    if (!nav.contains(event.target) && !toggle.contains(event.target) && toggle.getAttribute('aria-expanded') === 'true') setMenu(false);
  });
  document.addEventListener('keydown', event => {
    if (toggle.getAttribute('aria-expanded') !== 'true') return;
    if (event.key === 'Escape') {setMenu(false, true);return;}
    if (event.key !== 'Tab') return;
    const links = [...nav.querySelectorAll('a')];
    const first = links[0], last = links[links.length-1];
    if (!event.shiftKey && document.activeElement === last) {event.preventDefault();toggle.focus();}
    else if (event.shiftKey && document.activeElement === first) {event.preventDefault();toggle.focus();}
    else if (document.activeElement === toggle) {event.preventDefault();(event.shiftKey ? last : first).focus();}
  });
  matchMedia('(min-width: 921px)').addEventListener('change', event => {if(event.matches)setMenu(false);});
}
document.querySelectorAll('[data-confirm]').forEach(el => el.addEventListener('click',e => {
  if (!window.confirm(el.dataset.confirm)) e.preventDefault();
}));
// Mobile navigation and dashboard enhancements are progressive:
// without JavaScript all sections and forms remain accessible.
const dashboard = document.querySelector('.admin-shell');
if (dashboard) {
  const links = [...dashboard.querySelectorAll('[data-admin-section]')];
  const panels = [...dashboard.querySelectorAll('.admin-section[id]')];
  const valid = new Set(panels.map(p => p.id));
  const openPanel = (id, scroll = false) => {
    const target = valid.has(id) ? id : 'appointments';
    panels.forEach(p => {
      const active = p.id === target;
      p.classList.toggle('is-active', active);
      p.setAttribute('aria-hidden', String(!active));
    });
    links.forEach(a => {
      const active = a.dataset.adminSection === target;
      a.classList.toggle('is-active', active);
      if (active) a.setAttribute('aria-current', 'page');
      else a.removeAttribute('aria-current');
    });
    if (scroll && window.innerWidth < 920) {
      dashboard.querySelector('.admin-workspace')?.scrollIntoView({block:'start',behavior:reduced.matches?'instant':'smooth'});
    }
  };
  dashboard.classList.add('admin-enhanced');
  openPanel(location.hash.slice(1));
  links.forEach(link => link.addEventListener('click', e => {
    e.preventDefault();
    history.replaceState(null, '', '#' + link.dataset.adminSection);
    openPanel(link.dataset.adminSection, true);
  }));
  window.addEventListener('hashchange', () => openPanel(location.hash.slice(1)));
}

const gallery = [...document.querySelectorAll('[data-gallery-src]')];
const dialog = document.querySelector('#gallery-dialog');
if (dialog && gallery.length) {
  let index=0, opener=null;
  const image=document.querySelector('#gallery-full');
  function show(next) {
    index=(next+gallery.length)%gallery.length;
    image.src=gallery[index].dataset.gallerySrc;
    image.alt=gallery[index].dataset.galleryAlt || 'Automotive gallery photograph';
    document.querySelector('#gallery-position').textContent=(index+1)+' / '+gallery.length;
  }
  gallery.forEach((button,i)=>button.addEventListener('click',()=>{
    opener=button;show(i);dialog.showModal();
  }));
  document.querySelector('[data-gallery-prev]').addEventListener('click',()=>show(index-1));
  document.querySelector('[data-gallery-next]').addEventListener('click',()=>show(index+1));
  dialog.addEventListener('keydown',event=>{
    if(event.key==='ArrowRight'){event.preventDefault();show(index+1);}
    if(event.key==='ArrowLeft'){event.preventDefault();show(index-1);}
  });
  dialog.addEventListener('click',event=>{
    if(event.target!==dialog)return;
    const rect=dialog.getBoundingClientRect();
    if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)dialog.close();
  });
  dialog.addEventListener('close',()=>opener?.focus());
}
document.querySelectorAll('[data-submit-feedback]').forEach(form=>form.addEventListener('submit',()=>{
  const button=form.querySelector('[type=submit]');
  button.disabled=true;button.textContent='Submitting your review…';
  form.querySelector('[role=status]').textContent='Submitting your review.';
}));

const form = document.querySelector('#booking-form');
if (!form) return;
const service = document.querySelector('#service-choice');
const day = document.querySelector('#appointment-day');
const slots = document.querySelector('#slots');
const label = document.querySelector('#slots-label');
const selected = document.querySelector('#at-time');
const timeError = document.querySelector('#time-error');
const status = document.querySelector('#booking-status');
const submit = document.querySelector('#book-submit');
let controller, requestId=0, sending=false;
function summary() {
  const option=service.selectedOptions[0];
  document.querySelector('#summary-service').textContent=option?.dataset.title || 'Choose an appointment';
  document.querySelector('#summary-duration').textContent=option?.dataset.duration ? option.dataset.duration+' minutes' : '—';
  document.querySelector('#summary-date').textContent=day.value ? new Intl.DateTimeFormat('en',{month:'short',day:'numeric',year:'numeric'}).format(new Date(day.value+'T12:00:00')) : 'Choose a date';
  document.querySelector('#summary-time').textContent=selected.value || 'Choose a time';
  document.querySelector('[data-step="1"]').classList.toggle('is-complete',!!service.value);
  document.querySelector('[data-step="2"]').classList.toggle('is-complete',!!selected.value);
  const detailsReady=form.elements.name.value.trim().length>=2 && form.elements.email.validity.valid && !!form.elements.email.value && form.elements.phone.value.trim().length>=7;
  document.querySelector('[data-step="3"]').classList.toggle('is-complete',detailsReady);
}
function reset(text) {
  slots.replaceChildren();
  const p=document.createElement('p');p.className='muted';p.textContent=text;slots.appendChild(p);
  selected.value='';summary();
}
async function refresh() {
  const ownId=++requestId;
  controller?.abort();
  reset('Choose an appointment and date to see available times.');
  timeError.textContent='';slots.removeAttribute('aria-invalid');slots.removeAttribute('aria-describedby');
  label.textContent='Select an appointment and date';
  if (!service.value || !day.value || !day.validity.valid) return;
  controller=new AbortController();
  reset('Checking the calendar…');
  slots.setAttribute('aria-busy','true');
  label.textContent='Loading times';
  try {
    const response=await fetch('/api/availability?service_id='+encodeURIComponent(service.value)+'&day='+encodeURIComponent(day.value),{signal:controller.signal});
    if (!response.ok) throw Error('Unable to fetch availability');
    const result=await response.json();
    if(ownId!==requestId)return;
    label.textContent=result.slots.length+' available';
    slots.replaceChildren();
    if (!result.slots.length) {reset('No times are available on this date. Choose another date or contact the team.');return;}
    result.slots.forEach(time=>{
      const b=document.createElement('button');
      b.type='button';b.className='slot-button';b.textContent=time;
      b.setAttribute('aria-pressed','false');
      b.addEventListener('click',()=>{
        slots.querySelectorAll('button').forEach(x=>{x.classList.remove('selected');x.setAttribute('aria-pressed','false');});
        b.classList.add('selected');b.setAttribute('aria-pressed','true');selected.value=time;
        timeError.textContent='';slots.removeAttribute('aria-invalid');slots.removeAttribute('aria-describedby');summary();
      });
      slots.appendChild(b);
    });
  } catch(error) {
    if (error.name !== 'AbortError' && ownId===requestId) {
      reset('We couldn’t load available times. Check your connection and try again.');
      label.textContent='Calendar unavailable';
      const retry=document.createElement('button');retry.type='button';retry.className='btn btn-outline';retry.textContent='Try again';retry.addEventListener('click',refresh);slots.appendChild(retry);
    }
  } finally {if(ownId===requestId)slots.removeAttribute('aria-busy');}
}
service.addEventListener('change',refresh);
day.addEventListener('change',refresh);
form.addEventListener('input',summary);
form.addEventListener('submit',async event=>{
  event.preventDefault();
  if(sending)return;
  if (!selected.value) {
    timeError.textContent='Choose an available appointment time before confirming.';
    slots.setAttribute('aria-invalid','true');slots.setAttribute('aria-describedby','time-error');
    slots.focus({preventScroll:true});slots.scrollIntoView({behavior:reduced.matches?'instant':'smooth',block:'center'});return;
  }
  sending=true;submit.disabled=true;submit.setAttribute('aria-busy','true');
  status.textContent='Sending your appointment details…';
  try {
    const response=await fetch(form.action,{method:'POST',body:new FormData(form),headers:{'Accept':'text/html'}});
    if(response.ok && new URL(response.url).searchParams.get('success')==='1') {location.assign(response.url);return;}
    const html=new DOMParser().parseFromString(await response.text(),'text/html');
    const message=html.querySelector('.error-page p')?.textContent;
    if(response.status===409){await refresh();status.textContent='That time was just booked. Your details are saved here; choose another time.';}
    else status.textContent=message || 'We couldn’t complete your booking. Please try again or call the team.';
  } catch(error) {
    status.textContent='The connection was interrupted. Your booking may have been received. Check your email or call the team before trying again.';
  } finally {
    sending=false;submit.disabled=false;submit.removeAttribute('aria-busy');
  }
});
summary();
if (service.value && day.value) refresh();
})();
