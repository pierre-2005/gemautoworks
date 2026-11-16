// Booking page: live estimate, open days and start times. The form also works without this script
// (the server re-renders with times for the chosen day), so every step here is an enhancement.

const form = document.querySelector('[data-book]');
if (form) init(form);

function init(form) {
  const $ = (s, el = form) => el.querySelector(s);
  const $$ = (s, el = form) => [...el.querySelectorAll(s)];
  const money = (c) => (c % 100 === 0 ? `$${(c / 100).toLocaleString()}` : `$${(c / 100).toFixed(2)}`);
  const sizeLabel = { sedan: 'Sedan or coupe', suv: 'SUV or crossover', truck: 'Large SUV or truck' };
  const daysBox = $('[data-days]');
  const timesBox = $('[data-times]');
  const dayInput = $('[data-day-input]');
  let lastKey = '';

  const val = (name) => (form.querySelector(`[name="${name}"]:checked`) || {}).value || '';
  const service = () => form.querySelector('[name="service"]:checked');
  const vehicleRadio = () => form.querySelector('[name="vehicle_id"]:checked');
  const size = () => {
    const v = vehicleRadio();
    return v && v.value ? v.dataset.size : val('size');
  };
  const addons = () => $$('[name="addons"]:checked').map((i) => i.value).join(',');

  function showNewCar() {
    const v = vehicleRadio();
    const box = $('[data-new-car]');
    if (box && v !== null) box.hidden = Boolean(v && v.value);
  }

  function showWhere() {
    const mobile = $('[data-where-mobile]');
    if (!mobile) return;
    const t = val('location_type') || (form.querySelector('[name="location_type"]') || {}).value;
    mobile.hidden = t === 'shop';
    const sel = $('[data-address-select]');
    const fresh = $('[data-new-address]');
    if (sel && fresh) fresh.hidden = sel.value !== '';
  }

  function sizePrices() {
    const s = service();
    if (!s) return;
    const prices = JSON.parse(s.dataset.prices || '{}');
    for (const el of $$('[data-size-price]')) {
      const p = prices[el.dataset.sizePrice];
      el.textContent = p ? `${money(p.cents)} · about ${fmtHours(p.minutes)}` : '';
    }
  }

  const fmtHours = (m) => {
    const h = Math.round((m / 60) * 2) / 2;
    return h === 1 ? '1 hour' : `${h} hours`;
  };

  function ticket(q) {
    const s = service();
    $('[data-t-service]').textContent = s ? s.dataset.name : 'Choose a package';
    const v = vehicleRadio();
    let car = '–';
    if (v && v.value) car = v.closest('.choice').querySelector('.choice__title').textContent;
    else {
      const parts = [$('#b-year')?.value, $('#b-make')?.value, $('#b-model')?.value].filter(Boolean).join(' ');
      car = parts || (size() ? sizeLabel[size()] : '–');
    }
    $('[data-t-car]').textContent = car;
    const t = val('location_type') || (form.querySelector('[name="location_type"]') || {}).value;
    let where = t === 'shop' ? 'Drop-off at the shop' : 'We come to you';
    if (t !== 'shop') {
      const sel = $('[data-address-select]');
      const st = $('#b-street')?.value, town = $('#b-town')?.value;
      if (sel && sel.value) where = sel.options[sel.selectedIndex].text.split(': ').slice(1).join(': ');
      else if (st || town) where = [st, town].filter(Boolean).join(', ');
    }
    $('[data-t-where]').textContent = where;
    const day = dayInput.value, time = val('time');
    if (day) {
      const d = new Date(`${day}T12:00:00`);
      const label = d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
      const tl = time ? form.querySelector(`[name="time"][value="${time}"]`)?.nextElementSibling?.textContent : '';
      $('[data-t-when]').textContent = tl ? `${label}, ${tl}` : `${label}, pick a time`;
    } else $('[data-t-when]').textContent = '–';
    if (q) {
      $('[data-t-duration]').textContent = q.duration;
      $('[data-t-price]').textContent = q.price;
      $('[data-t-total]').textContent = q.total;
      const row = $('[data-t-offer-row]');
      row.hidden = !q.discount;
      if (q.discount) $('[data-t-discount]').textContent = `−${q.discount}`;
    }
  }

  async function refresh() {
    showNewCar();
    showWhere();
    sizePrices();
    const s = service(), z = size();
    if (!s || !z) { ticket(null); return; }
    const email = $('#b-email')?.value || '';
    const key = `${s.value}|${z}|${addons()}`;
    try {
      const q = await (await fetch(`/api/quote?service=${s.value}&size=${z}&addons=${addons()}&email=${encodeURIComponent(email)}`)).json();
      ticket(q.error ? null : q);
    } catch { ticket(null); }
    if (key !== lastKey) { lastKey = key; loadDays(s.value, z); }
  }

  async function loadDays(sid, z) {
    daysBox.innerHTML = '<p class="empty">Loading open days…</p>';
    let data;
    try { data = await (await fetch(`/api/days?service=${sid}&size=${z}&addons=${addons()}`)).json(); }
    catch { daysBox.innerHTML = '<p class="empty">Open days could not load. Check your connection and try again.</p>'; return; }
    const open = data.days.filter((d) => d.count > 0);
    if (!open.length) {
      daysBox.innerHTML = '<p class="empty">No open times in the next weeks for this package. Call or text us and we will find one.</p>';
      timesBox.innerHTML = '';
      return;
    }
    const frag = document.createElement('div');
    let month = '';
    let grid;
    for (const d of data.days) {
      const dt = new Date(`${d.day}T12:00:00`);
      const m = dt.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
      if (m !== month) {
        month = m;
        const h = document.createElement('p'); h.className = 'month-label'; h.textContent = m; frag.append(h);
        grid = document.createElement('div'); grid.className = 'days'; grid.setAttribute('role', 'radiogroup'); grid.setAttribute('aria-label', `Days in ${m}`);
        for (const n of ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']) { const s = document.createElement('span'); s.className = 'days__dow'; s.textContent = n; s.setAttribute('aria-hidden', 'true'); grid.append(s); }
        const pad = (dt.getDay() + 6) % 7;
        for (let p = 0; p < pad; p++) { const b = document.createElement('span'); b.className = 'day day--blank'; grid.append(b); }
        frag.append(grid);
      }
      const lab = document.createElement('label'); lab.className = 'day';
      const inp = document.createElement('input'); inp.type = 'radio'; inp.name = 'day_pick'; inp.value = d.day; inp.disabled = d.count === 0;
      inp.setAttribute('aria-label', `${dt.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}${d.count ? `, ${d.count} start times` : ', no open times'}`);
      if (d.day === dayInput.value) inp.checked = true;
      const sp = document.createElement('span'); sp.innerHTML = `${dt.getDate()}<small>${d.count ? (d.count > 3 ? 'open' : `${d.count} left`) : ''}</small>`;
      lab.append(inp, sp); grid.append(lab);
    }
    daysBox.replaceChildren(frag);
    if (dayInput.value && !open.find((d) => d.day === dayInput.value)) { dayInput.value = ''; timesBox.innerHTML = ''; }
    if (dayInput.value) loadTimes(dayInput.value);
  }

  async function loadTimes(day) {
    const s = service(), z = size();
    if (!s || !z) return;
    const keep = val('time');
    timesBox.innerHTML = '<p class="empty">Loading times…</p>';
    let data;
    try { data = await (await fetch(`/api/slots?service=${s.value}&size=${z}&day=${day}&addons=${addons()}`)).json(); }
    catch { timesBox.innerHTML = '<p class="empty">Times could not load. Try again.</p>'; return; }
    if (!data.times.length) { timesBox.innerHTML = '<p class="empty">That day just filled up. Pick another day.</p>'; return; }
    const head = document.createElement('p'); head.className = 'field__legend'; head.textContent = `Start times on ${data.label}`;
    const grid = document.createElement('div'); grid.className = 'times'; grid.setAttribute('role', 'radiogroup'); grid.setAttribute('aria-label', head.textContent);
    for (const t of data.times) {
      const lab = document.createElement('label'); lab.className = 'day';
      const inp = document.createElement('input'); inp.type = 'radio'; inp.name = 'time'; inp.value = t.value; if (t.value === keep) inp.checked = true;
      const sp = document.createElement('span'); sp.textContent = t.label;
      lab.append(inp, sp); grid.append(lab);
    }
    timesBox.replaceChildren(head, grid);
    ticket(null);
    refreshTicketOnly();
  }

  async function refreshTicketOnly() {
    const s = service(), z = size();
    if (!s || !z) return ticket(null);
    try { ticket(await (await fetch(`/api/quote?service=${s.value}&size=${z}&addons=${addons()}&email=${encodeURIComponent($('#b-email')?.value || '')}`)).json()); } catch { /* the estimate stays as it was */ }
  }

  form.addEventListener('change', (e) => {
    const n = e.target.name;
    if (n === 'day_pick') { dayInput.value = e.target.value; loadTimes(e.target.value); return; }
    if (n === 'time' || n === 'location_type' || e.target.matches('[data-address-select]')) { showWhere(); refreshTicketOnly(); return; }
    if (n === 'email') { refreshTicketOnly(); return; }
    refresh();
  });
  form.addEventListener('input', (e) => { if (['year', 'make', 'model', 'street', 'town'].includes(e.target.name)) ticket(null) || refreshTicketOnly(); });

  form.addEventListener('submit', (e) => {
    // light check before the round trip; the server checks everything again
    const missing = [];
    if (!service()) missing.push('#step-package');
    if (!size()) missing.push('#step-car');
    if (!dayInput.value || !val('time')) missing.push('#step-time');
    if (missing.length) {
      e.preventDefault();
      const target = form.querySelector(missing[0]);
      target.scrollIntoView({ block: 'start' });
      const status = document.createElement('p');
      status.className = 'notice notice--bad'; status.setAttribute('role', 'alert');
      status.textContent = missing[0] === '#step-package' ? 'Choose a package first.' : missing[0] === '#step-car' ? 'Choose your car or its size.' : 'Pick a day and a start time.';
      form.querySelector('.inline-alert')?.remove();
      status.classList.add('inline-alert');
      target.append(status);
      const btn = form.querySelector('[type="submit"]');
      btn.blur();
      return;
    }
    const btn = form.querySelector('aside [type="submit"]');
    setTimeout(() => { btn.disabled = true; btn.textContent = 'Booking…'; }, 0);
  });

  document.getElementById('book-errors')?.focus();
  refresh();
}
