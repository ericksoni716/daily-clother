import { expect, login, test, useProfile } from './fixtures';

test.afterEach(async ({ page }) => {
  await page.request.post('/api/profile', { data: { profile: 'main' } });
});

test('debug', async ({ page }) => {
  await page.addInitScript(() => {
    const add = (m: string) => sessionStorage.setItem('dbg', (sessionStorage.getItem('dbg') || '') + `\n${Math.round(performance.timeOrigin + performance.now()) % 100000} ${m}`);
    const f = window.fetch;
    window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === 'PATCH') add(`PATCH ${init.body} ka=${init.keepalive}`);
      const r = f(input, init);
      if (init?.method === 'PATCH') r.then((x) => add(`PATCH answered ${x.status}`), (e) => add(`PATCH failed ${e}`));
      return r;
    };
    addEventListener('pagehide', () => add(`pagehide textarea=${(document.querySelector('.detail-panel textarea') as HTMLTextAreaElement | null)?.value}`), { capture: true });
    document.addEventListener('visibilitychange', () => add(`vis ${document.visibilityState}`), { capture: true });
  });
  await login(page);
  await useProfile(page, 'demo');
  await page.getByTestId('tile').filter({ hasText: 'Oatmeal henley' }).click();
  const notes = () => page.locator('.detail-panel').getByRole('textbox', { name: 'Notes', exact: true });
  const items = (await (await page.request.get('/api/items')).json()).items as { id: string; name: string }[];
  const id = items.find((x) => x.name === 'Oatmeal henley')!.id;
  const t0 = Date.now();
  const log: string[] = [];
  page.context().on('request', (r) => { if (r.url().includes('/api/items/')) log.push(`${Date.now() - t0} req ${r.method()} ${r.url().split('/api/')[1]}`); });
  page.context().on('requestfinished', async (r) => { if (r.url().includes('/api/items/')) log.push(`${Date.now() - t0} done ${r.method()} ${r.url().split('/api/')[1]}`); });
  page.context().on('requestfailed', (r) => { if (r.url().includes('/api/items/')) log.push(`${Date.now() - t0} FAIL ${r.method()} ${r.failure()?.errorText}`); });
  const note = `Kept through a reload ${Date.now()}`;
  await page.locator('.detail-panel').getByText('More details').click();
  await notes().fill(note);
  log.push(`${Date.now() - t0} reload`);
  await page.reload();
  log.push(`${Date.now() - t0} reloaded`);
  await page.locator('.detail-panel').getByText('More details').click();
  const shown = await notes().inputValue();
  log.push(await page.evaluate(() => sessionStorage.getItem('dbg') || ''));
  await page.evaluate(() => sessionStorage.removeItem('dbg'));
  const server = [] as string[];
  for (let i = 0; i < 10; i++) {
    server.push(`${Date.now() - t0} ${(await (await page.request.get(`/api/items/${id}`)).json()).notes === note}`);
    await page.waitForTimeout(100);
  }
  console.log(shown === note ? 'OK' : 'STALE', '\n' + log.join('\n'), '\n' + server.join(' | '));
  expect(shown).toBe(note);
});
