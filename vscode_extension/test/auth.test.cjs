const { createHash } = require('node:crypto');
const assert = require('node:assert/strict');
const { test } = require('node:test');
const {
    AuthClient, AuthUnavailable, SignInRequest, SignInRequired, credentialKey, extensionId, trustedOrigin,
} = require('../out/auth.js');

const origin = 'https://snippets.example.test';
const config = { provider: 'https://auth.example.test', clientId: 'client-id', redirectUri: origin + '/oauth/vscode/callback' };
const tokens = (access, refresh, expires = 3600) => Response.json({
    access_token: access, refresh_token: refresh, expires_in: expires,
});

function storage() {
    const secrets = new Map();
    return {
        get: async key => secrets.get(key),
        store: async (key, value) => { secrets.set(key, value); },
        delete: async key => { secrets.delete(key); },
    };
}

function callback(params, overrides = {}) {
    return {
        scheme: 'vscode', authority: extensionId, path: '/auth', fragment: '',
        query: new URLSearchParams(params).toString(), ...overrides,
    };
}

test('PKCE binds the exact URI and state, and accepts a code once', () => {
    const attempt = new SignInRequest(config, origin);
    const url = attempt.url;
    assert.equal(url.origin, config.provider);
    assert.equal(url.searchParams.get('redirect_uri'), config.redirectUri);
    assert.equal(url.searchParams.get('code_challenge_method'), 'S256');
    assert.equal(url.searchParams.get('code_challenge'), createHash('sha256').update(attempt.verifier).digest('base64url'));
    assert.equal(url.searchParams.get('scope'), 'openid email');
    assert.equal(url.searchParams.get('state'), attempt.state);
    const params = { state: attempt.state, code: 'synthetic-code' };
    for (const overrides of [{ authority: 'wrong' }, { scheme: 'https' }, { path: '/other' }, { fragment: 'extra' }]) {
        assert.equal(attempt.accept(callback(params, overrides), 'vscode'), undefined);
    }
    assert.equal(attempt.accept(callback({ ...params, state: 'wrong' }), 'vscode'), undefined);
    assert.equal(attempt.accept(callback(params, { query: 'state=' + attempt.state + '&state=extra&code=foo' }), 'vscode'), undefined);
    assert.equal(attempt.accept(callback({ ...params, error: 'access_denied' }), 'vscode'), undefined);
    assert.equal(attempt.accept(callback(params), 'vscode'), 'synthetic-code');
    assert.equal(attempt.accept(callback(params), 'vscode'), undefined);
});

test('expired callbacks and cancellation do not authorize', async () => {
    const attempt = new SignInRequest(config, origin);
    attempt.expires = Date.now() - 1;
    assert.equal(attempt.accept(callback({ state: attempt.state, code: 'foo' }), 'vscode'), undefined);
    const denied = new SignInRequest(config, origin);
    assert.equal(denied.accept(callback({ state: denied.state, error: 'access_denied' }), 'vscode'), null);
    const secrets = storage();
    const auth = new AuthClient(secrets, () => origin, () => assert.fail('canceled attempt should not call network'));
    await assert.rejects(auth.complete(new SignInRequest(config, origin), 'code', AbortSignal.abort()), SignInRequired);
    assert.equal(await auth.hasSession(), false);
});

test('checks server origin, redirect and HTTPS requirements', async () => {
    for (const url of ['http://outside.test', 'https://user:pass@example.test', 'https://example.test/extra']) {
        assert.throws(() => trustedOrigin(url));
    }
    assert.equal(trustedOrigin('http://127.0.0.1:54321'), 'http://127.0.0.1:54321');
    for (const data of [
        { ...config, redirectUri: 'https://other.test/oauth/vscode/callback' },
        { ...config, provider: 'http://localhost:54321' },
    ]) {
        const auth = new AuthClient(storage(), () => origin, async (_url, init) => {
            assert.equal(init.redirect, 'error');
            return Response.json(data);
        });
        await assert.rejects(auth.configuration());
    }
});

test('exchanges once, persists across restart, serializes refresh, and revokes on sign-out', async () => {
    const secrets = storage();
    const requests = [];
    const http = async (url, init) => {
        const path = new URL(url).pathname;
        requests.push([path, init]);
        if (path === '/oauth/vscode/config') {
            return Response.json(config);
        }
        if (path.endsWith('/token')) {
            if (init.body.get('grant_type') === 'authorization_code') {
                assert.equal(init.body.get('client_id'), config.clientId);
                assert.equal(init.body.get('code'), 'code');
                assert.equal(init.body.get('code_verifier'), attempt.verifier);
                assert.equal(init.body.get('redirect_uri'), config.redirectUri);
                return tokens('old', 'old-refresh', 5);
            }
            assert.equal(init.body.get('refresh_token'), 'old-refresh');
            return tokens('renewed', 'new-refresh');
        }
        assert.equal(init.headers.Authorization, 'Bearer renewed');
        if (path.endsWith('/logout')) {
            assert.equal(init.method, 'POST');
            return new Response(null, { status: 204 });
        }
        return Response.json([]);
    };
    const auth = new AuthClient(secrets, () => origin, http);
    const attempt = await auth.configuration();
    await auth.complete(attempt, 'code', new AbortController().signal);
    const restarted = new AuthClient(secrets, () => origin, http);
    assert.equal(await restarted.hasSession(), true);
    await Promise.all([restarted.request('/api/snippets'), restarted.request('/api/snippets')]);
    assert.equal(requests.filter(([path]) => path.endsWith('/token')).length, 2);
    assert.equal(await restarted.signOut(), true);
    assert.equal(await secrets.get(credentialKey), undefined);
    await assert.rejects(restarted.request('/api/snippets'), SignInRequired);
});

test('invalid and replayed exchange fail, transient renewal preserves credentials', async () => {
    const secrets = storage();
    const attempt = new SignInRequest(config, origin);
    let action = 'reject';
    const http = async () => {
        if (action === 'offline') {
            throw new Error('network error');
        }
        return action === 'valid' ? tokens('access', 'refresh', 1) : new Response(null, { status: 400 });
    };
    const auth = new AuthClient(secrets, () => origin, http);
    const signal = new AbortController().signal;
    await assert.rejects(auth.complete(attempt, 'expired-or-already-used', signal), SignInRequired);
    assert.equal(await auth.hasSession(), false);
    action = 'valid';
    await auth.complete(attempt, 'valid', signal);
    action = 'offline';
    await assert.rejects(auth.request('/api/snippets'), AuthUnavailable);
    assert.equal(await auth.hasSession(), true);
    action = 'reject';
    await assert.rejects(auth.request('/api/snippets'), SignInRequired);
    assert.equal(await auth.hasSession(), false);
});
