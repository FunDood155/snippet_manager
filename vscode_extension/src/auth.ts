import { createHash, randomBytes, timingSafeEqual } from 'node:crypto';

export const extensionId = 'dineshkaarthik.snippo-code-snippets';
export const authPath = '/auth';

type SecretStorage = {
    get(key: string): Thenable<string | undefined>;
    store(key: string, value: string): Thenable<void>;
    delete(key: string): Thenable<void>;
};

type Configuration = { provider: string; clientId: string; redirectUri: string };
export type Snippet = {
    sno: number; name: string; cat: string; code: string;
    language?: string | null; template?: boolean; used_at?: string | null;
};
type Tokens = { access: string; refresh: string; expires: number };
type SavedSession = { origin: string; config: Configuration; tokens: Tokens };
type PendingLibrary = {
    path: string;
    session: SavedSession;
    controller: AbortController;
    result: Promise<{ items: Snippet[]; session: SavedSession }>;
    readers: number;
};
type Callback = { scheme: string; authority: string; path: string; query: string; fragment: string };

export const credentialKey = 'snippet-manager.session';

export class SignInRequired extends Error {}
export class AuthUnavailable extends Error {}
export class SaveSessionChanged extends Error {}
export class SaveUnconfirmed extends Error {}

const libraryBytes = 3 * 1024 * 1024;
const libraryRows = 1000;

export async function boundedJson(response: Response, maxBytes: number): Promise<unknown> {
    const length = Number(response.headers.get('Content-Length'));
    if (length > maxBytes) {
        void response.body?.cancel().catch(() => {});
        throw new AuthUnavailable('The server response is too large.');
    }
    const reader = response.body?.getReader();
    if (!reader) throw new AuthUnavailable('The server returned an invalid response.');
    const decoder = new TextDecoder('utf-8', {fatal: true});
    let size = 0;
    let text = '';
    try {
        for (;;) {
            const {done, value} = await reader.read();
            if (done) break;
            size += value.byteLength;
            if (size > maxBytes) {
                void reader.cancel().catch(() => {});
                throw new AuthUnavailable('The server response is too large.');
            }
            text += decoder.decode(value, {stream: true});
        }
        return JSON.parse(text + decoder.decode()) as unknown;
    } catch (error) {
        if (error instanceof AuthUnavailable) throw error;
        void reader.cancel().catch(() => {});
        throw new AuthUnavailable('The server returned an invalid or incomplete response.');
    } finally {
        reader.releaseLock();
    }
}

function object(value: unknown): value is Record<string, unknown> {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function snippetList(value: unknown): Snippet[] {
    const ids = new Set<number>();
    if (!Array.isArray(value) || value.length > libraryRows) {
        throw new AuthUnavailable('The server returned an invalid library. Narrow your search or use the web library.');
    }
    for (const row of value) {
        if (!object(row) || typeof row.sno !== 'number' || !Number.isInteger(row.sno) ||
                row.sno < 0 || row.sno > 2147483647 || ids.has(row.sno) ||
                typeof row.name !== 'string' || typeof row.cat !== 'string' || typeof row.code !== 'string' ||
                (row.language != null && (typeof row.language !== 'string' || !/^[a-z][a-z0-9_-]{0,31}$/.test(row.language))) ||
                (row.template !== undefined && typeof row.template !== 'boolean') ||
                (row.used_at != null && (typeof row.used_at !== 'string' || row.used_at.length > 40 ||
                    !Number.isFinite(Date.parse(row.used_at))))) {
            throw new AuthUnavailable('The server returned invalid snippet data.');
        }
        ids.add(row.sno);
    }
    return value as Snippet[];
}

export function trustedOrigin(input: string): string {
    const url = new URL(input);
    const loopback = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
    if (url.username || url.password || url.pathname !== '/' || url.search || url.hash ||
            (url.protocol !== 'https:' && !(url.protocol === 'http:' && loopback))) {
        throw new Error('Use an HTTPS server origin or an HTTP localhost address.');
    }
    return url.origin;
}

export class SignInRequest {
    readonly state = randomBytes(32).toString('base64url');
    readonly verifier = randomBytes(32).toString('base64url');
    readonly expires = Date.now() + 5 * 60_000;
    private used = false;

    constructor(readonly config: Configuration, readonly origin: string) {}

    get url(): URL {
        const url = new URL('/auth/v1/oauth/authorize', this.config.provider);
        url.search = new URLSearchParams({
            client_id: this.config.clientId,
            redirect_uri: this.config.redirectUri,
            response_type: 'code',
            scope: 'openid email',
            state: this.state,
            code_challenge: createHash('sha256').update(this.verifier).digest('base64url'),
            code_challenge_method: 'S256',
        }).toString();
        return url;
    }

    accept(uri: Callback, scheme: string): string | null | undefined {
        if (this.used || Date.now() >= this.expires || uri.scheme !== scheme ||
                uri.authority !== extensionId || uri.path !== authPath || uri.fragment) {
            return;
        }
        const query = new URLSearchParams(uri.query);
        const state = Buffer.from(query.get('state') ?? '');
        if (query.getAll('state').length !== 1 || state.length !== this.state.length ||
                !timingSafeEqual(state, Buffer.from(this.state))) {
            return;
        }
        const codes = query.getAll('code');
        const errors = query.getAll('error');
        if (codes.length + errors.length !== 1 || (codes.length && !/^[\w.-]{1,512}$/.test(codes[0]))) {
            return;
        }
        this.used = true;
        return codes[0] ?? null;
    }
}

export class AuthClient {
    private queue: Promise<unknown> = Promise.resolve();
    private pendingLibrary?: PendingLibrary;
    private saveDrafts = new Set<{ session: SavedSession }>();

    constructor(private storage: SecretStorage, private server: () => string, private http = fetch) {}

    get origin(): string {
        return trustedOrigin(this.server());
    }

    async configuration(signal?: AbortSignal): Promise<SignInRequest> {
        const origin = this.origin;
        const response = await this.send(origin + '/oauth/vscode/config', { signal });
        if (!response.ok) {
            throw new AuthUnavailable('VS Code sign-in is unavailable on this server.');
        }
        const data = await boundedJson(response, 16384);
        if (!object(data) || typeof data.provider !== 'string' || typeof data.clientId !== 'string' ||
                !data.clientId || data.clientId.length > 128 ||
                data.redirectUri !== origin + '/oauth/vscode/callback') {
            throw new AuthUnavailable('The server returned an invalid authorization configuration.');
        }
        const provider = trustedOrigin(data.provider);
        if (new URL(origin).protocol === 'https:' && new URL(provider).protocol !== 'https:') {
            throw new AuthUnavailable('The configured identity provider must use HTTPS.');
        }
        return new SignInRequest({ provider, clientId: data.clientId, redirectUri: data.redirectUri }, origin);
    }

    private serialize<T>(action: () => Promise<T>): Promise<T> {
        const result = this.queue.then(action);
        this.queue = result.catch(() => undefined);
        return result;
    }

    async complete(attempt: SignInRequest, code: string, signal: AbortSignal): Promise<void> {
        return this.serialize(async () => {
            if (signal.aborted || this.origin !== attempt.origin || Date.now() >= attempt.expires) {
                throw new SignInRequired();
            }
            const tokens = await this.exchange(attempt.config, {
                grant_type: 'authorization_code',
                code,
                code_verifier: attempt.verifier,
                redirect_uri: attempt.config.redirectUri,
            }, signal);
            if (signal.aborted || this.origin !== attempt.origin) {
                await this.revoke(attempt.origin, tokens.access);
                throw new SignInRequired();
            }
            const saved = { origin: attempt.origin, config: attempt.config, tokens };
            await this.save(saved);
            if (signal.aborted || this.origin !== attempt.origin) {
                await this.removeIfCurrent(saved);
                await this.revoke(attempt.origin, tokens.access);
                throw new SignInRequired();
            }
        });
    }

    async hasSession(): Promise<boolean> {
        return Boolean(await this.load());
    }

    request(path: string): Promise<Response> {
        return this.serialize(async () => {
            const saved = await this.load();
            if (!saved) {
                throw new SignInRequired();
            }
            return (await this.authorizeRequest(path, saved)).response;
        });
    }

    async readLibrary(query: string, signal: AbortSignal): Promise<{ items: Snippet[]; isCurrent: () => Promise<boolean>; recordUse: (sno: number) => Promise<void> }> {
        const saved = await this.load();
        signal.throwIfAborted();
        if (!saved) {
            throw new SignInRequired();
        }
        const path = '/api/snippets' + query;
        let pending = this.pendingLibrary;
        if (!pending || pending.path !== path || pending.controller.signal.aborted ||
                !this.sameSession(pending.session, saved)) {
            this.cancelLibraryReads();
            const controller = new AbortController();
            const result = this.serialize(async () => {
                controller.signal.throwIfAborted();
                if (!this.sameSession(saved, await this.load())) {
                    throw new AuthUnavailable('The Snippo session changed.');
                }
                const {response, session} = await this.authorizeRequest(path, saved, controller.signal);
                const items = snippetList(await boundedJson(response, libraryBytes));
                if (!this.sameSession(session, await this.load())) {
                    throw new AuthUnavailable('The Snippo session changed.');
                }
                return {items, session};
            }).finally(() => {
                if (this.pendingLibrary?.controller === controller) this.pendingLibrary = undefined;
            });
            pending = {path, session: saved, controller, result, readers: 0};
            this.pendingLibrary = pending;
        }
        pending.readers++;
        const entry = pending;
        try {
            const {items, session} = await new Promise<Awaited<PendingLibrary['result']>>((resolve, reject) => {
                const cancel = () => reject(signal.reason);
                signal.addEventListener('abort', cancel, { once: true });
                entry.result.then(resolve, reject).finally(() => signal.removeEventListener('abort', cancel));
            });
            signal.throwIfAborted();
            return {
                items,
                isCurrent: async () => this.sameSession(session, await this.load()),
                recordUse: async sno => {
                    if (Number.isInteger(sno) && this.sameSession(session, await this.load())) {
                        await this.authorized(session.origin, '/api/snippets/' + sno + '/recent',
                            session.tokens.access, 'POST', AbortSignal.timeout(5000));
                    }
                },
            };
        } finally {
            entry.readers--;
            if (signal.aborted && !entry.readers) {
                // Give an equivalent picker replacing this one a chance to attach.
                setTimeout(() => {
                    if (!entry.readers && this.pendingLibrary === entry) entry.controller.abort();
                }, 50);
            }
        }
    }

    async prepareSnippetSave(isCurrent: () => boolean) {
        const draft = await this.serialize(async () => {
            const session = await this.load();
            if (!isCurrent()) throw new SaveSessionChanged();
            if (!session) throw new SignInRequired();
            const draft = { session };
            this.saveDrafts.add(draft);
            return draft;
        });
        let submitted = false;
        const dispose = () => { this.saveDrafts.delete(draft); };
        const save = (fields: {name: string; cat: string; code: string; language: string}) => this.serialize(async () => {
            if (submitted || !this.saveDrafts.has(draft)) throw new SaveSessionChanged();
            submitted = true;
            const current = await this.load();
            if (!current || !isCurrent() || !this.sameSession(draft.session, current)) {
                throw new SaveSessionChanged();
            }
            const session = current.tokens.expires <= Date.now() + 30_000 ? await this.refresh(current) : current;
            if (!this.sameSession(session, await this.load()) || !isCurrent()) throw new SaveSessionChanged();

            // This request can commit even when the response is lost. Never replay it.
            let response: Response;
            try {
                response = await this.send(session.origin + '/api/snippets?v=2', {
                    method: 'POST',
                    headers: {Authorization: `Bearer ${session.tokens.access}`, 'Content-Type': 'application/json'},
                    body: JSON.stringify(fields),
                });
            } catch {
                throw new SaveUnconfirmed();
            }
            if (response.status === 401) {
                await this.removeIfCurrent(session);
                throw new SignInRequired();
            }
            return response;
        });
        return { save, dispose };
    }

    cancelLibraryReads() {
        this.pendingLibrary?.controller.abort();
        this.pendingLibrary = undefined;
    }

    private sameSession(expected: SavedSession, current?: SavedSession): boolean {
        return Boolean(current && expected.origin === current.origin &&
            expected.config.clientId === current.config.clientId && expected.config.provider === current.config.provider &&
            expected.config.redirectUri === current.config.redirectUri && expected.tokens.expires === current.tokens.expires &&
            expected.tokens.access === current.tokens.access && expected.tokens.refresh === current.tokens.refresh);
    }

    private async authorizeRequest(path: string, saved: SavedSession, signal?: AbortSignal) {
        let session = saved.tokens.expires <= Date.now() + 30_000 ? await this.refresh(saved) : saved;
        signal?.throwIfAborted();
        let response = await this.authorized(session.origin, path, session.tokens.access, 'GET', signal);
        signal?.throwIfAborted();
        if (response.status === 401 && session === saved) {
            session = await this.refresh(saved);
            signal?.throwIfAborted();
            response = await this.authorized(session.origin, path, session.tokens.access, 'GET', signal);
            signal?.throwIfAborted();
        }
        if (response.status === 401) {
            await this.removeIfCurrent(session);
            throw new SignInRequired();
        }
        if (response.status === 413 && path.startsWith('/api/snippets?')) {
            throw new AuthUnavailable('The library result is too large. Narrow your search or use the web library.');
        }
        if (!response.ok) {
            throw new AuthUnavailable('The snippet server is currently unavailable.');
        }
        return {response, session};
    }

    signOut(): Promise<boolean> {
        return this.serialize(async () => {
            const saved = await this.load(true);
            let target = saved;
            let revoked = true;
            try {
                if (saved) {
                    target = saved.tokens.expires <= Date.now() + 30_000 ? await this.refresh(saved) : saved;
                    const response = await this.revoke(target.origin, target.tokens.access);
                    if (response.status === 401 && target === saved) {
                        target = await this.refresh(saved);
                        revoked = (await this.revoke(target.origin, target.tokens.access)).ok;
                    } else {
                        revoked = response.ok;
                    }
                }
            } catch (error) {
                revoked = error instanceof SignInRequired;
            } finally {
                if (target) await this.removeIfCurrent(target);
            }
            return revoked;
        });
    }

    private async removeIfCurrent(expected: SavedSession): Promise<void> {
        // SecretStorage does not offer a cross-host compare-and-delete primitive.
        if (this.sameSession(expected, await this.load(true))) {
            await this.storage.delete(credentialKey);
        }
    }

    private async load(allowOtherOrigin = false): Promise<SavedSession | undefined> {
        const text = await this.storage.get(credentialKey);
        if (!text) {
            return;
        }
        try {
            const saved = JSON.parse(text) as SavedSession;
            if (trustedOrigin(saved.origin) === saved.origin && (allowOtherOrigin || saved.origin === this.origin) &&
                    typeof saved.config?.clientId === 'string' && typeof saved.config.provider === 'string' &&
                    typeof saved.config.redirectUri === 'string' && typeof saved.tokens?.access === 'string' &&
                    typeof saved.tokens.refresh === 'string' && Number.isFinite(saved.tokens.expires)) {
                return saved;
            }
        } catch {
            // A damaged entry cannot be used as credentials.
        }
    }

    private async save(session: SavedSession): Promise<void> {
        await this.storage.store(credentialKey, JSON.stringify(session));
    }

    private async refresh(saved: SavedSession): Promise<SavedSession> {
        try {
            const tokens = await this.exchange(saved.config, {
                grant_type: 'refresh_token',
                refresh_token: saved.tokens.refresh,
            });
            const renewed = { ...saved, tokens };
            if (!this.sameSession(saved, await this.load(true))) {
                throw new AuthUnavailable('The Snippo session changed.');
            }
            await this.save(renewed);
            // Follow only rotations performed by this client for the exact draft credentials.
            for (const draft of this.saveDrafts) {
                if (this.sameSession(draft.session, saved)) draft.session = renewed;
            }
            return renewed;
        } catch (error) {
            if (error instanceof SignInRequired) await this.removeIfCurrent(saved);
            throw error;
        }
    }

    private async exchange(config: Configuration, fields: Record<string, string>, signal?: AbortSignal): Promise<Tokens> {
        const response = await this.send(config.provider + '/auth/v1/oauth/token', {
            method: 'POST',
            body: new URLSearchParams({ ...fields, client_id: config.clientId }),
            signal,
        });
        if (response.status === 400 || response.status === 401 || response.status === 403) {
            throw new SignInRequired();
        }
        if (!response.ok) {
            throw new AuthUnavailable('The identity provider is currently unavailable.');
        }
        const data = await boundedJson(response, 32768);
        if (!object(data) || typeof data.access_token !== 'string' || !data.access_token ||
                data.access_token.length > 8192 || typeof data.refresh_token !== 'string' ||
                !data.refresh_token || data.refresh_token.length > 8192 ||
                typeof data.expires_in !== 'number' || !Number.isFinite(data.expires_in) || data.expires_in <= 0) {
            throw new AuthUnavailable('The identity provider returned an invalid session.');
        }
        return { access: data.access_token, refresh: data.refresh_token, expires: Date.now() + data.expires_in * 1000 };
    }

    private revoke(origin: string, access: string): Promise<Response> {
        return this.authorized(origin, '/api/logout', access, 'POST');
    }

    private authorized(origin: string, path: string, token: string, method = 'GET', signal?: AbortSignal): Promise<Response> {
        return this.send(origin + path, { method, signal, headers: { Authorization: `Bearer ${token}` } });
    }

    private async send(url: string, init?: RequestInit): Promise<Response> {
        const timeout = AbortSignal.timeout(12_000);
        try {
            return await this.http(url, {
                ...init,
                redirect: 'error',
                signal: init?.signal ? AbortSignal.any([init.signal, timeout]) : timeout,
            });
        } catch {
            throw new AuthUnavailable('Could not connect securely to the snippet server or identity provider.');
        }
    }
}
