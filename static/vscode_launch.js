(() => {
    const link = document.getElementById('open-vscode');
    const { launchMarker: marker, launchExpires } = link.dataset;
    delete link.dataset.launchMarker;
    delete link.dataset.launchExpires;

    try {
        // Links already hold the validated callback. Keep its query out of restored tabs.
        history.replaceState(null, '', location.pathname);
    } catch {
        return; // Keep manual links if the browser cannot update history.
    }

    const expires = Number(launchExpires) * 1000;
    if (!marker || !Number.isSafeInteger(expires) || expires <= Date.now() || !navigator.locks) {
        return;
    }

    let leaving = false;
    window.addEventListener('pagehide', () => { leaving = true; }, { once: true });
    const key = 'snippo.vscode.launches';
    navigator.locks.request(key, { ifAvailable: true }, lock => {
        const now = Date.now();
        if (!lock || leaving || document.visibilityState !== 'visible' || expires <= now) {
            return;
        }
        const entries = JSON.parse(localStorage.getItem(key) ?? '[]')
            .filter(([, until]) => until > now);
        if (entries.length >= 64 || entries.some(([seen]) => seen === marker)) {
            return;
        }
        // Persist before clicking, even if the editor launch is blocked or declined.
        entries.push([marker, expires]);
        localStorage.setItem(key, JSON.stringify(entries));
        link.click();
    }).catch(() => {}); // Storage and lock errors leave the manual links available.
})();
