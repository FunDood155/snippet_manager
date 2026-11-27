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

document.querySelectorAll('.toast').forEach(toast => {
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
