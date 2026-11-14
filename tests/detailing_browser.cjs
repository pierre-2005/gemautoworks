/* Run against an isolated local server. PLAYWRIGHT_PATH may point at a bundled runtime. */
const { chromium } = require(process.env.PLAYWRIGHT_PATH || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const base = process.env.GEM_BASE_URL || 'http://127.0.0.1:8765';
const out = path.resolve('visual-artifacts/detailing');
const report = { browsers: [], checks: [], resourceSamples: [] };
async function poster(page) {
  await page.waitForFunction(() => document.querySelector('.g-cleaning-poster img')?.naturalWidth > 0);
}
async function progress(page, fraction) {
  const desired = Math.round(fraction * 159);
  await page.evaluate((fraction) => {
    const root = document.querySelector('[data-car-experience]');
    const nav = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--nav-h'));
    const start = root.getBoundingClientRect().top + scrollY - nav;
    window.scrollTo(0, start + fraction * (root.offsetHeight - innerHeight + nav));
  }, fraction);
  await page.waitForFunction((desired) =>
    Number(document.querySelector('[data-car-experience]').dataset.cleaningFrame) === desired, desired);
}
async function installCounter(context) {
  await context.addInitScript(() => {
    window.__bitmapCount = { live: 0, max: 0 };
    const original = window.createImageBitmap;
    window.createImageBitmap = async (...args) => {
      const bitmap = await original(...args);
      const counter = window.__bitmapCount;
      counter.live++; counter.max = Math.max(counter.max, counter.live);
      const close = bitmap.close.bind(bitmap); let closed = false;
      bitmap.close = () => { if (!closed) { counter.live--; closed = true; close(); } };
      return bitmap;
    };
  });
}
async function standard(browser, channel) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'no-preference' });
  await installCounter(context);
  const page = await context.newPage();
  const errors = []; page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => {
    if (/Content Security Policy|Refused to .*violat/i.test(message.text())) errors.push(message.text());
  });
  const response = await page.goto(base, { waitUntil: 'domcontentloaded' }); await poster(page);
  assert.ok(response.headers()['content-security-policy'].includes("script-src 'self'"));
  await page.waitForSelector('#cleaning-canvas.is-ready');
  assert.equal(await page.locator('a[href="/book"]').count(), 1);
  await page.screenshot({ path: path.join(out, `${channel}-desktop-start.png`) });
  for (const value of [0, .25, .50, .75, .98, .50, .10, .90, .30, 0]) await progress(page, value);
  await progress(page, .72);
  await page.screenshot({ path: path.join(out, `${channel}-desktop-reveal.png`) });
  for (const index of [115, 116, 117]) await progress(page, index / 159);
  const cachedResponseMs = [];
  for (const index of [116, 115, 114, 115, 116]) {
    cachedResponseMs.push(await page.evaluate((index) => new Promise((resolve) => {
      const root = document.querySelector('[data-car-experience]');
      const nav = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--nav-h'));
      const start = performance.now();
      const observer = new MutationObserver(() => {
        if (+root.dataset.cleaningFrame === index) { observer.disconnect(); resolve(performance.now() - start); }
      });
      observer.observe(root, { attributes: true, attributeFilter: ['data-cleaning-frame'] });
      scrollTo(0, root.getBoundingClientRect().top + scrollY - nav + (index / 159) * (root.offsetHeight - innerHeight + nav));
    }), index));
  }
  // Fast jumps must settle on the requested frame, including reverse jumps.
  await page.evaluate(() => { for (let i = 0; i < 40; i++) scrollTo(0, (i % 2) * 900); scrollTo(0, 120); });
  await progress(page, .42);
  const state = await page.evaluate(() => ({
    decoded: Number(document.querySelector('[data-car-experience]').dataset.decodedFrames),
    bitmaps: window.__bitmapCount,
    heap: performance.memory?.usedJSHeapSize,
    overflow: document.documentElement.scrollWidth > innerWidth,
    resources: performance.getEntriesByType('resource').filter((r) => r.name.includes('/static/detailing/'))
      .map((r) => ({ name: r.name.split('/static/detailing/')[1], bytes: r.encodedBodySize, transferBytes: r.transferSize })),
  }));
  assert.ok(state.decoded <= 14); assert.ok(state.bitmaps.max <= 17); assert.equal(state.overflow, false);
  report.resourceSamples.push({ channel, viewport: 'desktop', cachedResponseMs, ...state });
  for (const width of [1024, 768, 390, 360]) {
    await page.setViewportSize({ width, height: width < 700 ? 844 : 900 });
    await progress(page, .70); await poster(page);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.screenshot({ path: path.join(out, `${channel}-${width}.png`) });
  }
  await page.setViewportSize({ width: 1440, height: 900 }); await page.goto(base);
  await page.keyboard.press('Tab');
  assert.equal(await page.evaluate(() => document.activeElement.className), 'skip-link');
  await page.keyboard.press('Enter');
  await page.locator('a[href="/book"]').click(); await page.waitForURL('**/book');
  assert.ok(await page.locator('#booking-form').count());
  assert.equal(await page.locator('#booking-form').evaluate((form) => form.checkValidity()), false);
  const minimum = await page.locator('#appointment-day').getAttribute('min');
  let available;
  for (let offset = 3; offset < 10; offset++) {
    const candidate = new Date(`${minimum}T12:00:00Z`); candidate.setUTCDate(candidate.getUTCDate() + offset);
    const day = candidate.toISOString().slice(0, 10);
    const response = await page.request.get(`${base}/api/availability?day=${day}&service_id=1`);
    const result = await response.json();
    if (result.slots.length) { available = day; break; }
  }
  assert.ok(available, 'Isolated fixture must expose a bookable appointment');
  await page.locator('#service-choice').selectOption('1');
  await page.locator('#appointment-day').fill(available);
  await page.locator('#slots button').first().waitFor();
  await page.locator('[name="name"]').fill('Animation Browser QA');
  await page.locator('[name="phone"]').fill('555-555-5555');
  await page.locator('[name="email"]').fill('customer@example.com');
  await page.locator('#book-submit').click();
  await page.waitForFunction(() => document.querySelector('#time-error')?.textContent.trim().length > 0);
  await page.locator('#slots button').first().click();
  await page.locator('#book-submit').click();
  await page.waitForURL('**/book?success=1&ref=GEM-*');
  assert.ok(await page.locator('.booking-success').isVisible());
  await page.screenshot({ path: path.join(out, `${channel}-booking-confirmation.png`) });
  await page.goto(`${base}/admin/login`);
  await page.locator('[name="email"]').fill('owner@example.com');
  await page.locator('[name="password"]').fill('StrongLocalPreviewPassword-2026');
  await page.locator('button[type="submit"]').click(); await page.waitForURL('**/admin');
  await page.locator('[data-admin-section="settings"]').click();
  assert.ok(await page.locator('#settings').isVisible());
  await page.locator('[data-admin-section="appointments"]').click();
  assert.ok(await page.locator('#appointments').isVisible());
  assert.deepEqual(errors, []);
  report.checks.push(`${channel}: forward, reverse, jumps, resize, overflow, bounded bitmap lifetime, keyboard, availability, validation, booking confirmation and admin navigation`);
  await context.close();
}
async function resilience(browser) {
  let context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, reducedMotion: 'no-preference' });
  const urls = []; context.on('request', (request) => urls.push(request.url()));
  await installCounter(context);
  let page = await context.newPage(); await page.goto(base); await poster(page);
  await progress(page, .7); await page.setViewportSize({ width: 844, height: 390 }); await progress(page, .3);
  assert.equal(await page.locator('[data-car-experience]').getAttribute('data-cleaning-variant'), 'mobile');
  assert.equal(urls.some((url) => url.includes('/static/detailing/desktop/')), false);
  const phoneState = await page.evaluate(() => ({
    decoded: Number(document.querySelector('[data-car-experience]').dataset.decodedFrames),
    bitmaps: window.__bitmapCount, heap: performance.memory?.usedJSHeapSize,
    resources: performance.getEntriesByType('resource').filter((r) => r.name.includes('/static/detailing/'))
      .map((r) => ({ name: r.name.split('/static/detailing/')[1], bytes: r.encodedBodySize, transferBytes: r.transferSize })),
  }));
  assert.ok(phoneState.decoded <= 14); assert.ok(phoneState.bitmaps.max <= 16);
  report.resourceSamples.push({ channel: 'chrome', viewport: 'phone-portrait-landscape', ...phoneState });
  await page.screenshot({ path: path.join(out, 'phone-landscape.png') });
  report.checks.push('Phone portrait and landscape request only mobile frames and poster');
  await context.close();

  context = await browser.newContext({ viewport: { width: 390, height: 844 }, reducedMotion: 'reduce' });
  const reducedUrls = []; context.on('request', (request) => reducedUrls.push(request.url()));
  page = await context.newPage(); await page.goto(base); await poster(page);
  await page.waitForFunction(() => document.querySelector('[data-car-experience]').dataset.cleaningMode === 'static');
  await page.waitForFunction(() => document.querySelector('.g-cleaning-poster img').currentSrc.includes('/finish.webp'));
  assert.equal(reducedUrls.some((url) => /\/\d{3}\.webp/.test(url)), false);
  await page.screenshot({ path: path.join(out, 'reduced-motion.png') });
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.waitForSelector('#cleaning-canvas.is-ready');
  await progress(page, .4);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.waitForFunction(() => !document.querySelector('canvas').classList.contains('is-ready'));
  report.checks.push('Reduced motion loads only a static final poster; live preference changes release frames');
  await context.close();

  context = await browser.newContext({ viewport: { width: 390, height: 844 }, reducedMotion: 'no-preference' });
  await context.addInitScript(() => Object.defineProperty(navigator, 'connection', {
    value: { saveData: true, addEventListener() {} }, configurable: true,
  }));
  const savedDataUrls = []; context.on('request', (request) => savedDataUrls.push(request.url()));
  page = await context.newPage(); await page.goto(base); await poster(page);
  await page.waitForFunction(() => document.querySelector('[data-car-experience]').dataset.cleaningReason === 'preference');
  await page.waitForFunction(() => document.querySelector('.g-cleaning-poster img').currentSrc.includes('/finish.webp'));
  assert.equal(savedDataUrls.some((url) => /\/\d{3}\.webp/.test(url)), false);
  report.checks.push('Save-Data preference keeps the static final picture and avoids sequence downloads');
  await context.close();

  for (const failure of ['frames', 'manifest']) {
    context = await browser.newContext({ reducedMotion: 'no-preference' });
    await context.route(failure === 'frames' ? /\/static\/detailing\/(desktop|mobile)\/\d{3}\.webp/ : '**/static/detailing/manifest.json',
      (route) => route.abort());
    page = await context.newPage(); await page.goto(base); await poster(page);
    await page.waitForFunction(() => document.querySelector('[data-car-experience]').dataset.cleaningMode === 'static');
    await page.waitForFunction(() => document.querySelector('.g-cleaning-poster img').currentSrc.includes('/finish.webp'));
    assert.equal(await page.locator('#cleaning-canvas').evaluate((el) => el.classList.contains('is-ready')), false);
    assert.ok(await page.locator('a[href="/book"]').isVisible());
    report.checks.push(`${failure} failures retain final picture and accessible booking action`);
    await context.close();
  }

  context = await browser.newContext({ reducedMotion: 'no-preference' });
  await context.route('**/static/detailing/**', (route) => route.abort());
  page = await context.newPage(); await page.goto(base); await poster(page);
  await page.waitForFunction(() => document.querySelector('[data-car-experience]').dataset.posterFallback === 'photograph');
  assert.ok(await page.locator('a[href="/book"]').isVisible());
  report.checks.push('Failure of the entire animation directory retains the existing photograph and booking access');
  await context.close();

  context = await browser.newContext({ viewport: { width: 390, height: 844 }, reducedMotion: 'no-preference' });
  await context.route(/\/static\/detailing\/(desktop|mobile)\/\d{3}\.webp/, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 900)); await route.continue();
  });
  page = await context.newPage(); await page.goto(base, { waitUntil: 'domcontentloaded' }); await poster(page);
  assert.ok(await page.locator('a[href="/book"]').isVisible());
  await page.screenshot({ path: path.join(out, 'slow-loading.png') });
  await page.waitForSelector('#cleaning-canvas.is-ready');
  report.checks.push('Delayed sequence requests retain the poster without a blank canvas');
  await context.close();

  context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 844 } });
  page = await context.newPage(); await page.goto(base); await poster(page);
  await page.waitForFunction(() => document.querySelector('.g-cleaning-nojs img')?.naturalWidth > 0);
  assert.ok(await page.locator('a[href="/book"]').isVisible());
  report.checks.push('JavaScript-disabled visitors retain final illustration and booking link');
  await context.close();
}
(async () => {
  await fs.mkdir(out, { recursive: true });
  for (const channel of ['chrome', 'msedge']) {
    const browser = await chromium.launch({ channel, headless: true });
    try {
      report.browsers.push({ name: channel, version: browser.version(), status: 'tested' });
      await standard(browser, channel);
      if (channel === 'chrome') await resilience(browser);
    } finally { await browser.close(); }
  }
  report.browsers.push({ name: 'Firefox', status: 'not available on this host' },
    { name: 'Safari', status: 'not available on Windows; WebKit/Safari was not tested' });
  await fs.writeFile(path.join(out, 'report.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify({ browsers: report.browsers, checks: report.checks }, null, 2));
})().catch(async (error) => {
  report.failure = error.stack; await fs.writeFile(path.join(out, 'report.json'), JSON.stringify(report, null, 2));
  console.error(error); process.exitCode = 1;
});
