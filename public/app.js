'use strict';
const $ = selector => document.querySelector(selector);
const main = $('#main');
const dialog = $('#dialog');
const glyph = {
    grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    chart: '<path d="M3 3v17h18M6 14l4-5 4 3 6-7"/>',
    leaf: '<path d="M20 3C10 2 3 8 5 15c2 7 13 5 15-12ZM3 21l11-11"/>',
    spark: '<path d="m12 3 2.1 6.9L21 12l-6.9 2.1L12 21l-2.1-6.9L3 12l6.9-2.1ZM20 2v4m-2-2h4"/>',
    bell: '<path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9Zm-8 12h4"/>',
    users: '<circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6m1 3a5 5 0 0 1 4 5"/>',
    menu: '<path d="M3 6h18M3 12h18M3 18h18"/>',
    panel: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/>',
    chevRight: '<path d="m9 5 7 7-7 7"/>',
    down: '<path d="m6 9 6 6 6-6"/>',
    pin: '<path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0Z"/><circle cx="12" cy="10" r="2"/>',
    calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 10h18"/>',
    wind: '<path d="M3 8h11a3 3 0 1 0-3-3M2 12h16a3 3 0 1 0 0-6M4 16h9a3 3 0 1 1-3 3"/>',
    shield: '<path d="m12 2 8 4v6c0 5-5 8-8 10-3-2-8-5-8-10V6Z"/><path d="m8 12 3 3 5-6"/>',
    shoe: '<path d="m4 7 4-2 2 5 4 2 5 1a3 3 0 0 1 2 3v2H4c-1-3-1-7 0-11ZM3 15h6m3-6-2 3m5-2-2 3"/>',
    home: '<path d="m2 11 10-8 10 8M5 10v11h14V10m-10 11v-7h6v7"/>',
    arrow: '<path d="M4 12h15m-6-6 6 6-6 6"/>',
    upRight: '<path d="M6 18 18 6M7 6h11v11"/>',
    layers: '<path d="m12 3 9 5-9 5-9-5Zm-9 9 9 5 9-5m-18 4 9 5 9-5"/>',
    bus: '<rect x="5" y="3" width="14" height="16" rx="3"/><path d="M5 12h14M8 19v2m8-2v2M8 16h1m6 0h1M8 7h8"/>',
    check: '<path d="m4 13 5 5L20 6"/>',
    close: '<path d="m5 5 14 14M19 5 5 19"/>',
    send: '<path d="m3 10 18-7-6 18-3-8-9-3Zm9 3 9-10"/>',
    target: '<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2"/><path d="M12 1v4m0 14v4M1 12h4m14 0h4"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'
};

function icon(name, extra = '') {
    return `<svg class="ic ${extra}" aria-hidden="true" viewBox="0 0 24 24">${glyph[name]||''}</svg>`;
}
document.querySelectorAll('[data-i]').forEach(el => el.outerHTML = icon(el.dataset.i));

function escapeHTML(x) {
    return String(x ?? '').replace(/[&<>"']/g, c => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
    } [c]));
}

function get(key, fallback) {
    try {
        return JSON.parse(localStorage.getItem('airwise.' + key)) ?? fallback;
    } catch {
        return fallback;
    }
}

function set(key, value) {
    try {
        localStorage.setItem('airwise.' + key, JSON.stringify(value));
    } catch {}
}
const cities = [
    ['New Delhi', 'India', 28.6139, 77.209],
    ['Mumbai', 'India', 19.076, 72.8777],
    ['Bengaluru', 'India', 12.9716, 77.5946],
    ['London', 'United Kingdom', 51.5072, -.1276],
    ['New York', 'United States', 40.7128, -74.006]
].map(([name, country, lat, lon]) => ({
    name,
    country,
    lat,
    lon
}));
let loc = get('location', cities[0]),
    profile = get('profile', {
        household: 'Adults',
        travel: 'Car',
        home: 'No air purifier'
    }),
    data = null,
    source = 'Checking',
    hours = 24,
    airRequest = 0;
let alertConfig = {
        enabled: false,
        desktop: false,
        threshold: 101,
        history: []
    },
    alertsReady = false;
let messages = [],
    pending = false,
    chatVersion = 0;
const titles = {
    overview: 'Overview',
    forecast: 'Air forecast',
    plan: 'Action plan',
    assistant: 'AI assistant',
    campaign: 'Campaign studio',
    alerts: 'Air alerts',
    household: 'Household'
};
const route = () => Object.hasOwn(titles, location.hash.slice(1)) ? location.hash.slice(1) : 'overview';
const cityName = () => [loc.name, loc.country].filter(Boolean).join(', ');
const esc = escapeHTML;
const bandNames = ['Good', 'Moderate', 'Unhealthy for sensitive groups', 'Unhealthy', 'Very unhealthy', 'Hazardous'];
const colors = ['#96d598', '#f1d477', '#efad6e', '#f19783', '#c49bcc', '#a27694'];
const band = n => n <= 50 ? 0 : n <= 100 ? 1 : n <= 150 ? 2 : n <= 200 ? 3 : n <= 300 ? 4 : 5;
const aqi = () => Number.isFinite(data?.current?.us_aqi) ? Math.round(data.current.us_aqi) : null;

function localTime(stamp, options) {
    return new Intl.DateTimeFormat('en-US', {
        timeZone: data?.timezone || undefined,
        ...options
    }).format(new Date(stamp * 1000));
}

function dayKey() {
    return localTime(Date.now() / 1000, {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
    }) + '/' + loc.lat + '/' + loc.lon;
}

function note(text) {
    $('#notice').textContent = text;
    clearTimeout(note.timer);
    note.timer = setTimeout(() => $('#notice').textContent = '', 3500);
}
async function api(path, body) {
    let r = await fetch('/api/' + path, body ? {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(body)
    } : {});
    if (!r.ok) throw Error('Service unavailable');
    return r.json();
}
const exampleTime = () => Math.floor(Date.now() / 3600000) * 3600;

function sample() {
    let t = exampleTime();
    return {
        timezone: 'Asia/Kolkata',
        current: {
            time: t,
            us_aqi: 184,
            pm2_5: 88.6,
            pm10: 142.2,
            nitrogen_dioxide: 32.7,
            ozone: 41.1
        },
        hourly: {
            time: Array.from({
                length: 49
            }, (_, i) => t + i * 3600),
            us_aqi: [184, 185, 187, 184, 180, 176, 170, 165, 168, 173, 175, 172, 164, 158, 155, 156, 160, 167, 174, 177, 180, 187, 188, 185, 181, 175, 171, 168, 165, 160, 155, 151, 150, 148, 146, 149, 152, 159, 164, 167, 163, 160, 158, 161, 165, 171, 174, 176, 177]
        }
    };
}

function precautions() {
    const n = aqi(),
        b = n === null ? -1 : band(n),
        sensitive = profile.household !== 'Adults';
    const exercise = b === -1 ? ['Check local advisories', 'Confirm the AQI before planning outdoor exercise.'] : b >= 5 ? ['Move activity indoors', 'Avoid physical activity outdoors until air improves.'] : b >= 4 ? ['Move workouts indoors', 'Avoid strenuous activity outdoors today.'] : b >= 3 ? ['Limit outdoor exertion', 'Shorten strenuous outings and take more breaks.'] : b === 2 ? ['Adjust outdoor activity', 'Sensitive groups should shorten intense outings.'] : ['Plan outdoor activity', b === 0 ? 'Conditions generally support outdoor activity.' : 'Take breaks if you are unusually sensitive.'];
    const indoor = b >= 2 ? ['Keep indoor air cleaner', profile.home === 'Air purifier available' ? 'Run a room-sized filter where you spend time.' : 'Skip incense, candles, and smoky cooking.'] : ['Reduce indoor particles', 'Use an exhaust hood vented outdoors when cooking.'];
    const family = b >= 2 ? [sensitive ? 'Protect your household' : 'Check on sensitive groups', sensitive ? 'Choose a cleaner indoor space for longer activities.' : 'Children and older adults may need extra care.'] : ['Check before heading out', 'Review the forecast before a long outing.'];
    return [
        [...exercise, 'shoe'],
        [...indoor, 'home'],
        [...family, 'users']
    ];
}

function actions() {
    let n = aqi(),
        bad = n === null || n > 100,
        travel = profile.travel,
        group = profile.household,
        filter = profile.home === 'Air purifier available';
    let trip = travel === 'Car' ? ['Combine your errands', 'Group nearby stops into one trip and switch off the engine while parked.', 'Fewer starts and less idling reduce fuel burned and exhaust near homes.'] : travel === 'Public transport' ? ['Take one shared route', 'Combine errands along one transit route. Wait away from idling vehicles.', 'Sharing a vehicle can cut per-person emissions and reduce traffic.'] : ['Choose quieter streets', bad ? 'Use a shorter, lower-traffic route for essential trips. Defer vigorous cycling.' : 'Walk or cycle on a quiet route for a nearby errand.', 'A quieter route reduces time beside exhaust. Replacing a car trip avoids tailpipe emissions.'];
    let inside = filter ? ['Filter your main room', 'Run a correctly sized HEPA cleaner in the room your household uses most.', 'Filtration removes airborne particles from the air that passes through the unit.'] : ['Skip indoor smoke', 'Choose an unlit decoration instead of incense or candles today.', 'Avoiding combustion prevents fine particles from entering your indoor air.'];
    let community = group === 'Community group' ? ['Plan a shared activity', bad ? 'Move the group session to a cleaner indoor space.' : 'Choose a nearby meeting place reachable by transit.', 'A shared local venue can shorten trips and help people limit exposure.'] : bad ? [group === 'Family with children' ? 'Move playtime indoors' : 'Move exercise indoors', 'Choose gentle movement in a cleaner room and recheck the AQI before heading out.', 'Less time exerting outdoors reduces the amount of polluted air inhaled.'] : ['Walk a nearby errand', 'Choose a nearby destination and check the AQI before leaving.', 'Replacing a short car journey avoids the exhaust from that trip.'];
    return [trip, inside, community].map(([title, detail, impact], i) => ({
        id: [travel, profile.home, bad + '-' + group][i] + '-' + i,
        title,
        detail,
        impact,
        tag: ['Low-emission travel', 'Indoor air', 'Daily routine'][i],
        icon: ['bus', 'home', 'leaf'][i]
    }));
}

function locationButton() {
    return `<button class="button" data-act="location">${icon('pin')}${esc(cityName())}${icon('down','chev')}</button>`;
}

function head(title, sub, control = '') {
    return `<div class="pagehead"><div><h1>${esc(title)}</h1><p class="sub">${esc(sub)}</p></div>${control}</div>`;
}

function cardTitle(i, title) {
    return `<div class="titleline">${icon(i)}<h2>${title}</h2></div>`;
}

function hero() {
    let n = aqi(),
        b = n === null ? 0 : band(n),
        low = [0, 50, 100, 150, 200, 300][b],
        high = [50, 100, 150, 200, 300, 500][b],
        pct = Math.min(99, (b + Math.min(1, (n - low) / (high - low))) * 100 / 6);
    return `<section class="hero ${Math.abs(loc.lat-28.61)<.5&&Math.abs(loc.lon-77.21)<.5?'':'other'}"><div class="herohead"><div class="eyebrow">${icon('wind')}Current air quality</div><span class="datachip"><i class="dot"></i>${esc(source)}</span></div>
 <div class="numline"><span class="aqinum">${n??'–'}</span>${n===null?'':`<span class="bandbadge" style="--tone:${colors[b]}">${bandNames[b]}</span>`}</div><div class="herounit">U.S. Air Quality Index</div><div class="heroplace">${icon('pin')}${esc(cityName())}${data&&source!=='Sample data'?` &nbsp;·&nbsp; ${localTime(data.current.time,{hour:'numeric',minute:'2-digit'})}`:''}</div>
 <div class="scale"><div class="scalebar">${colors.map(c=>`<span style="background:${c}"></span>`).join('')}${n===null?'':`<b style="left:${pct}%"></b>`}</div><div class="scalelabels"><span>Good</span><span>Hazardous</span></div></div></section>`;
}

function tips() {
    return `<section class="card precautions">${cardTitle('shield',"Today's precautions")}<div class="sub">Guidance for your household</div><div class="precautionlist">${precautions().map(([t,d,i],j)=>`<div class="tip"><span class="tileicon tone${j}">${icon(i)}</span><div><h3>${t}</h3><p>${d}</p></div></div>`).join('')}</div><a class="textbutton" href="#assistant">Ask Airwise ${icon('arrow')}</a></section>`;
}

function points() {
    return forecastPoints(data, hours);
}

function plot() {
    let pts = points();
    if (!pts.length) return '<p class="empty">Hourly estimates will appear when air data is available.</p>';
    let min = Math.max(0, Math.floor((Math.min(...pts.map(p => p.v)) - 8) / 10) * 10),
        max = Math.ceil((Math.max(...pts.map(p => p.v)) + 8) / 10) * 10;
    let x = i => 37 + i * 551 / Math.max(1, pts.length - 1),
        y = v => 8 + 108 * (max - v) / (max - min);
    let d = pts.map((p, i) => `${i?'L':'M'}${x(i).toFixed(2)} ${y(p.v).toFixed(2)}`).join(' ');
    let grid = [0, 1, 2, 3].map(i => {
        let v = Math.round(min + (max - min) * i / 3),
            h = y(v);
        return `<line x1="37" x2="588" y1="${h}" y2="${h}" stroke="#dbe5dd" stroke-dasharray="3 4"/><text x="0" y="${h+4}" font-size="11" fill="#718275">${v}</text>`;
    }).join('');
    return `<div class="plot"><svg viewBox="0 0 600 125" preserveAspectRatio="none" role="img" aria-label="Forecast AQI ranges from ${Math.min(...pts.map(p=>p.v))} to ${Math.max(...pts.map(p=>p.v))}"><defs><linearGradient id="fill" x2="0" y2="1" gradientUnits="objectBoundingBox"><stop stop-color="#7dbe92" stop-opacity=".45"/><stop offset="1" stop-color="#b8d9bd" stop-opacity=".08"/></linearGradient></defs>${grid}<path d="${d} L${x(pts.length-1)} 119 L37 119Z" fill="url(#fill)"/><path d="${d}" fill="none" stroke="#40875f" stroke-width="2.7" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>${pts.map((p,i)=>`<circle cx="${x(i)}" cy="${y(p.v)}" r="${i===0?3.5:5}" fill="${i===0?'#40875f':'transparent'}"><title>${localTime(p.t,{hour:'numeric',minute:'2-digit'})} · US AQI ${Math.round(p.v)}</title></circle>`).join('')}</svg><div class="axis">${[0,.25,.5,.75,1].map(f=>`<span>${localTime(pts[Math.round(f*(pts.length-1))].t,{hour:'numeric',minute:'2-digit'})}</span>`).join('')}</div></div>`;
}

function chart() {
    return `<section class="card chartcard"><div class="cardhead">${cardTitle('chart','AQI forecast')}<div class="seg" aria-label="Forecast range">${[24,48].map(n=>`<button data-hours="${n}" class="${n===hours?'on':''}" aria-pressed="${n===hours}">${n}h</button>`).join('')}</div></div><div class="sub">Hourly outlook for ${esc(loc.name)}</div>${plot()}<div class="legend">${source==='Sample data'?'Sample forecast':'Forecast US AQI'}</div></section>`;
}
const pollutants = [
    ['PM₂.₅', 'pm2_5', '#bd8157'],
    ['PM₁₀', 'pm10', '#d1ae62'],
    ['NO₂', 'nitrogen_dioxide', '#81a4b2'],
    ['O₃', 'ozone', '#8fa981']
];

let sensorStatus = 'Checking nearby sensors…';

function pollution() {
    return `<section class="card pollutants">${cardTitle('layers','Pollutant levels')}<div class="sub">Open-Meteo estimates in µg/m³</div><div class="pollgrid">${pollutants.map(([label,k,c])=>`<div class="polltile" style="--color:${c}"><strong>${label}</strong><div><b>${Number.isFinite(data?.current[k])?data.current[k].toFixed(1):'–'}</b><small>µg/m³</small></div></div>`).join('')}</div><p class="sub"><a href="https://sensor.community/" target="_blank" rel="noreferrer">Sensor.Community</a> · ${esc(sensorStatus)}</p></section>`;
}

function completed(a) {
    return get('completed', {})[dayKey()]?.includes(a.id) || false;
}

function actionCards(full = false) {
    return `<div class="actiongrid ${full?'fullplan':''}">${actions().map((a,i)=>`<article class="action"><div class="actiontop"><span class="tileicon tone${i}">${icon(a.icon)}</span><span class="eyebrow">${a.tag}</span></div>${full?`<h3>${a.title}</h3><p>${a.detail}</p><div class="impact"><b>Impact</b><br>${a.impact}</div><button class="softbutton" data-done="${i}" aria-pressed="${completed(a)}">${icon(completed(a)?'check':'leaf')}${completed(a)?'Completed':'Mark complete'}</button>`:`<button class="actionlink" data-detail="${i}"><h3>${a.title}</h3>${icon(completed(a)?'check':'upRight')}</button><p>${a.detail}</p>`}</article>`).join('')}</div>`;
}

function overview() {
    return head('Air quality overview', 'Your local air conditions and practical guidance for the day.', locationButton()) + `<div class="grid">${hero()}${tips()}${chart()}${pollution()}</div><div class="sectionhead"><h2>Your daily action plan</h2><a class="textbutton" href="#plan">View plan ${icon('arrow')}</a></div>${actionCards()}`;
}

function forecast() {
    return head('Air forecast', 'Explore upcoming conditions in local time.', locationButton()) + `<div class="stack wide">${chart()}<section class="card"><h2>Hourly breakdown</h2><p class="sub">${esc(source)} · ${esc(data?.timezone||'Local time')}</p><div class="tablewrap"><table><thead><tr><th>Local time</th><th>US AQI</th><th>Air quality</th></tr></thead><tbody>${points().map(p=>`<tr><td>${localTime(p.t,{weekday:'short',hour:'numeric',minute:'2-digit'})}</td><td>${Math.round(p.v)}</td><td>${bandNames[band(p.v)]}</td></tr>`).join('')}</tbody></table></div></section></div>`;
}

function plan() {
    let items = actions();
    return head('Daily action plan', 'Small changes tailored to your location, household, and travel habits.', locationButton()) + `<div class="summarybox">${icon('leaf')}<div><b>${items.filter(completed).length} of ${items.length} actions completed</b><div class="muted">Today in ${esc(loc.name)} · ${esc(source)}</div></div></div>${actionCards(true)}<div class="sectionhead"><h2>Household guidance</h2><a class="textbutton" href="#household">Edit profile ${icon('arrow')}</a></div><div class="wide">${tips()}</div>`;
}
