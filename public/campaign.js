const campaignActions = {
    'School families': 'Switch off engines while waiting at school pickup. Invite another family to do the same.',
    'Commuters': 'Combine two car errands into one trip this week, or share the journey with a colleague.',
    'Neighbours': 'Ask drivers to switch off parked engines while waiting outside homes and shops.'
};
const ecosystemFact = 'Ground-level ozone can slow tree growth by making it harder for sensitive leaves to turn sunlight into energy.';

const readyCampaigns = [
    {
        audience: 'School families', title: 'Switch off at pickup.', alt: 'A parent holding car keys greets a child at the school gate.',
        caption: 'Pickup is a good time to catch up with other families. If you’re parked and waiting, switch off your engine. Children waiting by the gate will have one less tailpipe running beside them.',
        action: 'Share this reminder in the school pickup group.', file: 'school-gate'
    },
    {
        audience: 'Commuters', title: 'Two errands, one trip.', alt: 'An illustrated neighbourhood map connects two errands along a single route.',
        caption: 'A pharmacy stop on the way home can save a separate drive tomorrow. Look at the errands on your list and pair two that take you in the same direction.',
        action: 'Pick the two stops you’ll combine this week.', file: 'two-errands'
    },
    {
        audience: 'Neighbours', title: 'Cleaner trips. Greener streets.', alt: 'A giant leaf rises over a green neighbourhood.',
        caption: 'Trees need sunlight to grow. Ground-level ozone can make it harder for sensitive leaves to use that light. Vehicle exhaust contributes to the pollution that forms ozone.',
        action: 'Planning a trip to the shops? Offer a neighbour a lift so one car can stay parked.', file: 'street-trees'
    }
];

function campaignLibrary() {
    return `<section aria-labelledby="libraryTitle"><h2 id="libraryTitle">Ready-to-share campaigns</h2>
        <p class="muted">Download an AI-illustrated poster and share it with the caption below.</p>
        <div class="actiongrid">${readyCampaigns.map((item) => `<article class="action">
          <a href="posters/${item.file}.jpg" aria-label="Open full-size poster: ${esc(item.title)}"><img class="campaign-art" src="posters/${item.file}.jpg" width="1254" height="1254" alt="${esc(item.alt)}"></a>
          <span class="eyebrow">${esc(item.audience)}</span><h3>${esc(item.title)}</h3>
          <p>${esc(item.caption)}</p><p><strong>${esc(item.action)}</strong></p>
          <a class="button" href="posters/${item.file}.jpg" download="airwise-${item.file}.jpg" aria-label="Download poster for ${esc(item.title)}">Download poster</a>
        </article>`).join('')}</div></section>`;
}

function campaign() {
    return head('Campaign studio', 'Create a clean-air message for your community.', locationButton()) +
        campaignLibrary() + `<div class="sectionhead"><h2>Create a local campaign</h2></div><form id="campaignForm" class="card formcard wide">
        <label class="field"><span>Who will see your campaign?</span><select name="audience">${options(Object.keys(campaignActions), profile.household === 'Family with children' ? 'School families' : 'Neighbours')}</select></label>
        <button class="primary">Create campaign</button></form>
        <div role="status" id="campaignStatus"></div><div id="campaignOutput" class="wide"></div>`;
}

function campaignReading() {
    const value = aqi();
    const stamp = data?.current?.time;
    const fresh = source === 'Current estimate' && isFreshReading(data?.current);
    if (!fresh) return `${loc.name} · Current AQI unavailable. Check local air advisories before heading out.`;
    const time = new Date(stamp * 1000).toLocaleString('en-GB', {
        timeZone: data.timezone || 'UTC', dateStyle: 'medium', timeStyle: 'short'
    });
    return `${loc.name} · US AQI ${value} (${bandNames[band(value)]}). Open-Meteo / CAMS estimate, ${time} (${data.timezone || 'UTC'}).`;
}

function renderPoster(canvas, lines, artwork) {
    canvas.width = 1080;
    const ctx = canvas.getContext('2d');
    const rows = [];
    let y = canvas.width + 80;
    for (const [text, size, bold] of lines) {
        const font = `${bold ? 700 : 400} ${size}px sans-serif`;
        ctx.font = font;
        let line = '';
        for (const word of text.split(/\s+/)) {
            const candidate = line ? line + ' ' + word : word;
            if (line && ctx.measureText(candidate).width > 940) {
                rows.push({line, font, y});
                y += size * 1.35;
                line = word;
            } else line = candidate;
        }
        rows.push({line, font, y});
        y += size * 1.35 + 42;
    }
    canvas.height = Math.max(800, Math.ceil(y));
    ctx.fillStyle = '#123735';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#a8dda1';
    ctx.drawImage(artwork, 0, 0, canvas.width, canvas.width);
    rows.forEach(({line, font, y}, index) => {
        ctx.font = font;
        ctx.fillStyle = index === 0 ? '#bdecb8' : '#ffffff';
        ctx.fillText(line, 70, y, 940);
    });
}

document.addEventListener('submit', async event => {
    const form = event.target;
    if (form.id !== 'campaignForm') return;
    event.preventDefault();
    const audience = form.elements.audience.value;
    const reading = campaignReading();
    const action = campaignActions[audience];
    const status = $('#campaignStatus');
    const output = $('#campaignOutput');
    form.querySelector('button').disabled = true;
    status.textContent = 'Preparing your campaign…';
    try {
        const artwork = new Image();
        artwork.src = 'posters/' + readyCampaigns.find(item => item.audience === audience).file + '.jpg';
        const [{headline, author}] = await Promise.all([api('campaign', {audience}), artwork.decode()]);
        if (!form.isConnected) return;
        const parts = [headline, reading, ecosystemFact, action];
        output.innerHTML = `<section class="card"><h2>Campaign preview</h2>
            <canvas style="width:100%;height:auto" aria-hidden="true"></canvas>
            <label class="field"><span>Caption and poster transcript</span><textarea rows="8" readonly></textarea></label>
            <a class="button" download="airwise-clean-air.png">Download PNG</a>
            <p class="sub"><a href="https://www.epa.gov/ground-level-ozone-pollution/ecosystem-effects-ozone-pollution">Source for ozone effects · US EPA</a></p></section>`;
        output.querySelector('textarea').value = parts.join('\n\n');
        const canvas = output.querySelector('canvas');
        renderPoster(canvas, [[`Airwise  /  ${audience}`, 32, true], [headline, 68, true],
            [reading, 35], [ecosystemFact, 38], [action, 42, true]], artwork);
        output.querySelector('[download]').href = canvas.toDataURL('image/png');
        status.textContent = `Campaign ready · ${author}`;
    } catch {
        status.textContent = 'Could not create the campaign. Please try again.';
    } finally {
        form.querySelector('button').disabled = false;
    }
});
