(() => {
    const key = 'airwise-theme';
    const system = window.matchMedia('(prefers-color-scheme: dark)');
    let preference;
    try {
        preference = localStorage.getItem(key);
    } catch {
        // Storage may be unavailable in a restricted browser.
    }

    function applyTheme() {
        const dark = preference === 'dark' || (preference !== 'light' && system.matches);
        document.documentElement.dataset.theme = dark ? 'dark' : 'light';
        const toggle = document.getElementById('theme-toggle');
        if (toggle) toggle.setAttribute('aria-pressed', String(dark));
    }

    applyTheme();
    system.addEventListener('change', applyTheme);
    window.addEventListener('storage', event => {
        if (event.key === key || event.key === null) {
            preference = event.newValue;
            applyTheme();
        }
    });
    document.addEventListener('DOMContentLoaded', () => {
        applyTheme();
        document.getElementById('theme-toggle').addEventListener('click', () => {
            preference = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
            applyTheme();
            try {
                localStorage.setItem(key, preference);
            } catch {
                // Keep the selection active for this visit.
            }
        });
    });
})();
