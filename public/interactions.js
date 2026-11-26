function options(values, current) {
    return values.map(v => `<option${v===current?' selected':''}>${esc(v)}</option>`).join('');
}

function household() {
    return head('Household profile', 'Personalize your routines and precautions.') + `<form class="card formcard wide" id="profileForm">${cardTitle('users','Lifestyle preferences')}<label class="field"><span>Household or community</span><select name="household">${options(['Adults','Family with children','Older adults','Sensitive household','Community group'],profile.household)}</select></label><label class="field"><span>Usual travel</span><select name="travel">${options(['Car','Public transport','Walking or cycling'],profile.travel)}</select></label><label class="field"><span>Indoor filtration</span><select name="home">${options(['No air purifier','Air purifier available'],profile.home)}</select></label><button class="primary">Save preferences ${icon('check')}</button></form>`;
}

function assistant() {
    const prompts = ['How can I improve my indoor air?', 'Plan a lower-emission commute', 'Help me plan outdoor time'];
    return head('Airwise assistant', 'Ask about cleaner air at home, on the move, or in your community.') + `<section class="card wide"><div class="cardhead">${cardTitle('spark','Ask Airwise')}<span class="muted">${esc(loc.name)}</span></div><div class="talk" id="talk" role="log" aria-live="polite">${messages.length?messages.map(m=>`<div class="message ${m.role}"><small>${esc(m.label)}</small>${esc(m.content)}</div>`).join(''):`<div class="message"><small>Airwise</small>What would you like to plan for your household in ${esc(loc.name)}?</div>`}${pending?'<div class="muted" role="status">Preparing your answer…</div>':''}</div><div class="promptlist">${prompts.map((p,i)=>`<button class="button" data-prompt="${i}" ${pending?'disabled':''}>${p}</button>`).join('')}</div><form class="composer" id="chatForm"><textarea rows="1" name="question" aria-label="Question for Airwise" placeholder="Ask about your air, routines, or household…" required maxlength="1200" ${pending?'disabled':''}></textarea><button class="primary" ${pending?'disabled':''}>Send ${icon('send')}</button></form></section>`;
}

function alerts() {
    let native = alertConfig.desktop,
        enabled = native ? alertConfig.enabled : get('browserAlerts', false),
        threshold = native ? alertConfig.threshold : get('threshold', 101);
    let history = native ? alertConfig.history : get('browserHistory', []);
    return head('Air alerts', 'Get the current AQI and a practical precaution for your saved location.', locationButton()) + `<div class="sectiongrid"><form class="card formcard" id="alertForm">${cardTitle('bell','Notification settings')}<label class="field"><span>Delivery</span><select name="enabled">${options(['Off',native?'Windows desktop notifications':'Browser notifications'],enabled?(native?'Windows desktop notifications':'Browser notifications'):'Off')}</select><small>${native?'Airwise checks every 10 minutes while the local server is running, including when this tab is closed.':'Airwise checks every 10 minutes while this page is open. Browser permission is required.'}</small></label><label class="field"><span>Notify me at</span><select name="threshold">${[[0,'Every new reading'],[51,'Moderate or above · 51+'],[101,'Sensitive groups or above · 101+'],[151,'Unhealthy or above · 151+'],[201,'Very unhealthy or above · 201+'],[301,'Hazardous · 301+']].map(([n,s])=>`<option value="${n}" ${threshold===n?'selected':''}>${s}</option>`).join('')}</select></label><div class="muted">Alert location · ${esc(enabled&&native&&alertConfig.location?alertConfig.location.name:cityName())}</div><button class="primary" ${alertsReady?'':'disabled'}>Save alerts ${icon('check')}</button></form><section class="card">${cardTitle('clock','Recent alerts')}${alertConfig.error?`<p class="impact">${esc(alertConfig.error)}</p>`:''}${history?.length?history.map(h=>`<div class="historyentry"><b>${esc(h.city)} · US AQI ${esc(h.aqi)}</b><small class="sub"> · ${new Date(h.time*1000).toLocaleString()}</small><p class="muted">${esc(h.body)}</p></div>`).join(''):'<p class="empty">Delivered AQI alerts will appear here.</p>'}</section></div>`;
}
const pages = {
    campaign,
    overview,
    forecast,
    plan,
    assistant,
    alerts,
    household
};

function render() {
    const page = route();
    document.title = `Airwise · ${titles[page]}`;
    $('#crumb').textContent = titles[page];
    $('#sidecity').textContent = cityName();
    $('#date').innerHTML = icon('calendar') + esc(localTime(Date.now() / 1000, {
        weekday: 'short',
        month: 'short',
        day: 'numeric',
        year: 'numeric'
    }));
    document.querySelectorAll('[data-nav]').forEach(a => {
        let active = a.dataset.nav === page;
        a.classList.toggle('active', active);
        if (active) a.setAttribute('aria-current', 'page');
        else a.removeAttribute('aria-current');
    });
    main.innerHTML = pages[page]() + `<footer class="footer"><span>Air data · <a href="https://open-meteo.com/en/docs/air-quality-api" target="_blank" rel="noreferrer">Open-Meteo</a> / <a href="https://atmosphere.copernicus.eu/" target="_blank" rel="noreferrer">CAMS</a> · Modeled US AQI</span><span>Guidance · <a href="https://www.airnow.gov/aqi/aqi-basics/" target="_blank" rel="noreferrer">AirNow</a> / <a href="https://www.epa.gov/wildfires/how-create-cleaner-air-room-home" target="_blank" rel="noreferrer">EPA</a></span></footer>`;
    const talk = $('#talk');
    if (talk) talk.scrollTop = talk.scrollHeight;
}

function refreshDataViews() {
    if (['overview', 'plan', 'forecast'].includes(route())) render();
}

function cacheKey() {
    return 'air/' + loc.lat + '/' + loc.lon;
}
async function loadObservation(seq) {
    try {
        const result = await api(`observation?lat=${encodeURIComponent(loc.lat)}&lon=${encodeURIComponent(loc.lon)}`);
        if (seq !== airRequest) return;
        const reading = result.observation;
        sensorStatus = reading
            ? `Outdoor sensor #${reading.sensor} within 10 km measured PM2.5 at ${reading.pm2_5.toFixed(1)} µg/m³ and PM10 at ${reading.pm10.toFixed(1)} µg/m³ · ${new Date(reading.time * 1000).toLocaleTimeString([], {hour: 'numeric', minute: '2-digit', timeZoneName: 'short'})}`
            : 'No recent outdoor sensor reading within 10 km.';
    } catch {
        if (seq !== airRequest) return;
        sensorStatus = 'Sensor readings are temporarily unavailable.';
    }
    if (route() === 'overview') refreshDataViews();
}

async function loadAir(changed = false) {
    const seq = ++airRequest,
        key = cacheKey();
    sensorStatus = 'Checking nearby sensors…';
    loadObservation(seq);
    if (changed || !data) {
        const cached = get(key, null);
        if (cached?.current) {
            data = cached;
            source = 'Saved reading';
        } else if (loc.lat === cities[0].lat && loc.lon === cities[0].lon) {
            data = sample();
            source = 'Sample data';
        } else {
            data = null;
            source = 'Checking';
        }
        refreshDataViews();
    }
    try {
        let fresh = await api(`air?lat=${encodeURIComponent(loc.lat)}&lon=${encodeURIComponent(loc.lon)}`);
        if (seq !== airRequest) return;
        if (!Number.isFinite(fresh.current?.us_aqi) || Math.abs(Date.now() / 1000 - fresh.current.time) > 7200) throw Error();
        data = fresh;
        source = 'Current estimate';
        set(key, fresh);
        browserNotify();
    } catch {
        if (seq !== airRequest) return;
        source = source === 'Sample data' ? source : data ? 'Saved reading' : 'Unavailable';
    }
    refreshDataViews();
}

function browserNotify() {
    if (alertConfig.desktop || !get('browserAlerts', false) || !('Notification' in window) || Notification.permission !== 'granted') return;
    const key = cacheKey() + '/' + data.current.time,
        n = aqi();
    if (get('lastAlert', '') === key || n < get('threshold', 101)) return;
    let body = precautions()[0][1];
    try {
        new Notification(`Airwise · ${loc.name} · US AQI ${n}`, {
            body,
            icon: 'icon.svg',
            tag: 'airwise-aqi'
        });
        set('lastAlert', key);
        set('browserHistory', [{
            city: loc.name,
            time: data.current.time,
            aqi: n,
            body
        }, ...get('browserHistory', [])].slice(0, 20));
    } catch {
        note('Browser notifications are unavailable on this device.');
    }
}
async function loadAlerts(background = false) {
    try {
        alertConfig = await api('alerts');
        const latest = alertConfig.history?.[0];
        if (alertConfig.enabled && latest) {
            const key = latest.city + '/' + latest.time;
            if (get('seenDesktopAlert', '') !== key) {
                note(latest.city + ' · US AQI ' + latest.aqi + '. ' + latest.body);
                set('seenDesktopAlert', key);
            }
        }
    } catch {
        alertConfig = {
            enabled: false,
            desktop: false,
            history: [],
            threshold: 101
        };
    }
    alertsReady = true;
    if (route() === 'alerts' && (!background || !document.activeElement?.closest('#alertForm'))) render();
}

function showDialog(title, body) {
    $('#dialogContent').innerHTML = `<div class="dialoghead"><h2 id="dialogTitle">${esc(title)}</h2><button class="iconbutton" data-act="close" aria-label="Close">${icon('close')}</button></div>${body}`;
    dialog.setAttribute('aria-labelledby', 'dialogTitle');
    if (!dialog.open) dialog.showModal();
}
let found = [],
    searchSequence = 0,
    searchTimer;

function results(list, message = '') {
    found = list;
    let el = $('#results');
    if (!el) return;
    el.innerHTML = list.map((p, i) => `<button class="result" data-city="${i}">${icon('pin')}<span><b>${esc(p.name)}</b><small>${esc([p.region,p.country].filter(Boolean).join(', '))}</small></span></button>`).join('') + (message ? `<p class="muted">${esc(message)}</p>` : '');
}

function locationDialog() {
    searchSequence++;
    showDialog('Set your location', `<input id="search" class="searchbox" placeholder="Search cities worldwide" type="search" aria-label="Search cities worldwide" autocomplete="off"><div class="results" id="results" aria-live="polite"></div><button class="softbutton" data-act="device">${icon('target')}Use my location</button>`);
    results(cities);
    $('#search').focus();
    $('#search').addEventListener('input', () => {
        let q = $('#search').value.trim(),
            seq = ++searchSequence;
        clearTimeout(searchTimer);
        if (q.length < 2) {
            results(cities, q ? 'Enter at least two letters.' : '');
            return;
        }
        const local = cities.filter(p => p.name.toLowerCase().includes(q.toLowerCase()));
        results(local, 'Searching…');
        searchTimer = setTimeout(async () => {
            try {
                let r = await api('locations?q=' + encodeURIComponent(q));
                if (seq === searchSequence) results(r, r.length ? '' : 'No matching cities found.');
            } catch {
                if (seq === searchSequence) results(local, 'Online city search is unavailable.');
            }
        }, 280);
    });
}
async function choose(p) {
    loc = p;
    set('location', p);
    chatVersion++;
    messages = [];
    pending = false;
    dialog.close();
    render();
    loadAir(true);
    if (alertConfig.desktop && alertConfig.enabled) {
        try {
            alertConfig = {
                ...alertConfig,
                ...await api('alerts', {
                    enabled: true,
                    threshold: alertConfig.threshold,
                    location: loc
                })
            };
        } catch {
            note('Location changed. Open Air alerts to update desktop monitoring.');
        }
    }
    if (route() === 'alerts') render();
}

function detail(i) {
    let a = actions()[i];
    showDialog(a.title, `<p>${a.detail}</p><div class="impact"><b>Impact</b><br>${a.impact}</div><button class="primary" data-done="${i}">${icon('check')}${completed(a)?'Undo completion':'Mark complete'}</button>`);
}

function toggleDone(i) {
    let a = actions()[i],
        all = get('completed', {}),
        today = dayKey(),
        list = new Set(all[today] || []);
    if (list.has(a.id)) list.delete(a.id);
    else list.add(a.id);
    all[today] = [...list];
    set('completed', Object.fromEntries(Object.entries(all).slice(-30)));
    if (dialog.open) dialog.close();
    render();
    note(list.has(a.id) ? 'Action completed for today.' : 'Action marked as pending.');
}
async function ask(question) {
    question = question.trim();
    if (!question || pending) return;
    const version = chatVersion,
        history = messages.slice(-4).map(({
            role,
            content
        }) => ({
            role,
            content
        }));
    messages.push({
        role: 'user',
        label: 'You',
        content: question
    });
    pending = true;
    render();
    try {
        let r = await api('assistant', {
            location: loc,
            profile,
            question,
            history
        });
        if (version === chatVersion) messages.push({
            role: 'assistant',
            label: r.mode,
            content: r.answer
        });
    } catch {
        const choice = /home|indoor|cook|window|purif/i.test(question) ? 1 : /commut|travel|car|bus|school/i.test(question) ? 0 : 2,
            a = actions()[choice];
        if (version === chatVersion) messages.push({
            role: 'assistant',
            label: 'Local guide · AI unavailable',
            content: `${a.detail} ${a.impact} ${source==='Current estimate'?`The current modeled US AQI for ${loc.name} is ${aqi()}.`:'Check your local AQI before going outdoors.'}`
        });
    } finally {
        if (version === chatVersion) {
            pending = false;
            if (route() === 'assistant') render();
        }
    }
}

function menu(open) {
    $('#sidebar').classList.toggle('open', open);
    document.body.classList.toggle('menuopen', open);
    $('#menu').setAttribute('aria-expanded', String(open));
}
$('#menu').onclick = () => menu(true);
$('#scrim').onclick = () => menu(false);
window.addEventListener('hashchange', () => {
    menu(false);
    render();
    window.scrollTo(0, 0);
    if (route() === 'alerts') loadAlerts();
});
document.addEventListener('keydown', e => {
    if (e.key === 'Escape') menu(false);
});
dialog.addEventListener('click', e => {
    if (e.target === dialog) dialog.close();
});
document.addEventListener('click', e => {
    let b = e.target.closest('button');
    if (!b) return;
    if (b.dataset.act === 'location') locationDialog();
    if (b.dataset.act === 'close') dialog.close();
    if (b.dataset.act === 'device') {
        if (!navigator.geolocation) {
            note('Location access is unavailable. Search for a city.');
            return;
        }
        b.disabled = true;
        navigator.geolocation.getCurrentPosition(pos => {
            if (dialog.open) choose({
                name: 'Current location',
                country: '',
                lat: +pos.coords.latitude.toFixed(4),
                lon: +pos.coords.longitude.toFixed(4)
            });
        }, () => {
            b.disabled = false;
            note('Location access failed. Search for a city instead.');
        }, {
            timeout: 12000
        });
    }
    if (b.dataset.city !== undefined) choose(found[Number(b.dataset.city)]);
    if (b.dataset.hours) {
        hours = Number(b.dataset.hours);
        render();
    }
    if (b.dataset.detail !== undefined) detail(Number(b.dataset.detail));
    if (b.dataset.done !== undefined) toggleDone(Number(b.dataset.done));
    if (b.dataset.prompt !== undefined) ask(b.textContent);
});
document.addEventListener('submit', async e => {
    const f = e.target;
    if (!['profileForm', 'alertForm', 'chatForm'].includes(f.id)) return;
    e.preventDefault();
    let values = Object.fromEntries(new FormData(f));
    if (f.id === 'profileForm') {
        profile = values;
        set('profile', values);
        note('Household preferences saved. Your action plan is updated.');
        return;
    }
    if (f.id === 'chatForm') {
        ask(values.question);
        return;
    }
    const enabled = values.enabled !== 'Off',
        threshold = Number(values.threshold);
    f.querySelector('button').disabled = true;
    try {
        if (alertConfig.desktop) {
            alertConfig = {
                ...alertConfig,
                ...await api('alerts', {
                    enabled,
                    threshold,
                    location: loc
                })
            };
        } else {
            if (enabled && (!('Notification' in window) || await Notification.requestPermission() !== 'granted')) {
                note('Allow notifications in browser settings to enable alerts.');
                return;
            }
            set('threshold', threshold);
            set('browserAlerts', enabled);
            if (source === 'Current estimate') browserNotify();
        }
        note('Air alert preferences saved.');
        render();
        if (enabled && alertConfig.desktop) setTimeout(() => loadAlerts(true), 2500);
    } catch {
        note('Could not save alert preferences. Please try again.');
    } finally {
        let btn = $('#alertForm button');
        if (btn) btn.disabled = false;
    }
});
render();
loadAlerts();
loadAir();
setInterval(() => loadAir(), 600000);
setInterval(() => { if (alertConfig.enabled) loadAlerts(true); }, 60000);
