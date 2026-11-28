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
            if (!elements.has(selector)) {
                const classes = new Set();
                elements.set(selector, {
                    classList: { contains: name => classes.has(name), toggle(name, on) { if (on) classes.add(name); else classes.delete(name); } },
                    addEventListener(type, listener) { this[type] = listener; },
                    setAttribute(name, value) { this[name] = value; },
                    focus() { document.activeElement = this; }
                });
            }
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
    document.body = document.querySelector('body');
    return { markup: () => elements.get('#main').innerHTML, refresh: () => context.loadAir(), elements, context };
}

test('overview moves from sample to current to saved when the provider goes offline', async () => {
    let online = true;
    const page = dashboard(() => {
        if (!online) throw Error('offline');
        return { current: { time: Math.floor(Date.now() / 1000), us_aqi: 42 }, hourly: { time: [0] } };
    });
    assert.match(page.markup(), /Sample data/);
    assert.match(page.markup(), /Confirm the AQI before planning outdoor exercise/);
    await nextTurn();
    assert.match(page.markup(), /Current estimate/);
    assert.match(page.markup(), /Conditions generally support outdoor activity/);
    assert.match(page.markup(), /class="aqinum">42</);
    assert.match(page.markup(), /Hourly estimates will appear/);
    online = false;
    await page.refresh();
    assert.match(page.markup(), /Saved reading/);
    assert.match(page.markup(), /Confirm the AQI before planning outdoor exercise/);
    assert.match(page.markup(), /class="aqinum">42</);
});

test('skip link moves focus into the active page and preserves the forecast route', () => {
    const {context, elements} = dashboard(() => ({}));
    context.location.hash = '#forecast';
    context.render();
    let prevented = false;
    elements.get('.skip').click({ preventDefault() { prevented = true; } });
    assert.ok(prevented);
    assert.equal(context.location.hash, '#forecast');
    assert.equal(context.document.activeElement, elements.get('#main'));
});

test('browser alerts show the saved threshold and escape local history', async () => {
    const page = dashboard(() => ({}));
    await nextTurn();
    page.context.set('threshold', 151);
    page.context.set('browserAlerts', true);
    page.context.set('browserHistory', [{city: '<Example>', aqi: 155, time: 1800000000, body: 'Take breaks.'}]);
    page.context.location.hash = '#alerts';
    page.context.render();
    assert.match(page.markup(), /<option selected>Browser notifications<\/option>/);
    assert.match(page.markup(), /value="151" selected/);
    assert.match(page.markup(), /&lt;Example&gt; · US AQI 155/);
});

test('mobile navigation moves and restores focus and isolates background controls', () => {
    const {context, elements} = dashboard(() => ({}));
    elements.get('#menu').onclick();
    assert.equal(elements.get('.workspace').inert, true);
    assert.equal(elements.get('#menu')['aria-expanded'], 'true');
    assert.equal(context.document.activeElement, elements.get('#sidebar [aria-current="page"]'));
    elements.get('#close-menu').onclick();
    assert.equal(elements.get('.workspace').inert, false);
    assert.equal(context.document.activeElement, elements.get('#menu'));
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
