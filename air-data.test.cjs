const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const vm = require('node:vm');
const { isFreshReading, forecastPoints } = vm.runInNewContext(
    readFileSync('public/air-data.js', 'utf8') + '\n({ isFreshReading, forecastPoints })'
);

test('freshness includes exactly two hours and rejects future or malformed readings', () => {
    const now = 10000;
    for (const time of [now, now - 7200]) assert.ok(isFreshReading({ time, us_aqi: 0 }, now));
    for (const time of [now + 1, now - 7201, undefined, NaN, '10000']) {
        assert.equal(isFreshReading({ time, us_aqi: 42 }, now), false);
    }
    for (const us_aqi of [null, -1, Infinity, '0']) {
        assert.equal(isFreshReading({ time: now, us_aqi }, now), false);
    }
});

test('forecast rows preserve timestamp alignment and respect the chosen horizon', () => {
    const report = { current: { time: 0 }, hourly: {
        time: [-1, 0, 3600, 7200, 86400, 172800], us_aqi: [8, 0, null, 62, 91, 99]
    } };
    assert.deepEqual(Array.from(forecastPoints(report, 24), row => row.v), [0, 62]);
    assert.deepEqual(Array.from(forecastPoints(report, 48), row => row.t), [0, 7200, 86400]);
});

test('missing or partial forecast fields leave the chart usable', () => {
    for (const hourly of [null, {}, { time: {} }, { time: [100] }, { time: [100], us_aqi: [] }]) {
        assert.equal(forecastPoints({ current: { time: 100 }, hourly }, 24).length, 0);
    }
});
