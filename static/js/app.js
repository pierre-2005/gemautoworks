// Small helpers for account and admin pages: confirm before destructive actions, auto-submit filter selects,
// and keep a submit button from being pressed twice.
document.addEventListener('submit', (e) => {
  const f = e.target;
  const msg = f.dataset.confirm;
  if (msg && !window.confirm(msg)) { e.preventDefault(); return; }
  const btn = e.submitter;
  if (btn && f.method.toLowerCase() === 'post') setTimeout(() => { btn.disabled = true; }, 0);
});
for (const f of document.querySelectorAll('form[data-autosubmit]')) {
  f.addEventListener('change', () => f.requestSubmit());
}
const toast = document.querySelector('[data-toast]');
if (toast) setTimeout(() => toast.remove(), 4000);
for (const b of document.querySelectorAll('[data-pw-toggle]')) {
  b.addEventListener('click', () => {
    const input = document.getElementById(b.getAttribute('aria-controls'));
    const show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    b.textContent = show ? 'Hide' : 'Show';
    b.setAttribute('aria-pressed', String(show));
  });
}
