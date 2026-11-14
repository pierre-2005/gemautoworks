// GEM Autoworks page script: the before/after sliders. Everything else is the kit's (system.js, motion.js, layout.js).

for (const box of document.querySelectorAll('[data-compare]')) {
  const range = box.querySelector('.compare__range');
  if (!range) continue;
  const set = () => box.style.setProperty('--pos', `${range.value}%`);
  range.addEventListener('input', set);
  set();
}
