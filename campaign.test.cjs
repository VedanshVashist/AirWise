const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const vm = require('node:vm');

function reading(source, ageSeconds = 0) {
    const script = readFileSync('public/campaign.js', 'utf8');
    return vm.runInNewContext(script + '\ncampaignReading()', {
        document: { addEventListener() {} },
        loc: { name: 'Delhi' }, source, aqi: () => 152,
        band: () => 3, bandNames: [null, null, null, 'Unhealthy'],
        data: { current: { time: Date.now() / 1000 - ageSeconds }, timezone: 'Asia/Kolkata' }
    });
}

test('fresh campaigns include the reading, category, source and timezone', () => {
    assert.match(reading('Current estimate'), /Delhi .*US AQI 152 \(Unhealthy\).*Open-Meteo.*Asia\/Kolkata/);
});

test('sample, saved and expired estimates never become shareable current readings', () => {
    for (const source of ['Sample data', 'Saved reading', 'Unavailable']) {
        assert.match(reading(source), /Current AQI unavailable/);
    }
    assert.match(reading('Current estimate', 7201), /Current AQI unavailable/);
});
