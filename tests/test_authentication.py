import base64
import json
import os
import re
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from html import unescape
from pathlib import Path
from unittest.mock import patch
from threading import Barrier, Event
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg2
from psycopg2 import sql

import auth
import main
import store


A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"
HELD = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
CONFIRM_LINK = "/auth/confirm-email"
RESET_LINK = "/auth/reset-password"
NEW_PASSWORD = "/auth/new-password"
CLIENT = "33333333-3333-4333-8333-333333333333"
SESSION_A = "44444444-4444-4444-8444-444444444444"
SESSION_B = "55555555-5555-4555-8555-555555555555"
ATTEMPT = "Aa0123456789_-Bb0123456789_-CcDd"
PASSWORD = "test-password-A"
FIXTURE_ISSUED_AT = int(time.time()) - 60
ORIGIN = "https://snippet.test"
ROOT = Path(__file__).resolve().parents[1]
MIGRATION = next((ROOT / "supabase/migrations").glob("*_snippet_ownership.sql")).read_text()
STARTER_MIGRATION = next((ROOT / "supabase/migrations").glob("*_default_starter_snippets.sql")).read_text()
PUBLIC_AUTH = next((ROOT / "supabase/migrations").glob("*_public_authentication.sql")).read_text()
SHARED_DEFAULTS = next((ROOT / "supabase/migrations").glob("*_shared_default_snippets.sql")).read_text()
FAVORITES_EDIT = next((ROOT / "supabase/migrations").glob("*_snippet_favorites_and_editing.sql")).read_text()
PRODUCTIVITY = next((ROOT / "supabase/migrations").glob("*_developer_productivity.sql")).read_text()
HIDDEN_DEFAULTS = next((ROOT / "supabase/migrations").glob("*_hidden_default_snippets.sql")).read_text()
RETIRE_STARTERS = next((ROOT / "supabase/migrations").glob("*_retire_starter_copies.sql")).read_text()
PUBLIC_UNDO = (ROOT / "supabase/rollback_public_authentication.sql").read_text()
STARTER_UNDO = (ROOT / "supabase/rollback_starter_snippets.sql").read_text()
STARTERS = {
    "Hello World": "Basics",
    "Loop Through a List": "Loops",
    "Function Template": "Functions",
    "Exception Handling": "Error Handling",
}
UNDO = (ROOT / "supabase/rollback_wp01.sql").read_text()
LEGACY = (17, "Legacy name", "legacy category", "legacy code")


def fake_jwt(owner, session_id, client_id=CLIENT, signature="fixture", issued_at=None):
    payload = json.dumps({"sub": owner, "client_id": client_id, "session_id": session_id,
                          "iat": FIXTURE_ISSUED_AT if issued_at is None else issued_at}).encode()
    return "header." + base64.urlsafe_b64encode(payload).decode().rstrip("=") + "." + signature


def bearer(token):
    return {"Authorization": "Bearer " + token}


def csrf(client, path):
    html = client.get(path, follow_redirects=True).get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([^"]+)"', html)[1]


class MockProvider:
    def __init__(self):
        self.calls = []
        self.oauth_tokens = {fake_jwt(A, SESSION_A): A, fake_jwt(B, SESSION_B): B}
        self.confirmed = {"a@sample.test": A, "b@sample.test": B}
        self.token_user = {}
        self.passwords = {}
        self.pending = {}
        self.links = {}
        self.autoconfirm = False
        self.token_offset = 0
        self.create_account = None
        self.confirm_account = None
        self.invalid_redirect = False

    def __call__(self, method, path, *, token=None, body=None):
        self.calls.append((method, path, body))
        if path == "/settings":
            return {"mailer_autoconfirm": self.autoconfirm}
        if path == "/verify":
            pending = self.links.get(body["token_hash"])
            if not pending or pending[0] != body["type"]:
                raise auth.AuthError(403, "otp_expired")
            kind, email = self.links.pop(body["token_hash"])
            if kind == "signup":
                user = self.pending.pop(email)
                self.confirm_account(user)
                self.confirmed[email] = user
            return self.tokens(self.confirmed[email])
        if path.partition("?")[0] in ("/recover", "/resend"):
            address = body["email"]
            if address not in self.confirmed and address not in self.pending:
                raise auth.AuthError(404)
            return {}
        if path == "/token?grant_type=password":
            user = self.confirmed.get(body["email"])
            if body["email"] in self.pending:
                raise auth.AuthError(400, "email_not_confirmed")
            if not user or body["password"] != self.passwords.get(body["email"], PASSWORD):
                raise auth.AuthError(400)
            return self.tokens(user)
        if path == "/token?grant_type=refresh_token":
            return self.tokens(self.token_user[body["refresh_token"]])
        if path == "/oauth/userinfo":
            owner = self.oauth_tokens.get(token)
            if not owner:
                raise auth.AuthError(403)
            return {"sub": owner, "email_verified": True}
        if path == "/user" and method == "GET":
            if token not in self.token_user:
                raise auth.AuthError(403)
            return {"id": self.token_user[token], "email_confirmed_at": "fixture"}
        if path == "/user" and method == "PUT":
            if token not in self.token_user:
                raise auth.AuthError(403)
            owner = self.token_user[token]
            email = next(email for email, user in self.confirmed.items() if user == owner)
            self.passwords[email] = body["password"]
            return {"id": owner}
        if path.partition("?")[0] == "/signup":
            email, password = body["email"], body["password"]
            if len(password) < 6:
                raise auth.AuthError(422, "weak_password")
            if email in self.confirmed or email in self.pending:
                raise auth.AuthError(422, "user_already_exists")
            self.pending[email] = self.create_account()
            self.passwords[email] = password
            return {}
        if path == "/oauth/authorizations/" + ATTEMPT:
            return {"client": {"id": CLIENT}, "redirect_uri": ORIGIN + auth.CALLBACK_PATH}
        if path == "/oauth/authorizations/" + ATTEMPT + "/consent":
            origin = "https://untrusted.invalid" if self.invalid_redirect else ORIGIN
            result = "code=foo" if body["action"] == "approve" else "error=access_denied"
            return {"redirect_url": origin + auth.CALLBACK_PATH + "?state=" + "a" * 43 + "&" + result}
        if method == "DELETE" and path.startswith("/user/oauth/grants?"):
            owner = self.token_user[token]
            self.oauth_tokens = {key: user for key, user in self.oauth_tokens.items() if user != owner}
        if path.startswith("/logout") and token:
            self.token_user.pop(token, None)
        return {}

    def tokens(self, owner):
        n = len(self.calls)
        access = fake_jwt(owner, str(uuid4()), client_id=None, signature=f"web-{n}",
                          issued_at=int(time.time()) + self.token_offset)
        refresh = f"refresh-{n}"
        self.token_user[access] = self.token_user[refresh] = owner
        return {"user": {"id": owner, "email_confirmed_at": "fixture"},
                "access_token": access, "refresh_token": refresh, "expires_in": 3600}


class AppTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dsn = os.environ.get("SNIPPET_TEST_ADMIN_URL")
        if not dsn:
            raise unittest.SkipTest("Set SNIPPET_TEST_ADMIN_URL to a fresh disposable PostgreSQL cluster.")
        url = urlsplit(dsn)
        if url.scheme not in ("postgres", "postgresql") or url.hostname not in ("127.0.0.1", "::1") or url.path != "/postgres":
            raise ValueError("The test database must be a fresh loopback cluster's postgres database.")
        cls.base = dsn
        cls.admin = dsn.rsplit("/", 1)[0] + "/wp01_fixture"
        cls.runtime = f"postgresql://snippet_app:fixture-only@{url.hostname}:{url.port}/wp01_fixture"
        with closing(psycopg2.connect(dsn)) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("CREATE DATABASE wp01_fixture")
        with closing(psycopg2.connect(cls.admin)) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE ROLE anon;
                    CREATE ROLE authenticated;
                    CREATE ROLE supabase_auth_admin;
                    CREATE ROLE wp01_migrator CREATEROLE BYPASSRLS;
                    GRANT USAGE ON SCHEMA public TO wp01_migrator WITH GRANT OPTION;
                    CREATE ROLE service_role BYPASSRLS;
                    CREATE SCHEMA auth;
                    CREATE TABLE auth.users (id uuid PRIMARY KEY, email_confirmed_at timestamptz);
                    GRANT USAGE ON SCHEMA auth TO supabase_auth_admin, wp01_migrator;
                    GRANT SELECT, INSERT, UPDATE, DELETE ON auth.users TO supabase_auth_admin;
                    GRANT REFERENCES, TRIGGER ON auth.users TO wp01_migrator;
                    CREATE TABLE public.snippets (
                        sno integer GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                        name text NOT NULL, cat text NOT NULL, code text NOT NULL
                    );
                    GRANT ALL ON public.snippets, public.snippets_sno_seq TO anon, authenticated, service_role;
                """)
                cur.execute("INSERT INTO auth.users (id, email_confirmed_at) VALUES (%s, now()), (%s, NULL)", (A, B))
                cur.execute("INSERT INTO snippets VALUES (%s, %s, %s, %s)", LEGACY)
                cur.execute("SELECT setval('public.snippets_sno_seq', 17)")
                cur.execute(MIGRATION)
                cur.execute("ALTER TABLE public.snippets OWNER TO wp01_migrator")
                cur.execute("ALTER SCHEMA snippet_private OWNER TO wp01_migrator")
                cur.execute("SET ROLE wp01_migrator")
                cur.execute(STARTER_MIGRATION)
                cur.execute("RESET ROLE")
                cur.execute("INSERT INTO auth.users (id) VALUES (%s)", (HELD,))
                cur.execute(PUBLIC_AUTH)
                cur.execute(SHARED_DEFAULTS)
                cur.execute(HIDDEN_DEFAULTS)
                cur.execute(FAVORITES_EDIT)
                cur.execute(PRODUCTIVITY)
                cur.execute("DELETE FROM snippet_private.legacy_email_holds WHERE user_id IN (%s, %s)", (A, B))
                cur.execute("ALTER ROLE snippet_app LOGIN PASSWORD 'fixture-only'")

    def setUp(self):
        with closing(psycopg2.connect(self.admin)) as conn:
            with conn, conn.cursor() as cur:
                cur.execute("DELETE FROM public.snippets WHERE owner_id IS NOT NULL")
                cur.execute("DELETE FROM snippet_private.hidden_default_snippets")
                cur.execute("DELETE FROM snippet_private.favorite_default_snippets")
                cur.execute("DELETE FROM snippet_private.recent_default_snippets")
                cur.execute("""TRUNCATE snippet_private.web_sessions, snippet_private.auth_limits,
                    snippet_private.revoked_vscode_sessions, snippet_private.session_cutoffs, snippet_private.email_flows""")
        patches = (patch.dict(os.environ, {"SNIPPET_DATABASE_URL": self.runtime}),
                   patch("auth.provider", MockProvider()))
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        self.app = main.create_app({
            "TESTING": True, "SECRET_KEY": "fixture-secret-key-32-characters-X",
            "SUPABASE_URL": "https://auth.example.test", "SUPABASE_PUBLISHABLE_KEY": "fixture-publishable-key",
            "SNIPPET_SITE_URL": ORIGIN, "SNIPPET_VSCODE_CLIENT_ID": CLIENT,
            "SESSION_COOKIE_NAME": "__Host-snippet_session", "SESSION_COOKIE_SECURE": True,
        })
        auth.provider.create_account = self.create_account
        auth.provider.confirm_account = self.confirm_account
        self.browser = self.app.test_client()
        self.api_a = bearer(fake_jwt(A, SESSION_A))
        self.api_b = bearer(fake_jwt(B, SESSION_B))

    def form(self, path, **data):
        return self.browser.post(path, data={"csrf_token": csrf(self.browser, path), **data})

    def login(self, email="a@sample.test"):
        return self.form("/login", email=email, password=PASSWORD)

    def api_create(self, headers, **overrides):
        return self.browser.post("/api/snippets", headers=headers, json={
            "name": "shared name", "cat": "sample", "code": "test code", **overrides,
        })

    def shared_browser(self):
        other = self.app.test_client()
        cookie = self.browser.get_cookie("__Host-snippet_session")
        other.set_cookie(cookie.key, cookie.value)
        return other

    def test_ordinary_web_verifications_overlap_for_one_cookie(self):
        self.login()
        waiting = Barrier(2)
        original = auth.provider

        def concurrent(method, path, **kwargs):
            if path == "/user":
                connection = store.g.snippet_connection
                self.assertEqual(connection.get_transaction_status(), psycopg2.extensions.TRANSACTION_STATUS_IDLE)
                waiting.wait(timeout=3)
            return original(method, path, **kwargs)

        with patch("auth.provider", side_effect=concurrent), ThreadPoolExecutor(max_workers=2) as pool:
            clients = [self.shared_browser() for _ in range(2)]
            self.assertEqual(list(pool.map(lambda client: client.get("/").status_code, clients)), [200, 200])

    def test_logout_and_account_hold_are_rechecked_after_verification(self):
        def request_during(change):
            started, release = Event(), Event()
            original = auth.provider

            def blocked(method, path, **kwargs):
                verified = original(method, path, **kwargs)
                if path == "/user" and not started.is_set():
                    started.set()
                    self.assertTrue(release.wait(5))
                return verified

            with patch("auth.provider", side_effect=blocked), ThreadPoolExecutor(max_workers=1) as pool:
                other = self.shared_browser()
                running = pool.submit(other.get, "/")
                try:
                    self.assertTrue(started.wait(5))
                    change()
                finally:
                    release.set()
                return running.result(timeout=5)

        self.login()
        with self.browser.session_transaction() as browser_session:
            csrf_value = browser_session.get("csrf")
        if not csrf_value:
            csrf_value = csrf(self.browser, "/")
        response = request_during(lambda: self.assertEqual(self.browser.post(
            "/logout", data={"csrf_token": csrf_value}).status_code, 303))
        self.assertEqual(response.location, "/login")

        self.login()
        try:
            def hold_account():
                with closing(psycopg2.connect(self.admin)) as conn, conn, conn.cursor() as cur:
                    cur.execute("INSERT INTO snippet_private.legacy_email_holds (user_id) VALUES (%s)", (A,))
            self.assertEqual(request_during(hold_account).location, "/login")
        finally:
            with closing(psycopg2.connect(self.admin)) as conn, conn, conn.cursor() as cur:
                cur.execute("DELETE FROM snippet_private.legacy_email_holds WHERE user_id = %s", (A,))

    def test_concurrent_expiry_refreshes_once(self):
        self.login()
        with closing(psycopg2.connect(self.admin)) as conn, conn, conn.cursor() as cur:
            cur.execute("UPDATE snippet_private.web_sessions SET token_expires_at = 0")
        ready = Barrier(3)
        original = auth.provider
        refreshed = Event()
        release = Event()

        def delaying(method, path, **kwargs):
            if path == "/token?grant_type=refresh_token":
                refreshed.set()
                self.assertTrue(release.wait(5))
            return original(method, path, **kwargs)

        def load(client):
            ready.wait(timeout=5)
            return client.get("/").status_code

        with patch("auth.provider", side_effect=delaying), ThreadPoolExecutor(max_workers=2) as pool:
            results = [pool.submit(load, self.shared_browser()) for _ in range(2)]
            try:
                ready.wait(timeout=5)
                self.assertTrue(refreshed.wait(5))
            finally:
                release.set()
            self.assertEqual([result.result(timeout=5) for result in results], [200, 200])
        self.assertEqual(sum(path == "/token?grant_type=refresh_token" for _, path, _ in original.calls), 1)

    def test_cutoff_during_token_refresh_rejects_the_source_session(self):
        self.login()
        with closing(psycopg2.connect(self.admin)) as conn, conn, conn.cursor() as cur:
            cur.execute("UPDATE snippet_private.web_sessions SET token_expires_at = 0")
        original = auth.provider

        def rotate_after_cutoff(method, path, **kwargs):
            if path == "/token?grant_type=refresh_token":
                with closing(psycopg2.connect(self.admin)) as conn, conn, conn.cursor() as cur:
                    cur.execute("INSERT INTO snippet_private.session_cutoffs VALUES (%s, %s)", (A, int(time.time())))
                original.token_offset = 10
            return original(method, path, **kwargs)

        with patch("auth.provider", side_effect=rotate_after_cutoff):
            self.assertEqual(self.browser.get("/").location, "/login")
        with closing(psycopg2.connect(self.admin)) as conn, conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM snippet_private.web_sessions")
            self.assertEqual(cur.fetchone()[0], 0)

    def test_request_connection_reuse_rolls_back_and_does_not_share_owner(self):
        with self.app.test_request_context("/"):
            with store.cursor(A) as cur:
                conn = cur.connection
                cur.execute("SELECT current_setting('snippet.owner_id')")
                self.assertEqual(cur.fetchone()[0], A)
            with store.cursor() as cur:
                self.assertIs(cur.connection, conn)
                cur.execute("SELECT nullif(current_setting('snippet.owner_id', true), '')")
                self.assertIsNone(cur.fetchone()[0])
            with self.assertRaises(psycopg2.errors.DivisionByZero):
                with store.cursor(A) as cur:
                    cur.execute("SELECT 1 / 0")
            self.assertTrue(conn.closed)
            with store.cursor(B) as cur:
                other = cur.connection
                self.assertIsNot(other, conn)
                cur.execute("SELECT current_setting('snippet.owner_id')")
                self.assertEqual(cur.fetchone()[0], B)
        self.assertTrue(other.closed)

    def test_web_page_totals_and_fragment_write_keep_legacy_api_unpaginated(self):
        self.login()
        token = csrf(self.browser, "/")
        with store.cursor(A) as cur:
            cur.execute("""INSERT INTO public.snippets (owner_id, name, cat, code)
                           SELECT %s, 'Page ' || to_char(n, 'FM000'), 'Paging', 'needle'
                           FROM generate_series(1, 83) n""", (A,))
        query = "category=Paging&search=need_e&scope=personal&sort=name"
        pages = [self.browser.get(f"/?{query}&page={index}").get_data(as_text=True) for index in range(1, 4)]
        self.assertEqual([page.count('data-snippet-id=') for page in pages], [40, 40, 3])
        for page in pages:
            self.assertIn("83 snippets", page)
        keys = [re.findall(r'data-snippet-id="(\d+)"', page) for page in pages]
        self.assertEqual(len(set().union(*map(set, keys))), 83)
        self.assertIn("Page 041", pages[1])
        link = unescape(re.search(r'rel="next" href="([^"]+)"', pages[0])[1])
        with store.cursor(B) as cur:
            cur.execute("INSERT INTO public.snippets (owner_id, name, cat, code) VALUES (%s, %s, %s, %s)",
                        (B, "Other owner", "Other", "needle"))
        self.assertIn(b"Page 2 of 3", self.browser.get(link).data)
        with store.cursor(A) as cur:
            cur.execute("UPDATE public.snippets SET name = 'Page 000' WHERE name = 'Page 083'")
        self.assertIn(b"Page 1 of 3", self.browser.get(link).data)
        api = self.browser.get("/api/snippets?category=Paging", headers=self.api_a)
        self.assertEqual(len(api.json), 83)
        self.assertEqual(self.browser.get("/api/snippets?category=Paging", headers=self.api_b).json, [])
        headers = {"X-Snippo-Fragment": "library"}
        before = len(auth.provider.calls)
        response = self.browser.post(f"/favorites/{keys[0][0]}?{query}", headers=headers,
                                     data={"csrf_token": token, "action": "add"})
        self.assertEqual(len(auth.provider.calls) - before, 1)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertIn("X-Snippo-Fragment", response.headers["Vary"])
        self.assertIn(b'id="library-content"', response.data)
        self.assertNotIn(b"<!doctype html>", response.data)
        self.assertIn(b"Added to favorites.", response.data)
        self.assertEqual(self.browser.post(f"/favorites/{keys[0][0]}", headers=headers,
                                          data={"action": "remove"}).status_code, 400)

    def test_productivity_metadata_and_legacy_api_contract(self):
        code = '  \tprint({{value}}) # $HOME \r\n'
        path = "/api/snippets?v=2"
        payload = {"name": "Template", "cat": "Examples", "code": code, "language": "typescriptreact", "template": True}
        response = self.browser.post(path, headers=self.api_a, json=payload)
        self.assertEqual(response.status_code, 201)
        self.assertEqual((response.json["language"], response.json["template"], response.json["code"]),
                         ("typescript", True, code))
        self.assertEqual(self.browser.post(path, headers=self.api_a, json=payload).status_code, 409)
        self.assertEqual(self.browser.post(path, headers=self.api_a, json={**payload, "name": "bad", "code": "{{bad-name}}"}).status_code, 400)
        self.assertEqual(self.browser.post(path, headers=self.api_a, json={**payload, "name": "bad", "template": "false"}).status_code, 400)
        sno = response.json["sno"]
        self.assertEqual(set(self.browser.get(f"/api/snippets/{sno}", headers=self.api_a).json), {"sno", "name", "cat", "code"})
        self.assertEqual(self.browser.get(path + "&language=typescript", headers=self.api_b).json, [])
        self.assertEqual(len(self.browser.get(path + "&language=typescript", headers=self.api_a).json), 1)
        fallback = self.browser.post(path, headers=self.api_a, json={**payload, "name": "Rust", "language": "rust"})
        self.assertIsNone(fallback.json["language"])
        legacy = self.browser.post("/api/snippets", headers=self.api_a,
                                   json={**payload, "name": "Old POST", "code": "${1:literal}"})
        self.assertEqual(legacy.status_code, 201)
        self.assertNotIn("language", legacy.json)
        self.login()
        editor = self.browser.get(f"/duplicate/{sno}").text
        self.assertRegex(editor, r'<option value="typescript"\s+selected')
        self.assertIn('name="template" checked', editor)
        self.assertIn("1 snippet", self.browser.get("/?language=typescript").text)
        self.assertIsNone(main.highlight("print('legacy')", "Python", "plaintext"))
        self.assertIsNotNone(main.highlight("print('legacy')", "Examples"))

    def test_productivity_recents_are_bounded_scoped_and_filtered(self):
        self.login()
        token = csrf(self.browser, "/")
        with store.cursor(A) as cur:
            cur.execute("""INSERT INTO public.snippets (owner_id, name, cat, code)
                           SELECT %s, 'Recent ' || n, 'Fixture', 'body' FROM generate_series(1, 42) n
                           RETURNING sno""", (A,))
            ids = [row[0] for row in cur.fetchall()]
        for sno in ids[-22:]:
            self.assertEqual(self.browser.post(f"/api/snippets/{sno}/recent", headers=self.api_a).status_code, 204)
        self.assertEqual(self.browser.post(f"/api/snippets/{ids[0]}/recent", headers=self.api_b).status_code, 404)
        self.assertEqual(self.browser.post(f"/recent/{ids[0]}", data={}).status_code, 400)
        self.assertEqual(self.browser.post(f"/recent/{ids[0]}", data={"csrf_token": token}).status_code, 204)
        with store.cursor(A) as cur:
            cur.execute("SELECT count(*) FROM snippet_private.recent_personal_snippets")
            self.assertEqual(cur.fetchone()[0], 20)
        with store.cursor(B) as cur:
            cur.execute("SELECT count(*) FROM snippet_private.recent_personal_snippets")
            self.assertEqual(cur.fetchone()[0], 0)
            with self.assertRaises(psycopg2.errors.InsufficientPrivilege):
                cur.execute("INSERT INTO snippet_private.recent_personal_snippets VALUES (%s, %s, now())", (A, ids[0]))
            cur.connection.rollback()
        page = self.browser.get("/?scope=personal").text
        section = page.partition('id="recent-title"')[2].partition("</section>")[0]
        self.assertEqual(re.findall(r'data-snippet-id="(\d+)"', section),
                         [str(i) for i in [ids[0], *reversed(ids[-4:])]])
        self.assertEqual(page.count("data-snippet-id="), 40)
        second = self.browser.get("/?scope=personal&page=2").text
        self.assertEqual(second.count("data-snippet-id="), 2)
        self.assertNotIn('id="recent-title"', second)
        self.assertNotIn('id="recent-title"', self.browser.get("/?category=Other").text)
        shared = 2_000_000_000
        self.assertEqual(self.browser.post(f"/api/snippets/{shared}/recent", headers=self.api_a).status_code, 204)
        store.hide_default(A, shared)
        self.assertEqual(self.browser.post(f"/api/snippets/{shared}/recent", headers=self.api_a).status_code, 404)
        self.assertNotIn('id="recent-title"', self.browser.get("/?scope=defaults").text)
        store.restore_default(A, shared)
        self.assertIn('id="recent-title"', self.browser.get("/?scope=defaults").text)
        self.assertTrue(store.delete_snippet(A, ids[0]))
        with store.cursor(A) as cur:
            cur.execute("SELECT count(*) FROM snippet_private.recent_personal_snippets")
            self.assertEqual(cur.fetchone()[0], 19)

    def test_recent_preferences_require_private_role_and_cascade_on_account_deletion(self):
        user = self.create_account()
        self.assertTrue(store.record_recent(user, 2_000_000_000))
        with closing(psycopg2.connect(self.admin)) as conn, conn, conn.cursor() as cur:
            cur.execute("""SELECT c.relrowsecurity, c.relforcerowsecurity,
                                  has_any_column_privilege('authenticated', c.oid, 'SELECT'),
                                  has_any_column_privilege('anon', c.oid, 'SELECT'),
                                  has_any_column_privilege('service_role', c.oid, 'SELECT')
                           FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                           WHERE n.nspname = 'snippet_private'
                             AND c.relname IN ('recent_personal_snippets', 'recent_default_snippets')""")
            self.assertEqual(cur.fetchall(), [(True, True, False, False, False)] * 2)
            cur.execute("SELECT has_column_privilege('snippet_app','public.default_snippets','language','UPDATE')")
            self.assertFalse(cur.fetchone()[0])
            cur.execute("DELETE FROM auth.users WHERE id = %s", (user,))
            cur.execute("SELECT count(*) FROM snippet_private.recent_default_snippets WHERE user_id = %s", (user,))
            self.assertEqual(cur.fetchone()[0], 0)

    def test_category_review_confirm_merge_and_owner_scope(self):
        self.login()
        token = csrf(self.browser, "/")
        first = store.add_snippet(A, "A1", "Source", "code", language="html")
        second = store.add_snippet(A, "A2", "Source", "  code ")
        store.add_snippet(A, "A3", "Existing", "code")
        foreign = store.add_snippet(B, "B1", "Source", "code")
        store.set_favorite(A, second, True)
        store.record_recent(A, second)
        form = {"csrf_token": token, "source": "Source", "destination": "Existing"}
        self.assertEqual(self.browser.post("/categories", data={"destination": "X"}).status_code, 400)
        review = self.browser.post("/categories", data=form)
        self.assertIn("Move 2 personal snippets", review.text)
        self.assertEqual(store.get_snippet(A, first)[2], "Source")
        self.assertEqual(self.browser.post("/categories", data={**form, "confirm": "1", "expected": "3"}).status_code, 409)
        response = self.browser.post("/categories", data={**form, "confirm": "1", "expected": "2"})
        self.assertEqual(response.status_code, 303)
        self.assertEqual(store.get_snippet(A, first, extended=True)[2:], ("Existing", "code", "html", False))
        self.assertEqual(store.get_snippet(B, foreign)[2], "Source")
        self.assertEqual(self.browser.post("/categories", data={
            "csrf_token": token, "snippet_ids": [first, foreign], "destination": "Only one",
        }).status_code, 409)
        selected = {"csrf_token": token, "snippet_ids": [second], "destination": "Moved"}
        self.assertIn("Move 1 personal snippet", self.browser.post("/categories", data=selected).text)
        self.assertEqual(self.browser.post("/categories", data={**selected, "confirm": "1", "expected": "1"}).status_code, 303)
        self.assertEqual(store.get_snippet(A, second)[2:], ("Moved", "  code "))
        self.assertIn('id="recent-title"', self.browser.get("/?scope=favorites&category=Moved").text)

    def test_registration_shows_verification_instructions_and_provisions_starters_once(self):
        email = "new@sample.test"
        password = "testpass"
        first = self.form("/register", email=email, password=password)
        duplicate = self.form("/register", email=email.upper(), password="other-password")
        self.assertEqual((first.status_code, first.location), (303, "/verification-pending"))
        self.assertEqual((duplicate.status_code, duplicate.location), (303, first.location))
        self.assertEqual(first.data, duplicate.data)
        for browser in (self.browser, self.app.test_client()):
            notice = browser.get(first.location)
            for copy in (b"<h1>Check your email</h1>", b"inbox and Spam", b"Continue", b"Resend confirmation",
                         b'href="/login"', b"Wait a few minutes"):
                self.assertIn(copy, notice.data)
            self.assertNotIn(email.encode(), notice.data)
        owner = auth.provider.pending[email]
        self.assertEqual(self.personal_snippets(owner), [])
        pending_token = fake_jwt(owner, str(uuid4()))
        with patch("auth.provider", return_value={"sub": owner, "email_verified": False}):
            self.assertEqual(self.browser.get("/api/snippets", headers=bearer(pending_token)).status_code, 401)
        self.assertIn(b"request a new confirmation", self.form("/login", email=email, password=password).data)
        self.verify_email_token("signup", email)
        self.assertEqual(self.browser.get("/").location, "/login")
        self.assertEqual(self.form("/login", email=email, password="other-password").status_code, 401)
        self.assertEqual(self.form("/login", email=email, password=password).status_code, 303)
        owner = auth.provider.confirmed[email]
        snippets = self.personal_snippets(owner)
        self.assertEqual({row[1]: row[2] for row in snippets}, STARTERS)
        self.assertEqual(len(snippets), 4)
        self.assertIn(b"Hello World", self.browser.get("/").data)
        self.assertEqual(self.browser.post("/logout", data={"csrf_token": csrf(self.browser, "/")}).status_code, 303)
        self.assertEqual(self.browser.get("/").location, "/login")

    def test_registration_validation_and_private_testing_forms(self):
        self.assertEqual(self.form("/register", email="invalid", password=PASSWORD).status_code, 400)
        self.assertEqual(self.form("/register", email="short@sample.test", password="").status_code, 400)
        response = self.form("/register", email="short@sample.test", password="abc")
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"longer or stronger password", response.data)
        self.assertNotIn(b"12 characters", self.browser.get("/register").data)
        for path in ("/forgot-password", "/resend-confirmation"):
            self.assertIn(path.encode(), self.browser.get("/login").data)
            self.assertEqual(self.browser.get(path).status_code, 200)

    def verify_email_token(self, kind, email, client=None):
        client = client or self.browser
        path = CONFIRM_LINK if kind == "signup" else RESET_LINK
        value = uuid4().hex
        auth.provider.links[value] = (kind, email)
        landing = client.get(path)
        self.assertEqual(landing.status_code, 200)
        self.assertNotIn(value, landing.headers.get("Set-Cookie", ""))
        self.assertNotIn(value.encode(), landing.data)
        self.assertIn(b"/static/email_link.js", landing.data)
        self.assertIn("script-src 'self'", landing.headers["Content-Security-Policy"])
        self.assertIn(value, auth.provider.links)
        self.assertEqual(landing.headers["Referrer-Policy"], "no-referrer")
        self.assertEqual(landing.headers["Cache-Control"], "no-store")
        self.assertEqual(client.post(path, data={}).status_code, 400)
        self.assertIn(value, auth.provider.links)
        return client.post(path, data={"csrf_token": csrf(client, path), "token_hash": value})

    def test_email_link_wrong_type_expired_and_replayed(self):
        email = "b@sample.test"
        value = uuid4().hex
        auth.provider.links[value] = ("recovery", email)
        wrong = self.form(CONFIRM_LINK, token_hash=value, type="recovery", next="https://bad.test")
        self.assertEqual(wrong.status_code, 400)
        self.assertIn(value, auth.provider.links)
        self.assertEqual(self.form(RESET_LINK, token_hash=uuid4().hex).status_code, 400)
        self.assertEqual(self.form(RESET_LINK, token_hash=value).location, NEW_PASSWORD)
        self.assertEqual(self.form(RESET_LINK, token_hash=value).status_code, 400)
        self.verify_email_token("recovery", email)
        self.assertEqual(self.browser.get("/").location, "/login")
        self.assertEqual(self.form(CONFIRM_LINK, password="other-pass").status_code, 400)
        self.assertEqual(self.browser.get("/api/snippets", headers=bearer(fake_jwt(B, SESSION_B, client_id=None))).status_code, 401)
        with store.cursor() as cur:
            cur.execute("UPDATE snippet_private.email_flows SET expires_at = now() - interval '1 second'")
        self.assertEqual(self.browser.get(NEW_PASSWORD).status_code, 400)

    def test_recovery_changes_password_and_revokes_stale_sessions(self):
        original = self.browser
        self.login()
        recovery = self.app.test_client()
        self.assertEqual(self.verify_email_token("recovery", "a@sample.test", recovery).location, NEW_PASSWORD)
        self.assertEqual(recovery.get("/").location, "/login")
        self.browser = recovery
        self.assertEqual(self.form(NEW_PASSWORD, password="new-pass", password_confirmation="different").status_code, 400)
        token = csrf(recovery, NEW_PASSWORD)
        values = {"csrf_token": token, "password": "new-pass", "password_confirmation": "new-pass"}
        self.assertEqual(recovery.post(NEW_PASSWORD, data=values).location, "/login")
        self.assertEqual(recovery.post(NEW_PASSWORD, data=values).status_code, 400)
        self.assertEqual(original.get("/").location, "/login")
        # Simulate a still-valid old JWT after provider logout.
        old_jwt = fake_jwt(A, SESSION_A)
        auth.provider.oauth_tokens[old_jwt] = A
        self.assertEqual(self.browser.get("/api/snippets", headers=bearer(old_jwt)).status_code, 401)
        self.assertEqual(self.browser.get("/api/snippets", headers=self.api_b).status_code, 200)
        auth.provider.token_offset = 2
        self.assertEqual(self.form("/login", email="a@sample.test", password=PASSWORD).status_code, 401)
        self.assertEqual(self.form("/login", email="a@sample.test", password="new-pass").location, "/")
        self.assertTrue(any(method == "DELETE" and path.startswith("/user/oauth/grants?")
                            for method, path, _ in auth.provider.calls))

    def test_held_legacy_account_cannot_use_verified_credentials_or_tokens(self):
        email = "legacy@sample.test"
        auth.provider.confirmed[email] = HELD
        old_jwt = fake_jwt(HELD, SESSION_A)
        auth.provider.oauth_tokens[old_jwt] = HELD
        self.assertEqual(self.form("/login", email=email, password=PASSWORD).status_code, 401)
        self.assertEqual(self.browser.get("/api/snippets", headers=bearer(old_jwt)).status_code, 401)
        with closing(psycopg2.connect(self.admin)) as conn, conn, conn.cursor() as cur:
            cur.execute("DELETE FROM snippet_private.legacy_email_holds WHERE user_id=%s", (HELD,))
        stale = self.browser
        self.assertEqual(self.login(email).location, "/")
        with closing(psycopg2.connect(self.admin)) as conn, conn, conn.cursor() as cur:
            cur.execute("INSERT INTO snippet_private.legacy_email_holds VALUES (%s)", (HELD,))
        self.assertEqual(stale.get("/").location, "/login")
        self.verify_email_token("recovery", email)
        self.assertEqual(self.form(NEW_PASSWORD, password="other-pass", password_confirmation="other-pass").location, "/login")
        auth.provider.token_offset = 2
        self.assertEqual(self.form("/login", email=email, password="other-pass").status_code, 401)
        with closing(psycopg2.connect(self.admin)) as conn, conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM snippet_private.legacy_email_holds WHERE user_id=%s", (HELD,))
            self.assertEqual(cur.fetchone(), (1,))
            cur.execute("DELETE FROM snippet_private.legacy_email_holds WHERE user_id=%s", (HELD,))
        try:
            auth.provider.oauth_tokens[old_jwt] = HELD
            self.assertEqual(self.browser.get("/api/snippets", headers=bearer(old_jwt)).status_code, 401)
            self.assertEqual(self.form("/login", email=email, password="other-pass").location, "/")
        finally:
            with closing(psycopg2.connect(self.admin)) as conn, conn, conn.cursor() as cur:
                cur.execute("INSERT INTO snippet_private.legacy_email_holds VALUES (%s)", (HELD,))

    def test_resend_recovery_rate_limits_and_provider_failures(self):
        for path in ("/resend-confirmation", "/forgot-password"):
            expected = "/verification-pending" if path == "/resend-confirmation" else "/login"
            for _ in range(3):
                self.assertEqual(self.form(path, email="unknown@sample.test").location, expected)
            limited = self.form(path, email="unknown@sample.test")
            self.assertEqual(limited.status_code, 429)
            if path == "/resend-confirmation":
                self.assertIn(b"Wait a few minutes before requesting another link", limited.data)
            with patch("auth.provider", side_effect=auth.AuthError(429)):
                self.assertEqual(self.form(path, email="b@sample.test").location, expected)
            with patch("auth.provider", side_effect=auth.AuthError(503)):
                self.assertEqual(self.form(path, email="b@sample.test").status_code, 503)
        auth.provider.autoconfirm = True
        self.assertEqual(self.form("/register", email="disabled@sample.test", password=PASSWORD).status_code, 503)
        self.assertNotIn("disabled@sample.test", auth.provider.pending)

    def test_login_validation_cookie_rotation_refresh_and_logout(self):
        self.assertEqual(self.form("/login", email="unconfirmed@sample.test", password=PASSWORD).status_code, 401)
        self.assertEqual(self.form("/login", email="a@sample.test", password="wrong").status_code, 401)
        before = csrf(self.browser, "/login")
        response = self.login()
        cookie = response.headers["Set-Cookie"]
        for attribute in ("__Host-snippet_session", "Secure", "HttpOnly", "SameSite=Lax"):
            self.assertIn(attribute, cookie)
        self.assertNotEqual(before, csrf(self.browser, "/"))
        with store.cursor() as cur:
            cur.execute("UPDATE snippet_private.web_sessions SET token_expires_at = %s", (int(time.time()) - 1,))
        self.assertEqual(self.browser.get("/").status_code, 200)
        self.assertTrue(any("refresh_token" in path for _, path, _ in auth.provider.calls))
        old = self.browser.get_cookie("__Host-snippet_session").value
        self.assertEqual(self.browser.post("/logout", data={"csrf_token": csrf(self.browser, "/")}).status_code, 303)
        self.browser.set_cookie("__Host-snippet_session", old)
        self.assertEqual(self.browser.get("/").location, "/login")

    def test_registration_preserves_vscode_authorization_request(self):
        path = "/register?authorization_id=" + ATTEMPT
        notice = self.form(path, email="vscode@sample.test", password=PASSWORD)
        self.assertEqual(notice.location, "/verification-pending?authorization_id=" + ATTEMPT)
        pending = self.browser.get(notice.location)
        signin_path = "/login?authorization_id=" + ATTEMPT
        resend_path = "/resend-confirmation?authorization_id=" + ATTEMPT
        self.assertIn(signin_path.encode(), pending.data)
        self.assertIn(resend_path.encode(), pending.data)
        self.assertIn(b"start sign-in again from VS Code", pending.data)
        self.assertEqual(self.browser.post(resend_path, data={"email": "vscode@sample.test"}).status_code, 400)
        self.assertEqual(self.form(resend_path, email="vscode@sample.test").location, notice.location)
        self.verify_email_token("signup", "vscode@sample.test")
        self.assertIn(b"start its sign-in again", self.browser.get("/login").data)
        signin = self.form(signin_path, email="vscode@sample.test", password=PASSWORD)
        self.assertEqual(signin.location, "/oauth/consent?authorization_id=" + ATTEMPT)

    def test_account_deletion_instructions_require_sign_in_and_only_offer_support(self):
        path = "/account/deletion"
        self.assertEqual(self.browser.get(path).location, "/login")
        self.login()
        self.assertIn(f'href="{path}"'.encode(), self.browser.get("/").data)
        instructions = self.browser.get(path)
        self.assertEqual(instructions.status_code, 200)
        for copy in (b"mailto:snippo.support@gmail.com", b"explicitly confirm deletion", b"snippets it owns"):
            self.assertIn(copy, instructions.data)
        self.assertNotIn(b"<form", instructions.data)
        self.assertEqual(self.browser.post(path, data={"csrf_token": csrf(self.browser, "/")}).status_code, 405)

    def test_deletion_schema_requires_targeted_snippet_cleanup(self):
        owner = self.create_account(confirmed=True)
        other = store.add_snippet(A, "Keep", "Fixture", "print(1)")
        with self.assertRaises(psycopg2.errors.ForeignKeyViolation):
            self.auth_sql("DELETE FROM auth.users WHERE id = %s", (owner,))
        with store.cursor() as cur:
            cur.execute("INSERT INTO snippet_private.session_cutoffs VALUES (%s, 0)", (owner,))
        with closing(psycopg2.connect(self.admin)) as conn, conn, conn.cursor() as cur:
            cur.execute("DELETE FROM public.snippets WHERE owner_id = %s", (owner,))
            self.assertEqual(cur.rowcount, len(STARTERS))
        # Exercise only the database constraints in the disposable fixture.
        self.auth_sql("DELETE FROM auth.users WHERE id = %s", (owner,))
        with store.cursor() as cur:
            cur.execute("SELECT count(*) FROM snippet_private.session_cutoffs WHERE user_id = %s", (owner,))
            self.assertEqual(cur.fetchone(), (0,))
        with closing(psycopg2.connect(self.admin)) as conn, conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM public.snippets WHERE sno IN (%s, %s)", (other, LEGACY[0]))
            self.assertEqual(cur.fetchone(), (2,))

    def test_rate_limit_is_shared_across_clients(self):
        for _ in range(8):
            self.assertEqual(self.form("/login", email="a@sample.test", password="wrong").status_code, 401)
        self.browser = self.app.test_client()
        self.assertEqual(self.form("/login", email="a@sample.test", password="wrong").status_code, 429)

    def test_anonymous_api_and_csrf(self):
        for method, path in (("GET", "/api/snippets"), ("GET", "/api/snippets/17"),
                             ("POST", "/api/snippets"), ("DELETE", "/api/snippets/17")):
            response = self.browser.open(path, method=method)
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(response.headers["WWW-Authenticate"], "Bearer")
        self.assertEqual(self.browser.get("/").location, "/login")
        self.assertEqual(self.browser.post("/add", data={}).status_code, 400)
        self.assertEqual(self.browser.post("/delete/17", data={"csrf_token": csrf(self.browser, "/login")}).location, "/login")
        self.login()
        self.assertEqual(self.browser.post("/add", data={}).status_code, 400)
        self.assertEqual(self.browser.post("/logout", data={}).status_code, 400)
        self.assertEqual(self.browser.get("/api/snippets").status_code, 401)

    def test_api_owner_isolation_categories_and_compatibility(self):
        first = self.api_create(self.api_a, owner_id=B, cat="only A")
        second = self.api_create(self.api_b, cat="only B")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(self.api_create(self.api_a).status_code, 409)
        a_id = first.json["sno"]
        b_id = second.json["sno"]
        mine = self.browser.get(f"/api/snippets/{a_id}", headers=self.api_a)
        self.assertEqual(mine.json, {"sno": a_id, "name": "shared name", "cat": "only A", "code": "test code"})
        self.assertEqual(self.browser.get(f"/api/snippets/{b_id}", headers=self.api_a).status_code, 404)
        self.assertEqual(self.browser.delete(f"/api/snippets/{b_id}", headers=self.api_a).status_code, 404)
        self.assertEqual(self.browser.get("/api/snippets/17", headers=self.api_a).status_code, 404)
        self.assertEqual(self.browser.get("/api/snippets?category=only%20B&search=shared", headers=self.api_a).json, [])
        own = self.browser.get("/api/snippets?search=TEST", headers=self.api_b).json
        self.assertEqual([item["sno"] for item in own], [b_id])
        self.assertEqual(self.browser.delete(f"/api/snippets/{a_id}", headers=self.api_a).json, {"message": "Snippet deleted"})

    def test_web_owner_isolation_and_search(self):
        self.login()
        self.assertEqual(self.browser.post("/add", data={
            "csrf_token": csrf(self.browser, "/"), "name": "Alice example", "cat": "private A", "code": "A code",
            "owner_id": B,
        }).status_code, 303)
        b_id = self.api_create(self.api_b, name="Bob example", cat="private B").json["sno"]
        listing = self.browser.get("/?search=code")
        self.assertIn(b"Alice example", listing.data)
        self.assertNotIn(b"private B", listing.data)
        self.assertNotIn(b"Alice example", self.browser.get("/?category=private+B").data)
        self.assertEqual(self.browser.post(f"/delete/{b_id}", data={"csrf_token": csrf(self.browser, "/")}).status_code, 404)
        a_id = self.browser.get("/api/snippets", headers=self.api_a).json[0]["sno"]
        self.assertEqual(self.browser.post(f"/delete/{a_id}", data={"csrf_token": csrf(self.browser, "/")}).status_code, 303)

    def test_api_invalid_client_forgery_revocation_and_outage(self):
        foreign = fake_jwt(A, SESSION_A, client_id="unrelated")
        auth.provider.oauth_tokens[foreign] = A
        self.assertEqual(self.browser.get("/api/session", headers=bearer(foreign)).status_code, 401)
        forged = fake_jwt(A, SESSION_A, signature="forged")
        self.assertEqual(self.browser.get("/api/session", headers=bearer(forged)).status_code, 401)
        self.assertEqual(self.browser.post("/api/logout", headers=self.api_a).status_code, 204)
        renewed = fake_jwt(A, SESSION_A, signature="refreshed")
        auth.provider.oauth_tokens[renewed] = A
        self.assertEqual(self.browser.get("/api/session", headers=bearer(renewed)).status_code, 401)
        self.assertEqual(self.browser.get("/api/session", headers=self.api_b).status_code, 200)
        with patch("auth.provider", side_effect=auth.AuthError(503)):
            self.assertEqual(self.browser.get("/api/session", headers=self.api_b).status_code, 503)

    def test_oauth_rejects_invalid_or_ambiguous_authorization_ids(self):
        signed_out = self.app.test_client()
        for value in ("", "../consent", "x/y", "x?y", "x#y", "x%2Fy", "x y", "é", "x\r\ny", "x" * 129):
            with self.subTest(value=value):
                response = signed_out.get("/oauth/consent", query_string={"authorization_id": value})
                self.assertEqual(response.status_code, 400)
        path = "/oauth/consent?authorization_id=" + ATTEMPT
        self.assertEqual(signed_out.get(path + "&authorization_id=duplicate").status_code, 400)
        self.assertEqual(signed_out.get("/oauth/consent").status_code, 400)
        self.assertEqual(auth.provider.calls, [])

        self.login()
        token = csrf(self.browser, path)
        calls = len(auth.provider.calls)
        response = self.browser.post(path, data={"csrf_token": token, "authorization_id": "conflict", "action": "approve"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(auth.provider.calls), calls)

    def test_uuid_shaped_authorization_id_is_preserved_without_normalization(self):
        opaque_id = "ABCDEF01-2345-6789-ABCD-EF0123456789"
        response = self.browser.get("/oauth/consent", query_string={"authorization_id": opaque_id})
        self.assertEqual(response.location, "/login?authorization_id=" + opaque_id)

    def test_browser_oauth_redirect_and_provider_revocation(self):
        path = "/oauth/consent?authorization_id=" + ATTEMPT
        self.assertEqual(self.browser.get(path).location, "/login?authorization_id=" + ATTEMPT)
        login_path = "/login?authorization_id=" + ATTEMPT
        credentials = {"csrf_token": csrf(self.browser, login_path), "email": "a@sample.test",
                       "password": PASSWORD, "authorization_id": ATTEMPT}
        self.assertEqual(self.browser.post("/login", data=credentials).location, path)
        page = self.browser.get(path)
        self.assertIn(b"Connect VS Code", page.data)
        self.assertIn(f'name="authorization_id" value="{ATTEMPT}"'.encode(), page.data)
        self.assertEqual(self.browser.post(path, data={"action": "approve"}).status_code, 400)
        data = {"csrf_token": csrf(self.browser, path), "action": "approve", "authorization_id": ATTEMPT}
        self.assertEqual(
            self.browser.post("/oauth/consent", data=data).location,
            ORIGIN + auth.CALLBACK_PATH + "?state=" + "a" * 43 + "&code=foo",
        )
        self.assertIn(("POST", f"/oauth/authorizations/{ATTEMPT}/consent", {"action": "approve"}), auth.provider.calls)
        auth.provider.invalid_redirect = True
        self.assertEqual(self.browser.post("/oauth/consent", data=data).status_code, 400)
        callback = self.browser.get(auth.CALLBACK_PATH, query_string={"state": "a" * 43, "code": "test"})
        self.assertIn(b"vscode://dineshkaarthik.snippo-code-snippets/auth", callback.data)
        self.assertEqual(self.browser.get(auth.CALLBACK_PATH + "?state=bogus&code=foo").status_code, 400)
        self.assertEqual(self.browser.post("/oauth/vscode/revoke", data=data).status_code, 200)
        self.assertEqual(self.browser.get("/api/session", headers=self.api_a).status_code, 401)
        self.assertEqual(self.browser.get("/api/session", headers=self.api_b).status_code, 200)

    def test_callback_success_and_decline_enable_handoff_with_manual_fallbacks(self):
        state = "a" * 43
        for parameters, heading, payload in (
            ({"code": "test-code"}, b"Authorization successful", "code=test-code"),
            ({"error": "access_denied"}, b"Authorization declined", "error=access_denied"),
        ):
            with self.subTest(parameters=parameters):
                response = self.browser.get(auth.CALLBACK_PATH, query_string={"state": state, **parameters})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
                self.assertEqual(response.headers["Cache-Control"], "no-store")
                self.assertIn(heading, response.data)
                self.assertIn(b"Snippo", response.data)
                self.assertIn(b'href="/" target="_blank" rel="noopener noreferrer"', response.data)
                self.assertIn(b"Manage my snippets", response.data)
                self.assertIn(b"/static/vscode_callback.css", response.data)
                self.assertIn(b'<script src="/static/vscode_launch.js" defer>', response.data)
                self.assertIn("script-src 'self'", response.headers["Content-Security-Policy"])
                self.assertIn(b'id="open-vscode"', response.data)
                self.assertNotIn(b"data-launch-marker", response.data)
                self.assertIsNone(response.headers.get("Location"))
                for scheme in ("vscode", "vscode-insiders"):
                    uri = f'{scheme}://dineshkaarthik.snippo-code-snippets/auth?state={state}&amp;{payload}'
                    self.assertIn(uri.encode(), response.data)
        self.assertNotIn("script-src", self.browser.get("/login").headers["Content-Security-Policy"])
        invalid = self.browser.get(auth.CALLBACK_PATH, query_string={"state": "bogus", "code": "test"})
        self.assertEqual(invalid.status_code, 400)
        self.assertNotIn(b"/static/vscode_launch.js", invalid.data)

    def test_only_fresh_matching_consent_issues_short_lived_launch(self):
        self.login()
        consent_url = "/oauth/consent?authorization_id=" + ATTEMPT
        consent = {"csrf_token": csrf(self.browser, consent_url), "action": "approve", "authorization_id": ATTEMPT}
        callback = self.browser.post("/oauth/consent", data=consent).location.removeprefix(ORIGIN)
        with self.browser.session_transaction() as signed_session:
            grant = signed_session[auth.VSCODE_LAUNCH_SESSION_KEY]
            self.assertEqual(set(grant), {"digest", "expires"})
        self.assertNotIn(b"data-launch-marker", self.browser.get(callback.replace("code=foo", "code=other")).data)
        self.assertNotIn(b"data-launch-marker", self.app.test_client().get(callback).data)
        fresh = self.browser.get(callback)
        marker = re.search(rb'data-launch-marker="([0-9a-f]{64})"', fresh.data)[1]
        self.assertNotIn(b"data-launch-marker", self.browser.get(callback).data)
        clean_url = self.browser.get(auth.CALLBACK_PATH)
        self.assertIn(b"start sign-in again from VS Code", clean_url.data)
        self.assertNotIn(b'id="open-vscode"', clean_url.data)

        provider_fixture = auth.provider
        with patch("auth.provider", side_effect=lambda method, path, **kwargs:
                   {"redirect_url": ORIGIN + callback} if path.startswith("/oauth/authorizations/")
                   else provider_fixture(method, path, **kwargs)):
            for method in ("GET", "POST"):
                response = (self.browser.get(consent_url) if method == "GET"
                            else self.browser.post("/oauth/consent", data=consent))
                self.assertEqual(response.location, ORIGIN + callback)
                self.assertNotIn(b"data-launch-marker", self.browser.get(callback).data)

        later = callback.replace("a" * 43, "b" * 43).replace("code=foo", "code=bar")
        with patch("auth.provider", side_effect=lambda method, path, **kwargs:
                   {"redirect_url": ORIGIN + later} if path.endswith("/consent")
                   else provider_fixture(method, path, **kwargs)):
            self.assertEqual(self.browser.post("/oauth/consent", data=consent).location, ORIGIN + later)
        later_marker = re.search(rb'data-launch-marker="([0-9a-f]{64})"', self.browser.get(later).data)[1]
        self.assertNotEqual(marker, later_marker)

        self.browser.post("/oauth/consent", data=consent)
        with self.browser.session_transaction() as signed_session:
            grant = signed_session[auth.VSCODE_LAUNCH_SESSION_KEY]
            signed_session[auth.VSCODE_LAUNCH_SESSION_KEY] = {**grant, "expires": 1}
        self.assertNotIn(b"data-launch-marker", self.browser.get(callback).data)
        consent["action"] = "deny"
        denied_url = self.browser.post("/oauth/consent", data=consent).location.removeprefix(ORIGIN)
        denied = self.browser.get(denied_url)
        self.assertIn(b"Authorization declined", denied.data)
        self.assertNotIn(b"data-launch-marker", denied.data)

    def test_cleanup_can_run_without_owning_the_managed_auth_table(self):
        cleanup = RETIRE_STARTERS.strip().removeprefix("BEGIN;").removesuffix("COMMIT;")
        with closing(psycopg2.connect(self.admin)) as conn, conn.cursor() as cur:
            cur.execute("""
                ALTER TABLE auth.users OWNER TO supabase_auth_admin;
                GRANT SELECT, UPDATE ON auth.users TO wp01_migrator;
                ALTER TABLE public.default_snippets OWNER TO wp01_migrator;
                SET LOCAL ROLE wp01_migrator;
            """)
            cur.execute("SELECT pg_has_role(current_user, 'supabase_auth_admin', 'USAGE'), "
                        "pg_has_role(current_user, 'snippet_starter', 'SET')")
            self.assertEqual(cur.fetchone(), (False, False))
            cur.execute(cleanup)
            conn.rollback()

    def test_db_rls_and_revoked_api_acl(self):
        row_id = store.add_snippet(A, "SQL fixture", "rls", "fixture")
        with store.cursor(B) as cur:
            cur.execute("SELECT sno FROM public.snippets")
            self.assertEqual(cur.fetchall(), [])
            cur.execute("DELETE FROM public.snippets WHERE sno = %s", (row_id,))
            self.assertEqual(cur.rowcount, 0)
        with store.cursor() as cur:
            cur.execute("SELECT sno FROM public.snippets")
            self.assertEqual(cur.fetchall(), [])
        with self.assertRaises(psycopg2.errors.InsufficientPrivilege):
            with store.cursor(B) as cur:
                cur.execute("INSERT INTO public.snippets (owner_id, name, cat, code) VALUES (%s, 'a', 'b', 'c')", (A,))
        for role in ("anon", "authenticated", "service_role"):
            with closing(psycopg2.connect(self.admin)) as conn, conn, conn.cursor() as cur:
                cur.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
                cur.execute("SELECT has_table_privilege(current_user, 'public.snippets', 'SELECT,INSERT,DELETE')")
                self.assertFalse(cur.fetchone()[0])
                cur.execute("SELECT has_schema_privilege(current_user, 'snippet_private', 'USAGE')")
                self.assertFalse(cur.fetchone()[0])
                with self.assertRaises(psycopg2.errors.InsufficientPrivilege):
                    cur.execute("SELECT * FROM public.snippets")
                conn.rollback()
        with closing(psycopg2.connect(self.admin)) as conn, conn, conn.cursor() as cur:
            cur.execute("SELECT sno, name, cat, code FROM public.snippets WHERE owner_id IS NULL")
            self.assertEqual(cur.fetchall(), [LEGACY])

    def test_explicit_mapping_preserves_fields_and_isolates_legacy_row(self):
        with closing(psycopg2.connect(self.admin)) as conn, conn, conn.cursor() as cur:
            cur.execute("UPDATE snippets SET owner_id = %s WHERE sno = %s AND owner_id IS NULL", (A, LEGACY[0]))
            self.assertEqual(cur.rowcount, 1)
        self.addCleanup(self.restore_legacy_fixture)
        self.assertEqual(store.get_snippet(A, LEGACY[0]), LEGACY)
        self.assertIsNone(store.get_snippet(B, LEGACY[0]))

    def restore_legacy_fixture(self):
        with closing(psycopg2.connect(self.admin)) as conn, conn, conn.cursor() as cur:
            cur.execute("UPDATE snippets SET owner_id = NULL WHERE sno = %s", (LEGACY[0],))

    def test_migration_is_versioned_and_replay_fails_without_changes(self):
        with closing(psycopg2.connect(self.admin)) as conn, conn.cursor() as cur:
            conn.autocommit = True
            with self.assertRaises(psycopg2.errors.DuplicateObject):
                cur.execute(MIGRATION)
            cur.execute("ROLLBACK")
            cur.execute("SELECT sno, name, cat, code FROM snippets")
            self.assertEqual(cur.fetchall(), [LEGACY])

    def auth_sql(self, query, params=()):
        with closing(psycopg2.connect(self.admin)) as conn, conn, conn.cursor() as cur:
            cur.execute("SET LOCAL ROLE supabase_auth_admin")
            cur.execute(query, params)

    def create_account(self, confirmed=False):
        user = str(uuid4())
        self.auth_sql(
            "INSERT INTO auth.users (id, email_confirmed_at) VALUES (%s, CASE WHEN %s THEN now() END)",
            (user, confirmed),
        )
        return user

    def confirm_account(self, user):
        self.auth_sql(
            "UPDATE auth.users SET email_confirmed_at = coalesce(email_confirmed_at, now()) WHERE id = %s", (user,),
        )

    def personal_snippets(self, owner):
        with store.cursor(owner) as cur:
            cur.execute("SELECT sno, name, cat, code FROM public.snippets WHERE owner_id = %s ORDER BY sno", (owner,))
            return cur.fetchall()

    def test_shared_defaults_are_filtered_read_only_and_keep_the_api_shape(self):
        a = self.browser.get("/api/snippets", headers=self.api_a).json
        self.assertEqual(a, self.browser.get("/api/snippets", headers=self.api_b).json)
        self.assertEqual({row["name"]: row["cat"] for row in a}, STARTERS)
        self.assertEqual(len(a), 4)
        hello = next(row for row in a if row["name"] == "Hello World")
        self.assertEqual(set(hello), {"sno", "name", "cat", "code"})
        self.assertEqual(hello["sno"], store.DEFAULT_ID_MIN)
        self.assertEqual(self.browser.get("/api/snippets?category=Basics&search=print", headers=self.api_b).json,
                         [hello])
        url = f"/api/snippets/{hello['sno']}"
        self.assertEqual(self.browser.get(url, headers=self.api_b).json, hello)
        self.assertEqual(self.browser.get(url).status_code, 401)
        self.assertEqual(self.browser.delete(url, headers=self.api_a).status_code, 404)
        personal = self.api_create(self.api_a, name=hello["name"]).json
        self.assertLess(personal["sno"], store.DEFAULT_ID_MIN)
        self.assertEqual(self.browser.get(f"/api/snippets/{personal['sno']}", headers=self.api_b).status_code, 404)
        self.login()
        page = self.browser.get("/").data
        self.assertIn(b"Shared default", page)
        self.assertIn(b"Basics", page)
        self.assertNotIn(f'/delete/{hello["sno"]}'.encode(), page)
        self.assertEqual(self.browser.post(f'/delete/{hello["sno"]}', data={
            "csrf_token": csrf(self.browser, "/"),
        }).status_code, 404)
        self.assertEqual(self.browser.post("/api/logout", headers=self.api_b).status_code, 204)
        self.assertEqual(self.browser.get(url, headers=self.api_b).status_code, 401)

    def test_dashboard_combines_filters_and_preserves_invalid_drafts(self):
        self.login()
        self.api_create(self.api_a, name="Other personal", cat="Basics", code="# match & code")
        self.api_create(self.api_b, name="Secret", cat="Basics", code="# match & code")
        filters = "?search=match&category=Basics&scope=personal"
        page = self.browser.get("/" + filters)
        self.assertIn(b"Other personal", page.data)
        self.assertNotIn(b"Secret", page.data)
        self.assertNotIn(b"Hello World", page.data)
        self.assertIn(b"Clear filters", page.data)
        self.assertIn(b'scope=defaults&amp;search=match&amp;category=Basics', page.data)
        self.assertIn(b"No matching snippets", self.browser.get("/?search=match&category=Basics&scope=defaults").data)
        token = csrf(self.browser, "/")
        form = {"csrf_token": token, "name": "Draft title", "cat": "Basics", "code": " "}
        invalid = self.browser.post("/add" + filters, data=form)
        self.assertEqual(invalid.status_code, 400)
        self.assertIn(b'value="Draft title"', invalid.data)
        self.assertIn(b'role="alert"', invalid.data)
        self.assertIn(b"class=\"composer\" open", invalid.data)
        self.assertNotIn(b"Snippet added.", invalid.data)
        form["code"] = "# match & <code>"
        with patch("store.add_snippet", side_effect=psycopg2.OperationalError):
            failed = self.browser.post("/add" + filters, data=form)
        self.assertEqual(failed.status_code, 503)
        self.assertIn(b"match &amp; &lt;code&gt;", failed.data)
        self.assertNotIn(b"Snippet added.", failed.data)
        saved = self.browser.post("/add" + filters, data=form)
        self.assertEqual(saved.location, "/" + filters)
        self.assertIn(b"Snippet added.", self.browser.get(saved.location).data)
        self.assertNotIn(b"Snippet added.", self.browser.get(saved.location).data)
        self.assertIn("img-src 'self'", page.headers["Content-Security-Policy"])
        self.assertNotIn("img-src", self.browser.get("/login").headers["Content-Security-Policy"])

    def test_hide_restore_and_restore_all_are_account_scoped(self):
        self.login()
        token = csrf(self.browser, "/")
        default = store.DEFAULT_ID_MIN
        api = f"/api/snippets/{default}"
        hide = f"/defaults/{default}/hide"
        self.assertEqual(self.browser.post(hide).status_code, 400)
        for _ in range(2):
            hidden = self.browser.post(hide, data={"csrf_token": token, "user_id": B}, follow_redirects=True)
            self.assertIn(b"Default hidden.", hidden.data)
        self.assertEqual(self.browser.get(api, headers=self.api_a).status_code, 404)
        self.assertEqual(self.browser.get(api, headers=self.api_b).status_code, 200)
        self.assertEqual(self.browser.get("/api/snippets?search=Hello%20World", headers=self.api_a).json, [])
        self.assertEqual(self.browser.get("/api/snippets?search=Hello%20World", headers=self.api_b).json[0]["sno"], default)
        self.assertEqual(self.browser.post("/defaults/17/hide", data={"csrf_token": token}).status_code, 404)
        self.assertEqual(self.browser.post("/defaults/2147483648/restore", data={"csrf_token": token}).status_code, 404)
        other_browser = self.app.test_client()
        other_browser.post("/login", data={"csrf_token": csrf(other_browser, "/login"),
                                            "email": "a@sample.test", "password": PASSWORD})
        self.assertIn(b"Hidden defaults (1)", other_browser.get("/?scope=defaults").data)
        for _ in range(2):
            restored = self.browser.post(f"/defaults/{default}/restore?scope=defaults", data={"csrf_token": token},
                                         follow_redirects=True)
            self.assertIn(b"Default restored.", restored.data)
        self.assertEqual(self.browser.get(api, headers=self.api_a).status_code, 200)
        for sno in range(default, default + 4):
            self.browser.post(f"/defaults/{sno}/hide", data={"csrf_token": token})
        self.assertIn(b"No visible defaults", self.browser.get("/?scope=defaults").data)
        self.assertTrue(store.hide_default(B, default))
        restored = self.browser.post("/defaults/restore-all", data={"csrf_token": token}, follow_redirects=True)
        self.assertIn(b"All defaults restored.", restored.data)
        self.assertEqual(self.browser.get(api, headers=self.api_b).status_code, 404)
        self.assertEqual(len(self.browser.get("/api/snippets", headers=self.api_a).json), 4)

    def test_dashboard_account_feedback_reports_revocation_outcome(self):
        self.login()
        form = {"csrf_token": csrf(self.browser, "/"), "dashboard": "1"}
        endpoint = "/oauth/vscode/revoke?scope=defaults"
        provider_fixture = auth.provider

        def reject_revocation(method, path, **kwargs):
            if method == "DELETE" and path.startswith("/user/oauth/grants?"):
                raise auth.AuthError(503)
            return provider_fixture(method, path, **kwargs)

        with patch("auth.provider", side_effect=reject_revocation):
            failed = self.browser.post(endpoint, data=form, follow_redirects=True)
        self.assertIn(b"Could not confirm that VS Code sessions were revoked.", failed.data)
        self.assertNotIn(b"All VS Code sessions revoked.", failed.data)
        finished = self.browser.post(endpoint, data=form, follow_redirects=True)
        self.assertIn(b"All VS Code sessions revoked.", finished.data)
        self.assertIn(b'name="scope" value="defaults"', finished.data)
        signed_out = self.browser.post("/logout", data=form, follow_redirects=True)
        self.assertIn(b"Signed out of Snippo.", signed_out.data)

    def test_edit_and_duplicate_keep_source_code_and_owner_boundaries(self):
        raw = "\r\n\tprint('<tag>')  \r\n\n"
        source = self.api_create(self.api_a, name="Source", cat="Python", code=raw).json["sno"]
        foreign = self.api_create(self.api_b, name="Other owner").json["sno"]
        shared = store.DEFAULT_ID_MIN
        self.login()
        token = csrf(self.browser, "/")
        form = {"csrf_token": token, "name": "Renamed", "cat": "Python", "code": raw.replace("\r\n", "\n"),
                "owner_id": B, "sno": foreign}
        self.assertEqual(self.browser.post(f"/edit/{source}", data={"name": "No CSRF"}).status_code, 400)
        for sno in (foreign, shared, 2147483648):
            self.assertEqual(self.browser.post(f"/edit/{sno}", data=form).status_code, 404)
        self.assertEqual(self.browser.get(f"/duplicate/{foreign}").status_code, 404)
        self.assertEqual(self.browser.post(f"/duplicate/{foreign}", data=form).status_code, 404)
        self.assertIn(b'value="Source"', self.browser.get(f"/edit/{source}").data)
        self.assertIn(b'value="Source (copy)"', self.browser.get(f"/duplicate/{source}").data)
        self.assertIn(b'value="Hello World (copy)"', self.browser.get(f"/duplicate/{shared}").data)
        self.assertEqual(len(self.personal_snippets(A)), 1)
        invalid = self.browser.post(f"/edit/{source}", data={**form, "cat": " "})
        self.assertEqual(invalid.status_code, 400)
        self.assertIn(b'value="Renamed"', invalid.data)
        self.assertIn(f'/edit/{source}'.encode(), invalid.data)
        with patch("store.edit_snippet", side_effect=psycopg2.OperationalError("private connection details")):
            failed = self.browser.post(f"/edit/{source}", data=form)
        self.assertEqual(failed.status_code, 503)
        self.assertIn(b'value="Renamed"', failed.data)
        self.assertNotIn(b"private connection details", failed.data)
        self.assertNotIn(b"Snippet updated.", failed.data)
        self.assertIn(b"Snippet updated.", self.browser.post(f"/edit/{source}", data=form, follow_redirects=True).data)
        row = self.browser.get(f"/api/snippets/{source}", headers=self.api_a).json
        self.assertEqual(row, {"sno": source, "name": "Renamed", "cat": "Python", "code": raw})
        self.assertEqual(self.browser.get(f"/api/snippets/{source}", headers=self.api_b).status_code, 404)
        duplicate = self.browser.post(f"/duplicate/{source}", data=form, follow_redirects=True)
        self.assertIn(b"Snippet duplicated.", duplicate.data)
        rows = self.personal_snippets(A)
        self.assertEqual([row[1:] for row in rows], [("Renamed", "Python", raw)] * 2)
        self.assertEqual(rows[0][0], source)
        self.assertNotEqual(rows[1][0], source)
        self.assertTrue(store.hide_default(A, shared))
        self.assertEqual(self.browser.get(f"/duplicate/{shared}").status_code, 404)
        self.assertEqual(self.browser.post(f"/duplicate/{shared}", data=form).status_code, 404)

    def test_favorites_combine_with_filters_and_preserve_hidden_state(self):
        older = self.api_create(self.api_a, name="Zebra", cat="Basics", code="match").json["sno"]
        newer = self.api_create(self.api_a, name="Alpha", cat="Basics", code="match").json["sno"]
        foreign = self.api_create(self.api_b, name="Other owner", cat="Basics").json["sno"]
        shared = store.DEFAULT_ID_MIN
        self.login()
        token = csrf(self.browser, "/")
        favorite = {"csrf_token": token, "action": "add", "user_id": B}
        for sno in (older, newer, shared, older):
            self.assertEqual(self.browser.post(f"/favorites/{sno}", data=favorite).status_code, 303)
        self.assertEqual(self.browser.post(f"/favorites/{foreign}", data=favorite).status_code, 404)
        self.assertEqual(self.browser.post("/favorites/2147483648", data=favorite).status_code, 404)
        self.assertEqual(self.browser.post(f"/favorites/{older}").status_code, 400)
        self.assertEqual(self.browser.post(f"/favorites/{older}", data={**favorite, "action": "wrong"}).status_code, 400)
        for order, expected in (("default", [older, newer]), ("name", [newer, older]),
                                ("newest", [newer, older]), ("oldest", [older, newer])):
            rows, _ = store.list_snippets(A, "match", "Basics", scope="favorites", sort=order)
            self.assertEqual([row[0] for row in rows], expected)
        page = self.browser.get("/?scope=favorites&search=match&category=Basics&sort=newest")
        self.assertIn(b"2 snippets", page.data)
        self.assertLess(page.data.index(b"<h2>Alpha"), page.data.index(b"<h2>Zebra"))
        self.assertIn(b"Insertion order within personal and shared snippets.", page.data)
        self.assertEqual(store.list_snippets(B, scope="favorites")[0], [])
        self.assertTrue(store.hide_default(A, shared))
        self.assertNotIn(b"<h2>Hello World", self.browser.get("/?scope=favorites").data)
        self.assertTrue(store.restore_default(A, shared))
        self.assertIn(b"<h2>Hello World", self.browser.get("/?scope=favorites").data)
        self.assertEqual(store.list_snippets(A, scope="favorites")[0][-1][0], shared)
        self.assertEqual(self.browser.post(f"/favorites/{older}", data={**favorite, "action": "remove"}).status_code, 303)
        self.assertTrue(store.delete_snippet(A, newer))
        self.assertEqual([row[0] for row in store.list_snippets(A, scope="favorites")[0]], [shared])
        api_rows = self.browser.get("/api/snippets?scope=favorites&sort=name", headers=self.api_a).json
        self.assertEqual(len(api_rows), 5)
        self.assertTrue(all(set(item) == {"sno", "name", "cat", "code"} for item in api_rows))

    def test_favorites_and_edit_database_privileges(self):
        personal = store.add_snippet(A, "Personal", "Fixture", "owner code")
        shared = store.DEFAULT_ID_MIN
        self.assertTrue(store.set_favorite(A, personal, True))
        with store.cursor(B) as cur:
            cur.execute("UPDATE public.snippets SET code = 'wrong' WHERE sno = %s", (personal,))
            self.assertEqual(cur.rowcount, 0)
            cur.execute("SELECT * FROM snippet_private.favorite_personal_snippets")
            self.assertFalse(cur.fetchall())
            with self.assertRaises(psycopg2.errors.ForeignKeyViolation):
                cur.execute("INSERT INTO snippet_private.favorite_personal_snippets VALUES (%s, %s)", (B, personal))
        with store.cursor(B) as cur:
            with self.assertRaises(psycopg2.errors.InsufficientPrivilege):
                cur.execute("INSERT INTO snippet_private.favorite_default_snippets VALUES (%s, %s)", (A, shared))
        with store.cursor(A) as cur:
            with self.assertRaises(psycopg2.errors.InsufficientPrivilege):
                cur.execute("UPDATE public.snippets SET owner_id = %s WHERE sno = %s", (B, personal))
        with closing(psycopg2.connect(self.admin)) as conn, conn.cursor() as cur:
            cur.execute("SELECT has_column_privilege('snippet_app', 'public.snippets', 'sno', 'UPDATE'), "
                        "has_table_privilege('snippet_app', 'public.default_snippets', 'UPDATE')")
            self.assertEqual(cur.fetchone(), (False, False))
            for role in ("anon", "authenticated", "service_role"):
                cur.execute("SELECT has_table_privilege(%s, 'snippet_private.favorite_default_snippets', 'SELECT'), "
                            "has_table_privilege(%s, 'snippet_private.favorite_personal_snippets', 'SELECT')",
                            (role, role))
                self.assertEqual(cur.fetchone(), (False, False))
            cur.execute("INSERT INTO snippet_private.favorite_default_snippets VALUES (%s, %s)", (B, shared))
            cur.execute("DELETE FROM public.default_snippets WHERE sno = %s", (shared,))
            cur.execute("SELECT count(*) FROM snippet_private.favorite_default_snippets")
            self.assertEqual(cur.fetchone(), (0,))
            cur.execute("SELECT count(*) FROM snippet_private.favorite_personal_snippets")
            self.assertEqual(cur.fetchone(), (1,))
            user = str(uuid4())
            cur.execute("INSERT INTO auth.users (id) VALUES (%s)", (user,))
            cur.execute("INSERT INTO snippet_private.favorite_default_snippets VALUES (%s, %s)", (user, shared + 1))
            cur.execute("DELETE FROM auth.users WHERE id = %s", (user,))
            cur.execute("SELECT count(*) FROM snippet_private.favorite_default_snippets")
            self.assertEqual(cur.fetchone(), (0,))
            conn.rollback()

    def test_highlighting_is_escaped_and_copy_data_round_trips(self):
        code = "  <img src=x onerror=alert(1)>\r\n<script>alert(1)</script>  \n"
        self.api_create(self.api_a, name="HTML sample", cat="HTML", code=code)
        self.api_create(self.api_a, name="Text sample", cat="Misc", code="literal <tag>")
        self.login()
        highlighted = self.browser.get("/?search=HTML+sample").get_data(as_text=True)
        self.assertNotIn("<script>alert(1)</script>", highlighted)
        self.assertNotIn("<img src=x", highlighted)
        self.assertIn("syntax-name", highlighted)
        data_copy = re.search(r'data-copy="([^"]*)"', highlighted)[1]
        self.assertEqual(json.loads(unescape(data_copy)), code)
        plain = self.browser.get("/?search=Text+sample").get_data(as_text=True)
        self.assertIn("<code>literal &lt;tag&gt;</code>", plain)

    def test_preference_rls_grants_and_fk_cascade(self):
        table = "snippet_private.hidden_default_snippets"
        self.assertTrue(store.hide_default(A, store.DEFAULT_ID_MIN))
        with store.cursor(B) as cur:
            cur.execute(f"SELECT count(*) FROM {table}")
            self.assertEqual(cur.fetchone(), (0,))
            cur.execute(f"DELETE FROM {table} WHERE user_id = %s", (A,))
            self.assertEqual(cur.rowcount, 0)
            with self.assertRaises(psycopg2.errors.InsufficientPrivilege):
                cur.execute(f"INSERT INTO {table} VALUES (%s, %s)", (A, store.DEFAULT_ID_MIN + 1))
        with store.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM {table}")
            self.assertEqual(cur.fetchone(), (0,))
        with closing(psycopg2.connect(self.admin)) as conn, conn.cursor() as cur:
            for role in ("anon", "authenticated", "service_role"):
                cur.execute("SELECT has_table_privilege(%s, %s, 'SELECT,INSERT,UPDATE,DELETE')", (role, table))
                self.assertFalse(cur.fetchone()[0])
            cur.execute("SELECT has_table_privilege('snippet_app', %s, 'UPDATE')", (table,))
            self.assertFalse(cur.fetchone()[0])
            user = str(uuid4())
            cur.execute("INSERT INTO auth.users (id) VALUES (%s)", (user,))
            cur.execute("INSERT INTO public.default_snippets (name,cat,code) VALUES ('New template','Fixture','code') RETURNING sno")
            fresh = cur.fetchone()[0]
            cur.execute(f"INSERT INTO {table} VALUES (%s,%s), (%s,%s)", (user, store.DEFAULT_ID_MIN, A, fresh))
            cur.execute("DELETE FROM auth.users WHERE id=%s", (user,))
            cur.execute("DELETE FROM public.default_snippets WHERE sno=%s", (fresh,))
            cur.execute(f"SELECT user_id::text,snippet_id FROM {table}")
            self.assertEqual(cur.fetchall(), [(A, store.DEFAULT_ID_MIN)])
            conn.rollback()
        with closing(psycopg2.connect(self.admin)) as conn, conn, conn.cursor() as cur:
            cur.execute("INSERT INTO public.default_snippets (name,cat,code) VALUES ('New template','Fixture','code') RETURNING sno")
            added = cur.fetchone()[0]
        def remove_fixture():
            with closing(psycopg2.connect(self.admin)) as conn, conn, conn.cursor() as cur:
                cur.execute("DELETE FROM public.default_snippets WHERE sno=%s", (added,))
        self.addCleanup(remove_fixture)
        for headers in (self.api_a, self.api_b):
            self.assertEqual(self.browser.get(f"/api/snippets/{added}", headers=headers).status_code, 200)

    def test_default_database_privileges_and_id_bounds(self):
        with store.cursor() as cur:
            cur.execute("SELECT count(*) FROM public.default_snippets")
            self.assertEqual(cur.fetchone(), (0,))
        with store.cursor(A) as cur:
            cur.execute("SELECT count(*) FROM public.default_snippets")
            self.assertEqual(cur.fetchone(), (4,))
            with self.assertRaises(psycopg2.errors.InsufficientPrivilege):
                cur.execute("DELETE FROM public.default_snippets")
        with closing(psycopg2.connect(self.admin)) as conn, conn.cursor() as cur:
            for role in ("anon", "authenticated", "service_role"):
                cur.execute("SELECT has_table_privilege(%s, 'public.default_snippets', 'SELECT,INSERT,UPDATE,DELETE')",
                            (role,))
                self.assertFalse(cur.fetchone()[0])
            with self.assertRaises(psycopg2.errors.CheckViolation):
                cur.execute("INSERT INTO public.snippets VALUES (%s, 'x', 'x', 'x', %s)", (store.DEFAULT_ID_MIN, A))
            conn.rollback()
            cur.execute("INSERT INTO public.default_snippets (name, cat, code) VALUES ('x', 'x', 'x') RETURNING sno")
            self.assertGreater(cur.fetchone()[0], store.DEFAULT_ID_MIN)
            conn.rollback()

    def test_cleanup_revalidates_scope_and_archives_only_reviewed_rows(self):
        legacy_ids = [1, 2, 3, 9, 10, 11, 14, 15, 16]
        seed_groups = ([43, 44, 45, 46], [47, 48, 49, 50], [52, 53, 54, 55])
        owners = [A, B, HELD]
        cleanup = RETIRE_STARTERS.strip().removeprefix("BEGIN;").removesuffix("COMMIT;")
        with closing(psycopg2.connect(self.admin)) as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO public.snippets (sno,name,cat,code) SELECT id,'old','test','old' FROM unnest(%s) id",
                        (legacy_ids,))
            for owner, group in zip(owners, seed_groups):
                cur.execute("""
                    INSERT INTO public.snippets (sno,name,cat,code,owner_id)
                    SELECT chosen.id, d.name, d.cat, d.code, %s
                    FROM unnest(%s) WITH ORDINALITY AS chosen(id, n)
                    JOIN public.default_snippets d ON d.sno = %s + chosen.n - 1
                """, (owner, group, store.DEFAULT_ID_MIN))
            cur.execute("""
                INSERT INTO public.snippets (sno,name,cat,code,owner_id) VALUES (51,'Functions','coding','keep',%s);
                INSERT INTO public.snippets (sno,name,cat,code,owner_id)
                SELECT 56,name,cat,code,%s FROM public.default_snippets WHERE sno = %s
            """, (A, B, store.DEFAULT_ID_MIN))
            ids = legacy_ids + [sno for group in seed_groups for sno in group]
            cur.execute("""
                SELECT jsonb_build_object(
                    'candidates', jsonb_object_agg(sno, hash) FILTER (WHERE sno <> 51),
                    'protected', max(hash) FILTER (WHERE sno = 51)
                )::text
                FROM (
                    SELECT s.sno, encode(sha256(convert_to(to_jsonb(s)::text, 'UTF8')), 'hex') AS hash
                    FROM public.snippets s WHERE sno = ANY(%s)
                ) fingerprints
            """, (ids + [51],))
            cur.execute("SELECT set_config('snippet.wp04_review', %s, true)", cur.fetchone())
            cur.execute("SAVEPOINT before_edits")
            cur.execute("UPDATE public.snippets SET code = 'changed' WHERE sno = 43")
            with self.assertRaises(psycopg2.errors.RaiseException):
                cur.execute(cleanup)
            cur.execute("ROLLBACK TO SAVEPOINT before_edits")
            cur.execute(cleanup)
            cur.execute("SELECT sno FROM public.snippets ORDER BY sno")
            self.assertEqual([row[0] for row in cur.fetchall()], [LEGACY[0], 51, 56])
            cur.execute("SELECT sno FROM snippet_private.wp04_snippet_archive ORDER BY sno")
            self.assertEqual([row[0] for row in cur.fetchall()], ids)
            self.assertFalse(self._archive_client_access(cur))
            pending = str(uuid4())
            cur.execute("SET LOCAL ROLE supabase_auth_admin")
            cur.execute("INSERT INTO auth.users (id) VALUES (%s)", (pending,))
            cur.execute("UPDATE auth.users SET email_confirmed_at = now() WHERE id = %s", (pending,))
            cur.execute("UPDATE auth.users SET email_confirmed_at = now() WHERE id = %s", (pending,))
            cur.execute("RESET ROLE")
            cur.execute("SELECT count(*) FROM public.snippets WHERE owner_id = %s", (pending,))
            self.assertEqual(cur.fetchone(), (0,))
            cur.execute("""
                INSERT INTO public.snippets
                SELECT (jsonb_populate_record(NULL::public.snippets, original_row)).*
                FROM snippet_private.wp04_snippet_archive
            """)
            self.assertEqual(cur.rowcount, 21)
            conn.rollback()

    def _archive_client_access(self, cur):
        cur.execute("""
            SELECT bool_or(has_table_privilege(role, 'snippet_private.wp04_snippet_archive', 'SELECT'))
            FROM unnest(ARRAY['anon','authenticated','service_role','snippet_app']) role
        """)
        return cur.fetchone()[0]

    def test_cleanup_waits_for_auth_writer_and_can_retry(self):
        cleanup = RETIRE_STARTERS.strip().removeprefix("BEGIN;").removesuffix("COMMIT;")
        with closing(psycopg2.connect(self.admin)) as writer, writer.cursor() as writer_cur, \
             closing(psycopg2.connect(self.admin)) as migrator, migrator.cursor() as migration_cur:
            writer_cur.execute("INSERT INTO auth.users (id) VALUES (%s)", (str(uuid4()),))
            with self.assertRaises(psycopg2.errors.LockNotAvailable):
                migration_cur.execute(cleanup.replace("'3s'", "'100ms'"))
            migrator.rollback()
            writer.rollback()
            migration_cur.execute(cleanup)
            migrator.rollback()

    def test_confirmed_on_signup_and_existing_accounts(self):
        new_user = self.create_account(confirmed=True)
        self.assertEqual({row[1]: row[2] for row in self.personal_snippets(new_user)}, STARTERS)
        self.confirm_account(B)
        self.assertEqual(self.personal_snippets(A), [])
        self.assertEqual(self.personal_snippets(B), [])
        self.assertIsNone(store.get_snippet(new_user, LEGACY[0]))

    def test_concurrent_confirmation_seeds_once_and_respects_deletion(self):
        new_user = self.create_account()
        self.assertEqual(self.personal_snippets(new_user), [])
        barrier = Barrier(2)

        def confirm():
            barrier.wait(timeout=5)
            self.confirm_account(new_user)

        with ThreadPoolExecutor(max_workers=2) as workers:
            futures = [workers.submit(confirm) for _ in range(2)]
            for future in futures:
                future.result(timeout=10)

        rows = self.personal_snippets(new_user)
        self.assertEqual(len(rows), 4)
        self.assertEqual({row[1]: row[2] for row in rows}, STARTERS)
        for _, name, _, code in rows:
            compile(code, name, "exec")
        auth.provider.confirmed["new@sample.test"] = new_user
        self.login("new@sample.test")
        for name in STARTERS:
            self.assertIn(name.encode(), self.browser.get("/").data)
        token = fake_jwt(new_user, str(uuid4()))
        auth.provider.oauth_tokens[token] = new_user
        api = bearer(token)
        self.assertEqual(len(self.browser.get("/api/snippets", headers=api).json), 8)
        self.assertEqual(len(self.browser.get("/api/snippets", headers=self.api_a).json), 4)
        hello = next(row for row in rows if row[1] == "Hello World")
        self.assertEqual(self.browser.delete(f"/api/snippets/{hello[0]}", headers=api).status_code, 200)
        self.confirm_account(new_user)
        self.login("new@sample.test")
        self.assertIn(b"Hello World", self.browser.get("/").data)
        self.assertEqual(len(self.browser.get("/api/snippets", headers=api).json), 7)

    def test_failed_provisioning_rolls_back_and_pending_signup_can_be_deleted(self):
        pending = self.create_account()
        self.auth_sql("DELETE FROM auth.users WHERE id = %s", (pending,))
        user = self.create_account()
        with closing(psycopg2.connect(self.admin)) as conn, conn, conn.cursor() as cur:
            cur.execute("ALTER TABLE public.snippets ADD CONSTRAINT fixture_failure CHECK (name != 'Function Template')")
        try:
            with self.assertRaises(psycopg2.errors.CheckViolation):
                self.confirm_account(user)
            self.assertEqual(self.personal_snippets(user), [])
        finally:
            with closing(psycopg2.connect(self.admin)) as conn, conn, conn.cursor() as cur:
                cur.execute("ALTER TABLE public.snippets DROP CONSTRAINT fixture_failure")
        self.confirm_account(user)
        self.assertEqual(len(self.personal_snippets(user)), 4)

    def test_starter_role_cannot_read_or_write_outside_owner_context(self):
        with closing(psycopg2.connect(self.admin)) as conn, conn.cursor() as cur:
            cur.execute("SELECT rolcanlogin, rolbypassrls FROM pg_roles WHERE rolname = 'snippet_starter'")
            self.assertEqual(cur.fetchone(), (False, False))
            cur.execute("SET LOCAL ROLE snippet_starter")
            cur.execute("SELECT has_table_privilege(current_user, 'public.snippets', 'SELECT,DELETE')")
            self.assertFalse(cur.fetchone()[0])
            cur.execute("SELECT set_config('snippet.owner_id', %s, true)", (A,))
            with self.assertRaises(psycopg2.errors.InsufficientPrivilege):
                cur.execute(
                    "INSERT INTO public.snippets (owner_id, name, cat, code) VALUES (%s, 'a', 'b', 'c')", (B,),
                )

    def test_starter_rollback_keeps_owned_rows_and_disables_provisioning(self):
        starter_rollback = STARTER_UNDO.strip().removeprefix("BEGIN;").removesuffix("COMMIT;")
        user = self.create_account(confirmed=True)
        with closing(psycopg2.connect(self.admin)) as conn, conn.cursor() as cur:
            cur.execute("SET LOCAL ROLE wp01_migrator")
            cur.execute(starter_rollback)
            cur.execute("RESET ROLE")
            cur.execute("SELECT count(*) FROM public.snippets WHERE owner_id = %s", (user,))
            self.assertEqual(cur.fetchone()[0], 4)
            cur.execute("INSERT INTO auth.users (id, email_confirmed_at) VALUES (%s, now())", (str(uuid4()),))
            cur.execute("SELECT count(*) FROM public.snippets")
            self.assertEqual(cur.fetchone()[0], 5)
            conn.rollback()

    def test_migration_rollback_fails_closed_with_assigned_rows_and_preserves_legacy(self):
        starter_rollback = STARTER_UNDO.strip().removeprefix("BEGIN;").removesuffix("COMMIT;")
        ownership_rollback = UNDO.strip().removeprefix("BEGIN;").removesuffix("COMMIT;")
        public_rollback = PUBLIC_UNDO.split("BEGIN;", 1)[1].removesuffix("COMMIT;\n")
        rollback_body = (
            "DROP TABLE snippet_private.recent_personal_snippets, snippet_private.recent_default_snippets;"
            "ALTER TABLE public.snippets DROP COLUMN language, DROP COLUMN template;"
            "DROP TABLE snippet_private.favorite_personal_snippets, snippet_private.favorite_default_snippets;"
            "ALTER TABLE public.snippets DROP CONSTRAINT snippets_owner_sno_key;"
            "DROP POLICY snippets_update_owned ON public.snippets;"
            "REVOKE UPDATE (name, cat, code) ON public.snippets FROM snippet_app;"
            "DROP TABLE snippet_private.hidden_default_snippets;"
            "DROP TABLE public.default_snippets;"
            "ALTER TABLE public.snippets DROP CONSTRAINT snippets_personal_id_range;"
            "ALTER SEQUENCE public.snippets_sno_seq MAXVALUE 2147483647;"
            + public_rollback + "SET LOCAL ROLE wp01_migrator;" + starter_rollback + "RESET ROLE;" + ownership_rollback
        )
        store.add_snippet(A, "keep", "rls", "keep")
        with closing(psycopg2.connect(self.admin)) as conn, conn.cursor() as cur:
            with self.assertRaises(psycopg2.errors.RaiseException):
                cur.execute(rollback_body)
            conn.rollback()
            cur.execute("DELETE FROM public.snippets WHERE owner_id IS NOT NULL")
            cur.execute(rollback_body)
            cur.execute("SELECT sno, name, cat, code FROM public.snippets")
            self.assertEqual(cur.fetchall(), [LEGACY])
            cur.execute("SELECT has_table_privilege('anon', 'public.snippets', 'SELECT')")
            self.assertFalse(cur.fetchone()[0])
            conn.rollback()


class ApplicationConfigurationTest(unittest.TestCase):
    def test_missing_configuration_fails_closed(self):
        app = main.create_app({"SECRET_KEY": "", "TESTING": True})
        client = app.test_client()
        self.assertEqual(client.get("/").status_code, 503)
        self.assertEqual(client.get("/api/snippets").status_code, 503)

    def test_origin_rejects_remote_http_and_userinfo(self):
        self.assertFalse(main.valid_origin("http://remote.test", True))
        self.assertFalse(main.valid_origin("https://user:secret@remote.test", False))
        self.assertTrue(main.valid_origin("http://127.0.0.1:5000", True))


if __name__ == "__main__":
    unittest.main()
