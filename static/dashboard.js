function closeDisclosure(disclosure) {
    disclosure.open = false;
    disclosure.querySelector('summary').focus();
}

function closeOtherMenus(event) {
    for (const menu of document.querySelectorAll('[data-menu][open]')) {
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

function bindLibraryControls(root) {
    root.querySelectorAll('[data-close]').forEach(button => {
        button.hidden = false;
        button.addEventListener('click', () => closeDisclosure(button.closest('details')));
    });

    root.querySelectorAll('.toast').forEach(toast => {
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

    root.querySelectorAll('[data-expand]').forEach(button => {
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

    root.querySelectorAll('[data-copy]').forEach(button => {
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
}

const libraryStatus = document.getElementById('library-status');
const libraryContent = () => document.getElementById('library-content');
const libraryNotices = () => document.getElementById('library-notices');
const fragmentHeaders = { 'X-Snippo-Fragment': 'library' };
let activeRead;
let writing = false;
let pendingHistory = false;

function announce(message) {
    libraryStatus.textContent = message;
}

function showLibraryError(message) {
    const notices = libraryNotices();
    const toast = document.createElement('div');
    toast.className = 'toast error';
    const text = document.createElement('p');
    text.setAttribute('role', 'alert');
    text.textContent = message;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'quiet';
    button.dataset.dismiss = '';
    button.setAttribute('aria-label', 'Dismiss notification');
    button.textContent = '×';
    toast.append(text, button);
    notices.replaceChildren(toast);
    bindLibraryControls(notices);
}

function openSignIn(response) {
    if (response.redirected && new URL(response.url).origin === location.origin) {
        location.assign(response.url);
        return true;
    }
    return false;
}

function draftFrom(content) {
    const composer = content.querySelector('.composer[open]');
    if (composer && content.dataset.editor === 'add') {
        const fields = new FormData(composer.querySelector('form'));
        const values = ['name', 'cat', 'code'].map(name => [name, fields.get(name)]);
        if (values.some(([, value]) => value)) return values;
    }
}

function settleFragment(next, notices, options) {
    const previous = libraryContent();
    const focused = previous.contains(document.activeElement) ? document.activeElement : null;
    const sourceCard = focused?.closest('[data-snippet-id]')?.dataset.snippetId;
    const hiddenOpen = previous.querySelector('#hidden-defaults').open;
    const expanded = new Set([...previous.querySelectorAll('[data-expand][aria-expanded="true"]')]
        .map(button => button.getAttribute('aria-controls')));
    if (options.keepEditor && previous.dataset.editor !== 'add' && next.dataset.editor === 'add') {
        next.querySelector('.composer').replaceWith(previous.querySelector('.composer'));
        next.dataset.editor = previous.dataset.editor;
        next.dataset.location = previous.dataset.location;
    }
    if (options.keepDraft && next.dataset.editor === 'add') {
        const draft = draftFrom(previous);
        if (draft) {
            const composer = next.querySelector('.composer');
            composer.open = true;
            for (const [name, value] of draft) composer.querySelector('form').elements[name].value = value;
        }
    }
    if (!options.keepEditor && options.keepDraft && !options.editorFocus && previous.dataset.editor !== 'add' &&
        next.dataset.location === previous.dataset.location) {
        const oldFields = previous.querySelector('.composer-form').elements;
        for (const name of ['name', 'cat', 'code']) next.querySelector('.composer-form').elements[name].value = oldFields[name].value;
    }
    previous.replaceWith(next);
    if (!options.keepNotices) libraryNotices().replaceWith(notices);
    bindLibraryControls(next);
    if (!options.keepNotices) bindLibraryControls(notices);
    if (hiddenOpen && options.keepHidden) next.querySelector('#hidden-defaults').open = true;
    for (const button of next.querySelectorAll('[data-expand]')) {
        if (expanded.has(button.getAttribute('aria-controls'))) button.click();
    }
    const destination = new URL(next.dataset.location, location.href);
    if (destination.origin === location.origin && options.history && destination.href !== location.href) {
        if (options.history === 'replace') history.replaceState(null, '', destination);
        else history.pushState(null, '', destination);
    }
    if (focused || options.editorFocus) {
        const card = sourceCard && [...next.querySelectorAll('[data-snippet-id]')]
            .find(item => item.dataset.snippetId === sourceCard);
        const target = options.editorFocus ? next.querySelector('.composer input[name="name"]') :
            focused?.matches('.scopes a') ? next.querySelector('.scopes [aria-current]') :
            focused?.id ? document.getElementById(focused.id) :
            focused?.matches('input[name="search"]') ? next.querySelector('input[name="search"]') :
            focused?.matches('[rel]') ? next.querySelector('.library-pages [rel]') :
            card?.querySelector(focused.matches('.star') ? '.star' : '[data-menu] summary');
        (target || next.querySelector('.composer summary')).focus({ preventScroll: !options.editorFocus });
    }
    const count = next.querySelector('.results-count');
    if (count) announce(count.textContent);
}

async function getFragment(response) {
    const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
    const next = doc.getElementById('library-content');
    const notices = doc.getElementById('library-notices');
    if (!next || !notices) throw new Error('Unexpected library response');
    return [next, notices];
}

async function readLibrary(url, options = {}) {
    activeRead?.abort();
    const request = new AbortController();
    activeRead = request;
    libraryContent().setAttribute('aria-busy', 'true');
    announce('Loading snippets…');
    const timeout = setTimeout(() => request.abort('timeout'), 12000);
    try {
        const response = await fetch(url, { headers: fragmentHeaders, cache: 'no-store', signal: request.signal });
        if (request.signal.aborted || activeRead !== request) return;
        if (openSignIn(response)) return;
        if (!response.ok) throw new Error('Library load failed');
        const fragment = await getFragment(response);
        if (!request.signal.aborted && activeRead === request) {
            settleFragment(...fragment, { keepDraft: true, keepHidden: true, ...options });
        }
    } catch {
        if ((!request.signal.aborted || request.signal.reason === 'timeout') && activeRead === request) {
            if (options.popstate) {
                location.assign(url);
                return;
            }
            showLibraryError('Could not refresh the library. Try again.');
            announce('');
        }
    } finally {
        clearTimeout(timeout);
        if (activeRead === request) {
            activeRead = undefined;
            libraryContent().removeAttribute('aria-busy');
        }
    }
}

async function writeLibrary(form) {
    const previousRead = activeRead;
    activeRead = undefined;
    previousRead?.abort();
    writing = true;
    const values = new URLSearchParams(new FormData(form));
    const buttons = [...form.querySelectorAll('button[type="submit"]')];
    buttons.forEach(button => { button.disabled = true; });
    announce('Saving changes…');
    libraryContent().setAttribute('aria-busy', 'true');
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
        const response = await fetch(form.getAttribute('action'), {
            method: 'POST', body: values, headers: fragmentHeaders, cache: 'no-store', signal: controller.signal,
        });
        if (openSignIn(response)) return;
        if (response.status >= 500) throw new Error('Mutation status unknown');
        if (response.status === 429 || response.status === 413) {
            showLibraryError(response.status === 429 ? 'Too many attempts. Try again later.' : 'This snippet is too large.');
            return;
        }
        let fragment;
        try {
            fragment = await getFragment(response);
        } catch (error) {
            if (response.ok) throw error;
            showLibraryError('The request was rejected. Reload the page before trying again.');
            return;
        }
        const editing = form.matches('.composer-form');
        settleFragment(...fragment, { history: response.ok && !pendingHistory ? 'replace' : undefined,
            keepHidden: true, keepDraft: !editing, keepEditor: !editing });
    } catch {
        showLibraryError('Could not confirm the change. Check the refreshed library before retrying.');
        if (!pendingHistory) await readLibrary(location.href, { keepNotices: true });
    } finally {
        clearTimeout(timeout);
        buttons.forEach(button => { button.disabled = false; });
        writing = false;
        libraryContent().removeAttribute('aria-busy');
        announce('');
        if (pendingHistory) {
            pendingHistory = false;
            void readLibrary(location.href, { popstate: true });
        }
    }
}

document.addEventListener('click', event => {
    const link = event.target.closest('a[data-library-nav]');
    if (!link || event.defaultPrevented || event.button !== 0 ||
        event.metaKey || event.ctrlKey || event.shiftKey || event.altKey ||
        new URL(link.href).origin !== location.origin) return;
    event.preventDefault();
    if (writing) return;
    const editorFocus = link.matches('.menu-panel a');
    void readLibrary(link.href, { history: 'push', editorFocus });
});

document.addEventListener('submit', event => {
    const form = event.target;
    if (!form.matches('[data-library-read], [data-library-write]')) return;
    event.preventDefault();
    if (writing) return;
    if (form.matches('[data-library-write]')) {
        void writeLibrary(form);
        return;
    }
    const url = new URL(form.action);
    url.search = new URLSearchParams(new FormData(form));
    void readLibrary(url, { history: 'push' });
});

window.addEventListener('popstate', () => {
    if (writing) pendingHistory = true;
    else void readLibrary(location.href, { popstate: true });
});

bindLibraryControls(document.querySelector('.topbar'));
bindLibraryControls(libraryContent());
bindLibraryControls(libraryNotices());
