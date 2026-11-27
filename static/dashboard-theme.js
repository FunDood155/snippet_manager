try {
    if (localStorage.getItem('snippo.theme') === 'light') document.documentElement.dataset.theme = 'light';
} catch {
    // The default dark theme also works when storage is unavailable.
}
