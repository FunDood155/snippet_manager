const menus = Array.from(document.querySelectorAll('[data-menu]'));

function closeDisclosure(disclosure) {
    disclosure.open = false;
    disclosure.querySelector('summary').focus();
}

function closeOtherMenus(event) {
    for (const menu of menus) {
        if (menu.open && !menu.contains(event.target)) menu.open = false;
    }
}

document.addEventListener('click', closeOtherMenus);
document.addEventListener('focusin', closeOtherMenus);

document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    const disclosure = event.target.closest('details[open]');
    if (disclosure) {
        event.preventDefault();
        closeDisclosure(disclosure);
    }
});

document.querySelectorAll('[data-close]').forEach(button => {
    button.hidden = false;
    button.addEventListener('click', () => closeDisclosure(button.closest('details')));
});

document.querySelectorAll('.toast:not(#copy-success, #copy-error)').forEach(toast => {
    const button = toast.querySelector('[data-dismiss]');
    const dismiss = () => {
        if (toast.contains(document.activeElement)) document.querySelector('.composer summary').focus();
        toast.remove();
    };
    button.hidden = false;
    button.addEventListener('click', dismiss);
    if (toast.hasAttribute('data-expire')) {
        window.setTimeout(() => {
            if (!toast.matches(':hover, :focus-within')) dismiss();
        }, 3000);
    }
});

const themeOptions = document.querySelector('.theme-options');
themeOptions.hidden = false;
const currentTheme = document.documentElement.dataset.theme || 'dark';
themeOptions.querySelector(`input[value="${currentTheme}"]`).checked = true;
themeOptions.addEventListener('change', ({ target }) => {
    document.documentElement.dataset.theme = target.value;
    try {
        localStorage.setItem('snippo.theme', target.value);
    } catch {
        // The selection still applies to this page.
    }
});

document.querySelectorAll('[data-expand]').forEach(button => {
    const block = document.getElementById(button.getAttribute('aria-controls'));
    const setExpanded = expanded => {
        block.classList.toggle('code-collapsed', !expanded);
        button.setAttribute('aria-expanded', String(expanded));
        button.textContent = expanded ? 'Collapse code' : 'Expand code';
    };
    button.hidden = false;
    setExpanded(false);
    button.addEventListener('click', () => setExpanded(button.getAttribute('aria-expanded') !== 'true'));
});

const copySuccess = document.getElementById('copy-success');
const copyError = document.getElementById('copy-error');
let copyTimer;

function clearCopyNotices() {
    window.clearTimeout(copyTimer);
    for (const toast of [copySuccess, copyError]) {
        toast.querySelector('p').textContent = '';
        toast.hidden = true;
    }
}

for (const toast of [copySuccess, copyError]) {
    toast.querySelector('button').addEventListener('click', () => {
        document.querySelector('.composer summary').focus();
        clearCopyNotices();
    });
}

document.querySelectorAll('[data-copy]').forEach(button => {
    button.hidden = false;
    button.addEventListener('click', async () => {
        clearCopyNotices();
        try {
            await navigator.clipboard.writeText(JSON.parse(button.dataset.copy));
            copySuccess.hidden = false;
            copySuccess.querySelector('p').textContent = 'Code copied.';
            copyTimer = window.setTimeout(() => {
                if (!copySuccess.matches(':hover, :focus-within')) clearCopyNotices();
            }, 3000);
        } catch {
            copyError.hidden = false;
            copyError.querySelector('p').textContent = 'Clipboard unavailable. Select and copy the code manually.';
        }
    });
});
