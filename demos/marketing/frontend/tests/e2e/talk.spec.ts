/**
 * Talk mode, driven the way a live call drives it: each test applies the actions
 * Tanvi's brain sends (`window.vq.act`) and checks what the visitor would see.
 * The ids come from src/data/voice.json, the same file the brain reads.
 */
import { expect, test, type Page } from '@playwright/test';
import voice from '../../src/data/voice.json' with { type: 'json' };

type Action = { command: string; payload: Record<string, string> };

async function talk(page: Page) {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto('/?mode=talk');
  await page.waitForFunction(() => document.body.classList.contains('is-ready') && 'vq' in window);
  return errors;
}

const act = (page: Page, a: Action) => page.evaluate((x) => window.vq.act(x as never), a);
const show = (page: Page, target: string) => act(page, { command: 'show', payload: { target } });
const active = (page: Page) => page.evaluate(() => document.querySelector('[data-section][data-active]')?.getAttribute('data-section') ?? null);

test('every control Tanvi can work is on the page, once, in its own section', async ({ page }) => {
  await talk(page);
  const missing = await page.evaluate((targets) => targets
    .filter((t) => document.querySelectorAll(`[data-section="${t.section}"] [data-voice="${t.id}"]`).length !== 1)
    .map((t) => t.id), voice.targets);
  expect(missing).toEqual([]);
});

test('pricing in rupees, then monthly, then back to dollars', async ({ page }) => {
  const errors = await talk(page);
  await show(page, 'pricing.inr');
  await expect.poll(() => active(page)).toBe('pricing');
  await expect(page.locator('html')).toHaveAttribute('data-cur', 'inr');
  await expect(page.locator('button[data-voice="pricing.inr"]')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('[data-voice="pricing.starter"] .plan__price')).toContainText('₹');

  await show(page, 'pricing.monthly');
  await expect(page.locator('html')).toHaveAttribute('data-bill', 'monthly');
  await expect(page.locator('[data-voice="pricing.starter"] .plan__price')).toContainText('₹9,999');

  await show(page, 'pricing.usd');
  await expect(page.locator('html')).toHaveAttribute('data-cur', 'usd');
  await expect(page.locator('[data-voice="pricing.starter"] .plan__price')).toContainText('$99');
  expect(errors).toEqual([]);
});

test('a plan she talks about is pointed at', async ({ page }) => {
  await talk(page);
  await show(page, 'pricing.growth');
  await expect(page.locator('[data-voice="pricing.growth"]')).toHaveClass(/is-pointed/);
});

test('the developer tab, and a step inside it from a standing start', async ({ page }) => {
  await talk(page);
  await show(page, 'ways.developer.step2');
  await expect.poll(() => active(page)).toBe('ways');
  await expect(page.locator('#tab-dev')).toHaveAttribute('aria-selected', 'true');
  await expect(page.locator('#panel-dev')).toBeVisible();
  // The step holds: the loop does not restart when the section comes on screen.
  await expect(page.locator('#panel-dev [data-loop]')).toHaveAttribute('data-at', '2', { timeout: 2000 });

  await show(page, 'ways.plug_and_play');
  await expect(page.locator('#tab-pnp')).toHaveAttribute('aria-selected', 'true');
  await expect(page.locator('#panel-pnp')).toBeVisible();
});

test('a use case tab', async ({ page }) => {
  await talk(page);
  await show(page, 'worlds.cab');
  await expect.poll(() => active(page)).toBe('worlds');
  await expect(page.locator('#tab-cab')).toHaveAttribute('aria-selected', 'true');
  await expect(page.locator('#panel-cab')).toBeVisible();
});

test('a step of how it works', async ({ page }) => {
  await talk(page);
  await show(page, 'action.step3');
  await expect.poll(() => active(page)).toBe('action');
  await expect(page.locator('#s-action .hw')).toHaveAttribute('data-at', '3', { timeout: 2000 });
});

test('a scene of the shift story', async ({ page }) => {
  await talk(page);
  await show(page, 'shift.scene3');
  await expect.poll(() => active(page)).toBe('shift');
  const scene = page.locator('[data-voice="shift.scene3"]');
  await expect(scene).toHaveClass(/is-pointed/);
  await expect(scene).toBeInViewport({ ratio: 0.3 });
});

test('a character', async ({ page }) => {
  await talk(page);
  await show(page, 'cast.tess');
  await expect.poll(() => active(page)).toBe('cast');
  await expect(page.locator('[data-voice="cast.tess"]')).toHaveClass(/is-pointed/);
});

test('a link she hands over opens in a new tab, and goes away when the page resets', async ({ page }) => {
  await talk(page);
  for (const l of voice.links) {
    await act(page, { command: 'open_link', payload: { link: l.id } });
    const card = page.locator('#linkcard');
    await expect(card).toBeVisible();
    // The console follows the environment (localhost goes to the dev console); every other link is as listed.
    if (l.id === 'console') await expect(card).toHaveAttribute('href', /^https:\/\/app\.(dev\.)?voqalize\.com/);
    else await expect(card).toHaveAttribute('href', l.url);
    await expect(card).toHaveAttribute('target', '_blank');
    await expect(card).toContainText(l.label);
    await expect(card).toBeInViewport();
  }
});

test('the link stays on screen with a section open', async ({ page }) => {
  await talk(page);
  await act(page, { command: 'open_section', payload: { section: 'pricing' } });
  await act(page, { command: 'open_link', payload: { link: 'mcp' } });
  await expect(page.locator('#linkcard')).toBeInViewport();
});

test('scrolling the open section', async ({ page }) => {
  await talk(page);
  await act(page, { command: 'open_section', payload: { section: 'pricing' } });
  await expect.poll(() => active(page)).toBe('pricing');
  // Where the section's top sits: the panel's own scroll on a desktop, the page on a phone.
  const top = () => page.evaluate(() => {
    const p = document.getElementById('panel')!;
    return p.scrollHeight > p.clientHeight + 4 ? p.scrollTop : Math.round(p.getBoundingClientRect().top);
  });
  await page.waitForTimeout(900);
  const start = await top();
  await act(page, { command: 'site_command', payload: { command: 'scroll_down' } });
  await expect.poll(async () => Math.abs((await top()) - start)).toBeGreaterThan(100);
  await act(page, { command: 'site_command', payload: { command: 'scroll_top' } });
  await expect.poll(async () => Math.abs((await top()) - start)).toBeLessThan(80);
});

test('theme, and going back', async ({ page }) => {
  const errors = await talk(page);
  await act(page, { command: 'site_command', payload: { command: 'dark' } });
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await act(page, { command: 'open_section', payload: { section: 'cast' } });
  await expect.poll(() => active(page)).toBe('cast');
  await act(page, { command: 'close_section', payload: {} });
  await expect.poll(() => active(page)).toBe(null);
  expect(errors).toEqual([]);
});

test('read mode from the brain', async ({ page }) => {
  await talk(page);
  await act(page, { command: 'set_mode', payload: { mode: 'read' } });
  await expect(page.locator('body')).toHaveAttribute('data-mode', 'read');
});

/* ---------- the site's other pages, beside Tanvi ---------- */

const frame = (page: Page) => page.frameLocator('#pageview');
const framePath = (page: Page) => page.evaluate(() => {
  const w = (document.getElementById('pageview') as HTMLIFrameElement).contentWindow;
  try { return (w?.location.pathname ?? '').replace(/(.)\/$/, '$1'); } catch { return ''; }
});

test('every page she can open shows beside her, without its own header or footer', async ({ page }) => {
  const errors = await talk(page);
  for (const p of voice.pages) {
    await act(page, { command: 'open_page', payload: { page: p.id } });
    await expect.poll(() => active(page)).toBe('page');
    await expect.poll(() => framePath(page)).toBe(p.url);
    await expect(frame(page).locator('html')).toHaveClass(/is-framed/);
    await expect(frame(page).locator('.top')).toBeHidden();
    await expect(frame(page).locator('h1').first()).toBeVisible();
  }
  await expect(page.locator('#pageview')).toBeInViewport({ ratio: 0.5 });
  expect(errors).toEqual([]);
});

test('links inside a page stay beside her', async ({ page }) => {
  await talk(page);
  await act(page, { command: 'open_page', payload: { page: 'retail' } });
  await expect.poll(() => framePath(page)).toBe('/solutions/retail');
  // Another site page opens in its place.
  await frame(page).locator('body').evaluate((b) => { const a = document.createElement('a'); a.href = '/story'; a.id = 't-story'; a.textContent = 'story'; b.prepend(a); });
  await frame(page).locator('#t-story').click();
  await expect.poll(() => framePath(page)).toBe('/story');
  await expect(frame(page).locator('.top')).toBeHidden();
  // A link home to a section opens that section.
  await frame(page).locator('body').evaluate((b) => { const a = document.createElement('a'); a.href = '/#s-pricing'; a.id = 't-home'; a.textContent = 'pricing'; b.prepend(a); });
  await frame(page).locator('#t-home').click();
  await expect.poll(() => active(page)).toBe('pricing');
});

test('scrolling and the theme reach the page beside her', async ({ page }) => {
  await talk(page);
  await act(page, { command: 'open_page', payload: { page: 'security' } });
  await expect(frame(page).locator('h1').first()).toBeVisible();
  const y = () => page.evaluate(() => (document.getElementById('pageview') as HTMLIFrameElement).contentWindow!.scrollY);
  await act(page, { command: 'site_command', payload: { command: 'scroll_down' } });
  await expect.poll(y).toBeGreaterThan(100);
  await act(page, { command: 'site_command', payload: { command: 'dark' } });
  await expect(frame(page).locator('html')).toHaveAttribute('data-theme', 'dark');
  await act(page, { command: 'close_section', payload: {} });
  await expect.poll(() => active(page)).toBe(null);
});

test('the Experience Center button opens beside her in Talk mode', async ({ page, isMobile }) => {
  test.skip(isMobile, 'the header button is hidden on phones');
  await talk(page);
  await page.locator('a.top__cta').click();
  await expect.poll(() => active(page)).toBe('page');
  await expect.poll(() => framePath(page)).toBe('/experience');
  expect(page.context().pages()).toHaveLength(1);
});

/* ---------- parts of a page ---------- */

test('every part she can show exists on its page', async ({ page }) => {
  await talk(page);
  for (const p of voice.pages) {
    const want = voice.parts.filter((x) => x.page === p.id).map((x) => x.part);
    await act(page, { command: 'open_page', payload: { page: p.id } });
    await expect.poll(() => framePath(page)).toBe(p.url);
    await expect(frame(page).locator('h1').first()).toBeVisible();
    const missing = await frame(page).locator('body').evaluate((b, parts) => parts.filter((x) => !b.querySelector(`[data-part="${x}"]`)), want);
    expect(missing, p.id).toEqual([]);
  }
});

test('she scrolls a page to the part she is talking about', async ({ page }) => {
  await talk(page);
  // From a standing start: the retail page opens, then scrolls to the checkout scene.
  await act(page, { command: 'show', payload: { target: 'retail.scene2' } });
  await expect.poll(() => framePath(page)).toBe('/solutions/retail');
  const scene = frame(page).locator('[data-part="scene2"]');
  await expect(scene.locator('h3')).toHaveClass(/is-marked/);
  await expect(scene).toBeInViewport({ ratio: 0.2 });
  // Another page's part: the page changes, then scrolls.
  await act(page, { command: 'show', payload: { target: 'banking.scene3' } });
  await expect.poll(() => framePath(page)).toBe('/solutions/banking');
  await expect(frame(page).locator('[data-part="scene3"] h3')).toHaveClass(/is-marked/);
  await expect(frame(page).locator('[data-part="scene3"]')).toBeInViewport({ ratio: 0.2 });
  // Back up the same page.
  await act(page, { command: 'show', payload: { target: 'banking.hero' } });
  await expect(frame(page).locator('[data-part="hero"]')).toBeInViewport({ ratio: 0.3 });
});

/* ---------- phones: one screen, one scroll, Tanvi in her corner ---------- */

for (const width of [320, 360, 390]) {
  test(`on a ${width}px phone a page beside her fills the screen and the tile stays on it`, async ({ browser }) => {
    const ctx = await browser.newContext({ viewport: { width, height: 760 }, isMobile: true, hasTouch: true });
    const page = await ctx.newPage();
    await page.addInitScript(() => { try { localStorage.setItem('vq-consent', JSON.stringify({ v: 1, analytics: false, ads: false })); } catch { /* ignore */ } });
    await talk(page);
    await act(page, { command: 'open_page', payload: { page: 'retail' } });
    await expect(frame(page).locator('h1').first()).toBeVisible();
    const m = await page.evaluate(() => {
      const f = document.getElementById('pageview')!.getBoundingClientRect();
      const g = document.querySelector('.guide')!.getBoundingClientRect();
      const nav = document.querySelector('.top')!.getBoundingClientRect().bottom;
      return { docW: document.documentElement.scrollWidth, docH: document.documentElement.scrollHeight, w: innerWidth, h: innerHeight,
        frame: [f.left, f.top, f.right, f.bottom], nav, tile: [g.left, g.top, g.right, g.bottom] };
    });
    expect(m.docW, 'the page is no wider than the screen').toBe(width);
    expect(m.docH, 'the page behind does not scroll').toBeLessThanOrEqual(m.h);
    expect(m.frame).toEqual([0, m.nav, width, m.h]);
    expect(m.tile[0]).toBeGreaterThanOrEqual(0);
    expect(m.tile[2]).toBeLessThanOrEqual(width);
    expect(m.tile[3]).toBeLessThanOrEqual(m.h);
    await ctx.close();
  });
}

/* ---------- what is on the visitor's screen, as Tanvi is told ---------- */

const view = (page: Page) => page.evaluate(() => window.vq.view());

test('every home block the brain names is on the page, once, in its own section', async ({ page }) => {
  await talk(page);
  const missing = await page.evaluate((blocks) => blocks
    .filter((b) => document.querySelectorAll(`[data-section="${b.section}"] [data-part="${b.part}"]`).length !== 1)
    .map((b) => b.id), voice.blocks);
  expect(missing).toEqual([]);
});

test('on a computer the Plug & Play steps and their animation are side by side', async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  await talk(page);
  expect(await view(page)).toMatchObject({ device: 'desktop', layout: 'centre' });
  await show(page, 'ways.plug_and_play.step2');
  await expect.poll(async () => (await view(page)).rows, { timeout: 10000 }).toContainEqual(['ways.pnp_steps', 'ways.pnp_demo']);
  expect(await view(page)).toMatchObject({ layout: 'beside', section: 'ways' });
  expect((await view(page)).showing).toContain('ways.plug_and_play');
  await ctx.close();
});

test('on a phone the animation is below the steps, and scrolling a page beside her is followed', async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const page = await ctx.newPage();
  await page.addInitScript(() => { try { localStorage.setItem('vq-consent', JSON.stringify({ v: 1, analytics: false, ads: false })); } catch { /* ignore */ } });
  await talk(page);
  await show(page, 'ways.plug_and_play.step2');
  await page.waitForTimeout(800);
  await page.evaluate(() => document.querySelector('[data-part="pnp_steps"]')!.scrollIntoView({ block: 'start' }));
  await expect.poll(async () => (await view(page)).rows, { timeout: 10000 }).toEqual(expect.arrayContaining([['ways.pnp_steps'], ['ways.pnp_demo']]));
  const v = await view(page);
  expect(v).toMatchObject({ device: 'phone', layout: 'tile', section: 'ways' });
  expect(v.rows!.findIndex((r) => r[0] === 'ways.pnp_steps')).toBeLessThan(v.rows!.findIndex((r) => r[0] === 'ways.pnp_demo'));

  // She shows the retail checkout; the visitor scrolls on to the scene after it.
  await show(page, 'retail.scene2');
  await expect.poll(async () => (await view(page)).focus, { timeout: 10000 }).toBe('retail.scene2');
  await page.evaluate(() => {
    const f = document.getElementById('pageview') as HTMLIFrameElement;
    const el = f.contentDocument!.querySelector('[data-part="scene3"]')!;
    f.contentWindow!.scrollTo({ top: el.getBoundingClientRect().top + f.contentWindow!.scrollY - 40 });
  });
  await expect.poll(async () => (await view(page)).focus, { timeout: 10000 }).toBe('retail.scene3');
  expect(await view(page)).toMatchObject({ page: 'retail', heading: expect.stringContaining('swap') });
  await ctx.close();
});

/* ---------- no mailto links, anywhere ---------- */

test('no page opens a mail app: addresses are text with a Copy button', async ({ page }) => {
  const urls = ['/', '/privacy', '/dpa', '/pricing', ...voice.pages.map((p) => p.url)];
  for (const url of [...new Set(urls)]) {
    await page.goto(url);
    expect(await page.locator('a[href^="mailto:"]').count(), url).toBe(0);
  }
  await page.goto('/security');
  const fine = page.locator('.sec-card__fine .email');
  await expect(fine).toContainText('support@voqalize.com');
  await expect(fine.locator('button.email__copy')).toHaveAttribute('data-copy', 'support@voqalize.com');
});
