const assert = require('node:assert/strict');
const { test } = require('node:test');
const { AuthClient, SaveSessionChanged, SaveUnconfirmed, SignInRequired } = require('../out/auth.js');

const origin = 'https://snippo.example.test';
const fields = { name: 'Fixture', cat: 'Examples', language: 'python', code: '  x = 1  \r\n' };

function fixture() {
    const config = { provider: 'https://auth.example.test', clientId: 'client', redirectUri: origin + '/oauth/vscode/callback' };
    const session = (access, expires = Date.now() + 1000) => ({ origin, config, tokens: { access, refresh: access + '-refresh', expires } });
    let saved = JSON.stringify(session('original'));
    let activeOrigin = origin;
    let current = true;
    const writes = [];
    const state = {
        writes,
        beforeRefresh: () => {},
        post: () => Response.json({ sno: 1, ...fields }, { status: 201 }),
        switchAccount: () => { saved = JSON.stringify(session('different-account')); },
        switchServer: () => { activeOrigin = 'https://other.example.test'; },
        invalidateDraft: () => { current = false; },
        saved: () => saved,
    };
    const storage = {
        get: async () => saved,
        store: async (_key, value) => { saved = value; },
        delete: async () => { saved = undefined; },
    };
    const auth = new AuthClient(storage, () => activeOrigin, async (url, options) => {
        if (url === config.provider + '/auth/v1/oauth/token') {
            assert.equal(options.body.get('grant_type'), 'refresh_token');
            await state.beforeRefresh();
            return Response.json({ access_token: 'renewed', refresh_token: 'renewed-refresh', expires_in: 3600 });
        }
        if (options.method === 'GET') return Response.json([]);
        assert.equal(url, origin + '/api/snippets?v=2');
        writes.push(options);
        return state.post();
    });
    return { ...state, auth, prepare: () => auth.prepareSnippetSave(() => current), state };
}

test('a refresh during prompts follows the same session and sends exactly one confirmed POST', async () => {
    const f = fixture();
    const draft = await f.prepare();
    await f.auth.request('/api/snippets');
    assert.equal(f.writes.length, 0);
    const result = await Promise.allSettled([draft.save(fields), draft.save(fields)]);
    assert.equal(result[0].value.status, 201);
    assert.ok(result[1].reason instanceof SaveSessionChanged);
    assert.equal(f.writes.length, 1);
    assert.equal(f.writes[0].headers.Authorization, 'Bearer renewed');
    assert.deepEqual(JSON.parse(f.writes[0].body), fields);
    draft.dispose();
});

test('cancellation, an account switch, a server switch or an invalidated draft prevent transmission', async () => {
    for (const stop of ['dispose', 'switchAccount', 'switchServer', 'invalidateDraft']) {
        const f = fixture();
        const draft = await f.prepare();
        (stop === 'dispose' ? draft.dispose : f[stop])();
        await assert.rejects(draft.save(fields), SaveSessionChanged);
        assert.equal(f.writes.length, 0);
        draft.dispose();
    }
});

test('credentials replaced during refresh cause no POST and keep the new account', async () => {
    const f = fixture();
    f.state.beforeRefresh = f.switchAccount;
    const draft = await f.prepare();
    await assert.rejects(draft.save(fields), /session changed/i);
    assert.equal(f.writes.length, 0);
    assert.equal(JSON.parse(f.saved()).tokens.access, 'different-account');
    draft.dispose();
});

test('authentication rejection and lost response do not repeat a POST', async () => {
    for (const failure of ['unauthorized', 'lost']) {
        const f = fixture();
        f.state.post = () => {
            if (failure === 'unauthorized') return new Response(null, { status: 401 });
            throw new Error('response lost');
        };
        const draft = await f.prepare();
        await assert.rejects(draft.save(fields), failure === 'unauthorized' ? SignInRequired : SaveUnconfirmed);
        assert.equal(f.writes.length, 1);
        assert.equal(Boolean(f.saved()), failure === 'lost');
        draft.dispose();
    }
});
