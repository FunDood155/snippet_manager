import { createHash, randomBytes, timingSafeEqual } from 'node:crypto';

export const extensionId = 'dineshkaarthik.snippo-code-snippets';
export const authPath = '/auth';

type SecretStorage = {
    get(key: string): Thenable<string | undefined>;
    store(key: string, value: string): Thenable<void>;
    delete(key: string): Thenable<void>;
};

type Configuration = { provider: string; clientId: string; redirectUri: string };
type Tokens = { access: string; refresh: string; expires: number };
type SavedSession = { origin: string; config: Configuration; tokens: Tokens };
type PendingLibrary = {
    path: string;
    session: SavedSession;
    controller: AbortController;
    result: Promise<{ items: unknown; session: SavedSession }>;
    readers: number;
};
type Callback = { scheme: string; authority: string; path: string; query: string; fragment: string };

export const credentialKey = 'snippet-manager.session';

export class SignInRequired extends Error {}
export class AuthUnavailable extends Error {}

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
        const data = await response.json() as Configuration;
        if (!data.clientId || typeof data.clientId !== 'string' ||
                data.redirectUri !== origin + '/oauth/vscode/callback') {
            throw new AuthUnavailable('The server returned an invalid authorization configuration.');
        }
        const provider = trustedOrigin(data.provider);
        if (new URL(origin).protocol === 'https:' && new URL(provider).protocol !== 'https:') {
            throw new AuthUnavailable('The configured identity provider must use HTTPS.');
        }
        return new SignInRequest({ ...data, provider }, origin);
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
            await this.save({ origin: attempt.origin, config: attempt.config, tokens });
            if (signal.aborted || this.origin !== attempt.origin) {
                await this.storage.delete(credentialKey);
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

    async readLibrary<T>(query: string, signal: AbortSignal): Promise<{ items: T; isCurrent: () => Promise<boolean> }> {
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
                const items: unknown = await response.json();
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
            return {items: items as T, isCurrent: async () => this.sameSession(session, await this.load())};
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
            if (this.sameSession(session, await this.load())) await this.storage.delete(credentialKey);
            throw new SignInRequired();
        }
        if (!response.ok) {
            throw new AuthUnavailable('The snippet server is currently unavailable.');
        }
        return {response, session};
    }

    signOut(): Promise<boolean> {
        return this.serialize(async () => {
            const saved = await this.load(true);
            let revoked = true;
            try {
                if (saved) {
                    const session = saved.tokens.expires <= Date.now() + 30_000 ? await this.refresh(saved) : saved;
                    const response = await this.revoke(session.origin, session.tokens.access);
                    if (response.status === 401 && session === saved) {
                        const renewed = await this.refresh(saved);
                        revoked = (await this.revoke(renewed.origin, renewed.tokens.access)).ok;
                    } else {
                        revoked = response.ok;
                    }
                }
            } catch (error) {
                revoked = error instanceof SignInRequired;
            } finally {
                await this.storage.delete(credentialKey);
            }
            return revoked;
        });
    }

    private async load(allowOtherOrigin = false): Promise<SavedSession | undefined> {
        const text = await this.storage.get(credentialKey);
        if (!text) {
            return;
        }
        try {
            const saved = JSON.parse(text) as SavedSession;
            if (trustedOrigin(saved.origin) === saved.origin && (allowOtherOrigin || saved.origin === this.origin) &&
                    saved.tokens?.access && saved.tokens.refresh) {
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
            return renewed;
        } catch (error) {
            if (error instanceof SignInRequired && this.sameSession(saved, await this.load(true))) {
                await this.storage.delete(credentialKey);
            }
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
        const data = await response.json() as {
            access_token?: string; refresh_token?: string; expires_in?: number;
        };
        if (!data.access_token || !data.refresh_token || !data.expires_in || data.expires_in <= 0) {
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
