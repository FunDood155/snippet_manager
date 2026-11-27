const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { runInNewContext } = require('node:vm');
const assert = require('node:assert/strict');
const { test } = require('node:test');

const script = readFileSync(join(__dirname, '../static/vscode_launch.js'), 'utf8');
const marker = 'a'.repeat(64);

async function page({
    store = new Map(), eligible = marker, expires = 120, now = 60000,
    available = true, storageBlocked = false, lockBlocked = false, protocolBlocked = false,
    leaving = false, visibility = 'visible',
} = {}) {
    let launches = 0;
    let path;
    let pagehide;
    const link = {
        dataset: eligible ? { launchMarker: eligible, launchExpires: String(expires) } : {},
        click() {
            launches++;
            if (protocolBlocked) throw new Error('Protocol blocked');
        },
    };
    runInNewContext(script, {
        Date: { now: () => now }, location: { pathname: '/oauth/vscode/callback' },
        history: { replaceState(_state, _title, next) { path = next; } },
        document: { getElementById: () => link, visibilityState: visibility },
        window: { addEventListener: (_event, callback) => { pagehide = callback; } },
        navigator: {
            locks: lockBlocked ? undefined : {
                request: async (_key, options, callback) => {
                    assert.equal(options.ifAvailable, true);
                    if (leaving) pagehide();
                    callback(available ? {} : null);
                },
            },
        },
        localStorage: {
            getItem: key => store.get(key),
            setItem(key, value) {
                if (storageBlocked) throw new Error('Storage blocked');
                store.set(key, value);
            },
        },
    });
    await Promise.resolve();
    assert.deepEqual(link.dataset, {});
    assert.equal(path, '/oauth/vscode/callback');
    return { launches, manualClick: () => { link.click(); return launches; } };
}

test('one launch per attempt across tabs, reload and browser restore; distinct attempts still work', async () => {
    const storage = new Map();
    const first = await page({ store: storage });
    assert.equal(first.launches, 1);
    assert.equal((await page({ store: storage })).launches, 0);
    assert.equal((await page({ store: new Map(storage) })).launches, 0);
    assert.equal((await page({ store: storage, eligible: 'b'.repeat(64) })).launches, 1);
    assert.deepEqual([...storage.values()].map(JSON.parse), [[[marker, 120000], ['b'.repeat(64), 120000]]]);
});

test('stale URLs, cancelled navigation, unavailable locks or storage leave links manual', async () => {
    for (const options of [
        { eligible: null }, { now: 120000 }, { available: false }, { lockBlocked: true },
        { storageBlocked: true }, { leaving: true }, { visibility: 'hidden' },
    ]) {
        const result = await page(options);
        assert.equal(result.launches, 0);
        assert.equal(result.manualClick(), 1);
    }
});

test('a blocked protocol attempt is consumed and markers are bounded', async () => {
    const storage = new Map();
    assert.equal((await page({ store: storage, protocolBlocked: true })).launches, 1);
    assert.equal((await page({ store: storage })).launches, 0);
    const full = Array.from({ length: 64 }, (_, i) => [String(i), 120000]);
    storage.set('snippo.vscode.launches', JSON.stringify(full));
    assert.equal((await page({ store: storage })).launches, 0);
});
