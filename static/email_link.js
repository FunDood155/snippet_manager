const hashes = new URLSearchParams(location.hash.slice(1)).getAll('token_hash');
history.replaceState(null, '', location.pathname);

if (hashes.length === 1 && /^[A-Za-z0-9_-]{20,256}$/.test(hashes[0])) {
    document.querySelector('input[name="token_hash"]').value = hashes[0];
    document.getElementById('email-link-continue').disabled = false;
} else {
    document.getElementById('email-link-error').hidden = false;
}
