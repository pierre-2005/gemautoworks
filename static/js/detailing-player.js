/* Original Blender frames. Native scroll, bounded decoding, no animation library. */
const root = document.querySelector('[data-car-experience]');
const canvas = root?.querySelector('canvas');
const context = canvas?.getContext('2d', { alpha: false });
const poster = root?.querySelector('.g-cleaning-poster img');
const stage = root?.querySelector('.g-cleaning-stage');
const originalLabel = stage?.getAttribute('aria-label');
const phone = matchMedia('(max-width: 700px), (max-height: 500px) and (hover: none)');
const posterSources = [...(root?.querySelectorAll('.g-cleaning-poster source') || [])]
  .map((node) => ({ node, srcset: node.getAttribute('srcset') }));
const posterDefault = poster?.getAttribute('src');
let posterEpoch = 0;
function selectPoster(finalPose) {
  if (!poster || root.dataset.posterFallback === 'photograph') return;
  const epoch = ++posterEpoch;
  const url = `/static/detailing/${phone.matches ? 'mobile' : 'desktop'}/${finalPose ? 'finish' : 'poster'}.webp`;
  function apply() {
    if (epoch !== posterEpoch || root.dataset.posterFallback === 'photograph') return;
    for (const source of posterSources) source.node.setAttribute('srcset', finalPose ? url : source.srcset);
    poster.src = finalPose ? url : posterDefault;
  }
  if (poster.complete && poster.naturalWidth && poster.currentSrc !== new URL(url, location.href).href) {
    // Keep the currently decoded picture until its replacement is available.
    const replacement = new Image(); replacement.onload = apply; replacement.src = url;
  } else apply();
}
if (poster) {
  const usePhotograph = () => {
    for (const source of root.querySelectorAll('.g-cleaning-poster source')) source.removeAttribute('srcset');
    poster.src = '/static/img/editorial-drive.webp';
    stage.setAttribute('aria-label', 'Sports-car inspiration. This is not GEM premises or customer work.');
    root.dataset.posterFallback = 'photograph';
  };
  poster.addEventListener('error', usePhotograph, { once: true });
  if (poster.complete && !poster.naturalWidth) usePhotograph();
}
if (root && !context) {
  root.dataset.cleaningMode = 'static';
  root.dataset.cleaningReason = 'unavailable';
  root.querySelector('#cleaning-phase').textContent = 'Finish';
  selectPoster(true);
}
if (root && canvas && context) {
  const motion = matchMedia('(prefers-reduced-motion: reduce)');
  const data = matchMedia('(prefers-reduced-data: reduce)');
  const phase = root.querySelector('#cleaning-phase');
  const images = new Map();
  const pending = new Set();
  const controllers = new Set();
  let manifest, variant, target = 0, painted = -1, generation = 0;
  let tick = 0, active = 0, visible = true, failed = false;
  let queue = [], rect, travel = 1, start = 0;
  const limit = 14;
  const staticMode = () => motion.matches || data.matches || navigator.connection?.saveData;
  const frameUrl = (index) => `${variant.path}${String(index).padStart(3, '0')}.webp`;

  function release() {
    generation++;
    for (const controller of controllers) controller.abort();
    controllers.clear(); pending.clear(); queue = [];
    for (const bitmap of images.values()) bitmap.close?.();
    images.clear(); painted = -1;
    delete root.dataset.cleaningFrame; root.dataset.decodedFrames = '0';
    canvas.classList.remove('is-ready');
  }

  function fallback() {
    failed = true; release();
    root.dataset.cleaningMode = 'static';
    root.dataset.cleaningReason = staticMode() ? 'preference' : 'failure';
    phase.textContent = 'Finish';
    selectPoster(true);
  }

  function trim() {
    while (images.size > limit) {
      // Keep the last displayed bitmap while its requested replacement loads.
      const victim = [...images.keys()].find((index) => index !== painted && index !== target);
      if (victim === undefined) break;
      images.get(victim).close?.(); images.delete(victim);
    }
  }

  function draw() {
    tick = 0;
    if (!images.size || staticMode() || failed || document.hidden) return;
    const index = images.has(target) ? target : [...images.keys()].reduce((a, b) =>
      Math.abs(a - target) < Math.abs(b - target) ? a : b);
    if (painted === index && canvas.classList.contains('is-ready')) return;
    const bitmap = images.get(index);
    images.delete(index); images.set(index, bitmap);
    context.fillStyle = '#0b1116'; context.fillRect(0, 0, canvas.width, canvas.height);
    const scale = Math.min(canvas.width / bitmap.width, canvas.height / bitmap.height);
    const w = bitmap.width * scale, h = bitmap.height * scale;
    context.drawImage(bitmap, (canvas.width - w) / 2, (canvas.height - h) / 2, w, h);
    painted = index; canvas.classList.add('is-ready');
    stage.setAttribute('aria-label', originalLabel);
    root.dataset.cleaningFrame = String(index);
    root.dataset.decodedFrames = String(images.size);
    trim();
  }

  function schedule() { if (!tick) tick = requestAnimationFrame(draw); }

  function enqueue(index) {
    if (index < 0 || index >= manifest.count || images.has(index) || pending.has(index)) return;
    queue = queue.filter((item) => item !== index); queue.push(index);
  }

  function pump() {
    if (staticMode() || failed || !visible || document.hidden) return;
    while (active < (phone.matches ? 2 : 3) && queue.length) {
      const index = queue.shift(), epoch = generation, url = frameUrl(index);
      if (images.has(index) || pending.has(index)) continue;
      const controller = new AbortController(); controllers.add(controller);
      const timeout = setTimeout(() => { if (epoch === generation) fallback(); controller.abort(); }, 12000);
      pending.add(index); active++;
      fetch(url, { signal: controller.signal, credentials: 'same-origin' })
        .then((response) => { if (!response.ok) throw new Error(`Frame ${response.status}`); return response.blob(); })
        .then((blob) => createImageBitmap(blob))
        .then((bitmap) => {
          if (epoch !== generation) { bitmap.close(); return; }
          images.set(index, bitmap); trim(); schedule();
        })
        .catch((error) => { if (epoch === generation && error.name !== 'AbortError') fallback(); })
        .finally(() => {
          clearTimeout(timeout);
          controllers.delete(controller); active--;
          if (epoch === generation) pending.delete(index);
          pump();
        });
    }
  }

  function update() {
    if (!manifest || staticMode() || failed) return;
    const progress = Math.max(0, Math.min(1, (scrollY - start) / travel));
    target = Math.round(progress * (manifest.count - 1));
    const label = progress < .135 ? 'Prepare' : progress < .47 ? 'Wash' :
      progress < .65 ? 'Wipe' : progress < .85 ? 'Reveal' : 'Finish';
    if (phase.textContent !== label) phase.textContent = label;
    // Discard stale queued work after fast jumps. In-flight work stays bounded.
    queue = []; enqueue(target);
    for (let distance = 1; distance <= 3; distance++) { enqueue(target + distance); enqueue(target - distance); }
    if (images.size) { if (tick) cancelAnimationFrame(tick); draw(); }
    else schedule();
    pump();
  }

  function measure() {
    if (!variant) return;
    rect = canvas.getBoundingClientRect();
    const nav = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--nav-h')) || 0;
    start = root.getBoundingClientRect().top + scrollY - nav;
    travel = Math.max(1, root.offsetHeight - innerHeight + nav);
    const fit = Math.min(Math.max(1, rect.width) / variant.width, Math.max(1, rect.height) / variant.height);
    const ratio = Math.min(devicePixelRatio || 1, 1.5, 1 / fit);
    const width = Math.max(1, Math.round(rect.width * ratio));
    const height = Math.max(1, Math.round(rect.height * ratio));
    if (canvas.width !== width) canvas.width = width;
    if (canvas.height !== height) canvas.height = height;
    painted = -1; update();
  }

  function configure() {
    if (!manifest) return;
    failed = false; release();
    variant = manifest.variants[phone.matches ? 'mobile' : 'desktop'];
    root.dataset.cleaningVariant = phone.matches ? 'mobile' : 'desktop';
    root.dataset.cleaningMode = staticMode() ? 'static' : 'sequence';
    root.dataset.cleaningReason = staticMode() ? 'preference' : 'scroll';
    selectPoster(staticMode());
    if (staticMode()) { phase.textContent = 'Finish'; return; }
    measure();
    // Load a few key poses after the current neighbourhood; defer other frames
    // until scrolling approaches them. Phones never request the desktop variant.
    for (const progress of [0, .25, .5, .75, 1]) enqueue(Math.round(progress * (manifest.count - 1)));
    pump();
  }

  let updateTick = 0;
  addEventListener('scroll', () => {
    if (!updateTick) updateTick = requestAnimationFrame(() => { updateTick = 0; update(); });
  }, { passive: true });
  new ResizeObserver(measure).observe(canvas);
  new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; if (visible) update(); },
    { rootMargin: '200px' }).observe(root);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) update(); });
  addEventListener('pagehide', release);
  addEventListener('pageshow', () => { if (manifest) configure(); });
  for (const media of [motion, phone, data]) media.addEventListener('change', configure);
  navigator.connection?.addEventListener('change', configure);
  // Reduced-motion and reduced-data visitors need only the final HTML picture.
  if (staticMode()) {
    root.dataset.cleaningMode = 'static'; root.dataset.cleaningReason = 'preference'; phase.textContent = 'Finish';
    selectPoster(true);
  }
  const manifestController = new AbortController();
  const manifestTimeout = setTimeout(() => manifestController.abort(), 8000);
  fetch('/static/detailing/manifest.json', { credentials: 'same-origin', signal: manifestController.signal })
    .then((response) => { if (!response.ok) throw new Error('Manifest unavailable'); return response.json(); })
    .then((value) => {
      if (!Number.isInteger(value.count) || value.count < 2 || !value.variants?.desktop || !value.variants?.mobile)
        throw new Error('Invalid sequence manifest');
      manifest = value; configure();
    }).catch(fallback).finally(() => clearTimeout(manifestTimeout));
}
