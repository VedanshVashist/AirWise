// Shared by the dashboard, alert checks and campaign captions.
function hasReading(current) {
    return Number.isFinite(current?.us_aqi) && current.us_aqi >= 0 &&
        Number.isFinite(current.time);
}

function isFreshReading(current, now = Date.now() / 1000) {
    return hasReading(current) && current.time <= now && now - current.time <= 7200;
}

function currentEstimate(source, current) {
    return source === 'Current estimate' && isFreshReading(current) ? Math.round(current.us_aqi) : null;
}

function forecastPoints(report, hours) {
    const start = report?.current?.time;
    const hourly = report?.hourly;
    if (!Number.isFinite(start) || !Array.isArray(hourly?.time) || !Array.isArray(hourly.us_aqi)) return [];
    const end = start + hours * 3600;
    return hourly.time.map((t, i) => ({ t, v: hourly.us_aqi[i] }))
        .filter(({ t, v }) => Number.isFinite(t) && t >= start && t < end && Number.isFinite(v) && v >= 0);
}
