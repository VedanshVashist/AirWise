const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const vm = require('node:vm');
const { setImmediate: nextTurn } = require('node:timers/promises');

// Load the same scripts, in the same order, as the deployed entry page.
const html = readFileSync('public/index.html', 'utf8');
const scripts = Array.from(html.matchAll(/<script defer src="([^"]+)"/g), match => match[1]);

function dashboard(getAir) {
    const elements = new Map();
    const storage = new Map();
    const document = {
        addEventListener() {},
        querySelectorAll: () => [],
        querySelector(selector) {
            if (!elements.has(selector)) elements.set(selector, { addEventListener() {} });
            return elements.get(selector);
        }
    };
    const context = vm.createContext({
        document, window: { addEventListener() {} }, location: { hash: '#overview' },
        setInterval() {},
        localStorage: { getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value) },
        async fetch(path) {
            const payload = path.startsWith('/api/air?') ? await getAir() : {};
            return { ok: true, json: async () => payload };
        }
    });
    for (const name of scripts) vm.runInContext(readFileSync('public/' + name, 'utf8'), context, { filename: name });
    return { markup: () => elements.get('#main').innerHTML, refresh: () => context.loadAir() };
}

test('overview moves from sample to current to saved when the provider goes offline', async () => {
    let online = true;
    const page = dashboard(() => {
        if (!online) throw Error('offline');
        return { current: { time: Math.floor(Date.now() / 1000), us_aqi: 42 }, hourly: { time: [0] } };
    });
    assert.match(page.markup(), /Sample data/);
    await nextTurn();
    assert.match(page.markup(), /Current estimate/);
    assert.match(page.markup(), /class="aqinum">42</);
    assert.match(page.markup(), /Hourly estimates will appear/);
    online = false;
    await page.refresh();
    assert.match(page.markup(), /Saved reading/);
    assert.match(page.markup(), /class="aqinum">42</);
});

test('an older request finishing last cannot overwrite the latest dashboard reading', async () => {
    let finishFirst;
    const pending = new Promise(resolve => { finishFirst = resolve; });
    const current = us_aqi => ({ current: { time: Math.floor(Date.now() / 1000), us_aqi } });
    let requests = 0;
    const page = dashboard(() => ++requests === 1 ? pending : current(75));
    await page.refresh();
    finishFirst(current(20));
    await nextTurn();
    assert.match(page.markup(), /class="aqinum">75</);
});
