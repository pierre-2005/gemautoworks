(() => {
  'use strict';

  // Accessible mobile navigation. The site still works when scripting is disabled.
  const menu = document.querySelector('.menu-toggle');
  const nav = document.querySelector('#main-nav');
  const closeMenu = () => {
    if (!menu || !nav) return;
    nav.classList.remove('open');
    menu.setAttribute('aria-expanded', 'false');
    menu.setAttribute('aria-label', 'Open navigation menu');
  };
  if (menu && nav) {
    menu.addEventListener('click', () => {
      const open = menu.getAttribute('aria-expanded') !== 'true';
      nav.classList.toggle('open', open);
      menu.setAttribute('aria-expanded', String(open));
      menu.setAttribute('aria-label', open ? 'Close navigation menu' : 'Open navigation menu');
    });
    nav.querySelectorAll('a').forEach(a => a.addEventListener('click', closeMenu));
    document.addEventListener('keydown', e => { if (e.key === 'Escape') closeMenu(); });
    document.addEventListener('click', e => {
      if (!nav.contains(e.target) && !menu.contains(e.target)) closeMenu();
    });
  }

  document.querySelectorAll('[data-confirm]').forEach(el => el.addEventListener('click', e => {
    if (!window.confirm(el.dataset.confirm)) e.preventDefault();
  }));

  // Admin tabs: navigate between independently functioning forms, preserve URL hashes.
  const dashboard = document.querySelector('.admin-shell');
  if (dashboard) {
    const links = [...dashboard.querySelectorAll('[data-admin-section]')];
    const panels = [...dashboard.querySelectorAll('.admin-section[id]')];
    const valid = new Set(panels.map(p => p.id));
    const showPanel = (id, scroll = false) => {
      const target = valid.has(id) ? id : 'appointments';
      panels.forEach(panel => {
        const active = panel.id === target;
        panel.classList.toggle('is-active', active);
        panel.hidden = !active;
      });
      links.forEach(link => {
        const active = link.dataset.adminSection === target;
        link.classList.toggle('is-active', active);
        if (active) link.setAttribute('aria-current', 'page');
        else link.removeAttribute('aria-current');
      });
      if (scroll && window.innerWidth < 920) {
        dashboard.querySelector('.admin-workspace')?.scrollIntoView({block:'start',behavior:'smooth'});
      }
    };
    dashboard.classList.add('admin-enhanced');
    showPanel(location.hash.slice(1));
    links.forEach(link => link.addEventListener('click', e => {
      e.preventDefault();
      history.replaceState(null, '', '#' + link.dataset.adminSection);
      showPanel(link.dataset.adminSection, true);
    }));
    window.addEventListener('hashchange', () => showPanel(location.hash.slice(1)));
  }

  // Gallery lightbox: native dialog handles focus containment and Escape.
  const lightbox = document.querySelector('#gallery-lightbox');
  if (lightbox && typeof lightbox.showModal === 'function') {
    const photo = lightbox.querySelector('img');
    const caption = lightbox.querySelector('.lightbox-caption');
    document.querySelectorAll('[data-lightbox-src]').forEach(button => {
      button.addEventListener('click', () => {
        photo.src = button.dataset.lightboxSrc;
        photo.alt = button.dataset.lightboxAlt || '';
        caption.textContent = button.closest('figure')?.querySelector('figcaption span')?.textContent || '';
        lightbox.showModal();
      });
    });
    lightbox.querySelector('.lightbox-close')?.addEventListener('click', () => lightbox.close());
    lightbox.addEventListener('click', e => { if (e.target === lightbox) lightbox.close(); });
    lightbox.addEventListener('close', () => { photo.removeAttribute('src'); photo.alt = ''; });
  }

  // Booking: only the client presentation is new. Slot validation and reservation
  // transaction are still authoritative on the server.
  const form = document.querySelector('#booking-form');
  if (!form) return;
  const service = form.querySelector('#service-choice');
  const day = form.querySelector('#appointment-day');
  const slots = form.querySelector('#slots');
  const label = form.querySelector('#slots-label');
  const selected = form.querySelector('#at-time');
  const preview = form.querySelector('#service-preview');
  const warning = form.querySelector('#booking-form-error');
  const stages = [...form.querySelectorAll('[data-book-step]')];
  const progress = [...document.querySelectorAll('[data-progress]')];
  let current = 1;
  let controller = null;
  let sequence = 0;

  function warn(message) {
    if (!warning) return;
    warning.textContent = message;
    warning.hidden = !message;
  }
  function showStep(n) {
    current = Math.max(1, Math.min(stages.length, n));
    stages.forEach(stage => { stage.hidden = Number(stage.dataset.bookStep) !== current; });
    progress.forEach(item => {
      const index = Number(item.dataset.progress);
      item.classList.toggle('is-current', index === current);
      item.classList.toggle('is-complete', index < current);
      if (index === current) item.setAttribute('aria-current', 'step');
      else item.removeAttribute('aria-current');
    });
    warn('');
    const title = stages[current - 1]?.querySelector('h3');
    if (title) { title.setAttribute('tabindex', '-1'); title.focus({preventScroll:true}); }
    if (window.matchMedia('(max-width: 900px)').matches) {
      document.querySelector('.booking-panel')?.scrollIntoView({block:'start',behavior:'smooth'});
    }
  }
  function resetSlots(text) {
    slots.replaceChildren();
    const p = document.createElement('p');
    p.className = 'muted';
    p.textContent = text;
    slots.appendChild(p);
    selected.value = '';
  }
  function refreshPreview() {
    const option = service.selectedOptions[0];
    preview.textContent = service.value
      ? option.textContent + (option.dataset.note ? ' · ' + option.dataset.note : '')
      : 'Select a service to see its appointment details.';
  }
  async function refresh() {
    sequence += 1;
    const requestNumber = sequence;
    if (controller) controller.abort();
    resetSlots('Select an appointment and date to see available times.');
    label.textContent = 'Choose a date';
    if (!service.value || !day.value) return;
    controller = new AbortController();
    resetSlots('Looking for available times...');
    label.textContent = 'Loading…';
    try {
      const params = new URLSearchParams({service_id:service.value,day:day.value});
      const response = await fetch('/api/availability?' + params.toString(), {signal:controller.signal});
      if (!response.ok) throw new Error('Unable to load availability');
      const result = await response.json();
      if (requestNumber !== sequence) return;
      const available = Array.isArray(result.slots) ? result.slots : [];
      label.textContent = available.length + ' available';
      slots.replaceChildren();
      if (!available.length) { resetSlots('No open times on this date. Please choose another date.'); return; }
      available.forEach(time => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'slot-button';
        button.textContent = time;
        button.setAttribute('aria-pressed', 'false');
        button.addEventListener('click', () => {
          slots.querySelectorAll('button').forEach(b => {
            b.classList.remove('selected');
            b.setAttribute('aria-pressed', 'false');
          });
          button.classList.add('selected');
          button.setAttribute('aria-pressed', 'true');
          selected.value = time;
          label.textContent = 'Time selected';
          warn('');
        });
        slots.appendChild(button);
      });
    } catch(error) {
      if (error.name !== 'AbortError' && requestNumber === sequence) {
        label.textContent = 'Unavailable';
        resetSlots('Availability could not be loaded. Please try again.');
      }
    }
  }
  function validateStep(number) {
    if (number === 2 && !selected.value) {
      warn('Please choose an available appointment time.');
      slots.scrollIntoView({block:'center',behavior:'smooth'});
      return false;
    }
    const stage = stages[number - 1];
    for (const field of stage.querySelectorAll('input:not([type=hidden]), select, textarea')) {
      if (!field.checkValidity()) {
        warn('Please complete the required fields to continue.');
        field.reportValidity();
        return false;
      }
    }
    return true;
  }
  function updateSummary() {
    const summary = key => form.querySelector('[data-summary="' + key + '"]');
    const value = name => form.elements.namedItem(name)?.value?.trim() || '';
    summary('service').textContent = service.selectedOptions[0]?.textContent || 'Not selected';
    summary('date').textContent = day.value || 'Not selected';
    summary('time').textContent = selected.value || 'Not selected';
    summary('name').textContent = value('name') || 'Not provided';
    summary('contact').textContent = [value('email'),value('phone')].filter(Boolean).join(' · ') || 'Not provided';
    summary('vehicle').textContent = value('vehicle') || 'Not provided';
  }
  service.addEventListener('change', () => { refreshPreview(); refresh(); });
  day.addEventListener('change', refresh);
  refreshPreview();

  if (stages.length === 4) {
    form.classList.add('has-booking-wizard');
    // Keep HTML's step-by-step validation controlled, including hidden stages.
    stages.forEach(stage => {
      stage.querySelector('[data-book-next]')?.addEventListener('click', () => {
        if (!validateStep(current)) return;
        if (current === 3) updateSummary();
        showStep(current + 1);
      });
      stage.querySelector('[data-book-prev]')?.addEventListener('click', () => showStep(current - 1));
    });
    showStep(1);
  }
  form.addEventListener('submit', e => {
    for (let step = 1; step <= 3; step += 1) {
      if (!validateStep(step)) {
        e.preventDefault();
        if (stages.length === 4) showStep(step);
        return;
      }
    }
    const submit = form.querySelector('#book-submit');
    if (submit) { submit.disabled = true; submit.textContent = 'Submitting your appointment…'; }
  });
})();