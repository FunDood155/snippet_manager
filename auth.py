import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from http.cookiejar import DefaultCookiePolicy
from threading import local
from urllib.parse import parse_qs, quote, urlencode, urlsplit
from uuid import UUID, uuid4

import psycopg2
import requests
from flask import (
    Blueprint, abort, current_app, flash, g, jsonify, redirect, render_template, request, session, url_for,
)
from werkzeug.exceptions import TooManyRequests

import store

bp = Blueprint("auth", __name__)
EMAIL = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
AUTHORIZATION_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
EMAIL_TOKEN_HASH = re.compile(r"[A-Za-z0-9_-]{20,256}")
EMAIL_LINK_PATHS = {"signup": "/auth/confirm-email", "recovery": "/auth/reset-password"}
CALLBACK_PATH = "/oauth/vscode/callback"
VSCODE_LAUNCH_TTL = 60
VSCODE_LAUNCH_SESSION_KEY = "vscode_launch"
provider_transport = local()
INVALID_SESSION_STATUSES = (400, 401, 403, 404, 422)


def provider_session():
    # Requests sessions carry mutable state. Reuse the transport only on this worker thread.
    if not hasattr(provider_transport, "session"):
        client = requests.Session()
        client.cookies.set_policy(DefaultCookiePolicy(allowed_domains=()))
        provider_transport.session = client
    return provider_transport.session


class AuthError(Exception):
    def __init__(self, status, code=None):
        self.status = status
        self.code = code


def provider(method, path, *, token=None, body=None):
    config = current_app.config
    headers = {"apikey": config["SUPABASE_PUBLISHABLE_KEY"]}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = provider_session().request(
            method, config["SUPABASE_URL"] + "/auth/v1" + path,
            headers=headers, json=body, timeout=(3, 5), allow_redirects=False,
        )
        if not response.ok or response.is_redirect:
            code = response.headers.get("x-sb-error-code")
            if not code and response.content:
                try:
                    payload = response.json()
                    if isinstance(payload, dict):
                        code = payload.get("error_code") or payload.get("code")
                except ValueError:
                    pass
            raise AuthError(response.status_code, code if isinstance(code, str) else None)
        return response.json() if response.content else {}
    except (requests.RequestException, ValueError):
        raise AuthError(503) from None


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def protect_form():
    expected = session.get("csrf")
    supplied = request.form.get("csrf_token", "")
    if not expected or not hmac.compare_digest(supplied.encode(), expected.encode()):
        abort(400, "Invalid form token. Reload the page and try again.")


def digest(value):
    key = current_app.secret_key.encode()
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()


def limit(action, subject, max_hits, total_hits):
    window = int(time.time()) // 300
    global_bucket = digest(f"{action}:all") if total_hits else None
    subject_bucket = digest(f"{action}:input:{subject}")
    # A failed subject check never spends the shared budget. Roll back the
    # subject increment if another request takes the last shared slot first.
    with store.cursor() as cur:
        cur.execute(
            """WITH subject AS (
                   INSERT INTO snippet_private.auth_limits AS counters (bucket, window_id, hits)
                   SELECT %(subject)s, %(window)s, 1 WHERE NOT EXISTS (
                       SELECT 1 FROM snippet_private.auth_limits
                       WHERE bucket = %(global)s AND window_id = %(window)s AND hits >= %(total)s
                   )
                   ON CONFLICT (bucket) DO UPDATE SET window_id = excluded.window_id,
                       hits = CASE WHEN counters.window_id = excluded.window_id THEN counters.hits + 1 ELSE 1 END
                   WHERE counters.window_id < excluded.window_id
                      OR (counters.window_id = excluded.window_id AND counters.hits < %(maximum)s)
                   RETURNING hits
               ), shared AS (
                   INSERT INTO snippet_private.auth_limits AS counters (bucket, window_id, hits)
                   SELECT %(global)s::text, %(window)s, 1 FROM subject WHERE %(global)s::text IS NOT NULL
                   ON CONFLICT (bucket) DO UPDATE SET window_id = excluded.window_id,
                       hits = CASE WHEN counters.window_id = excluded.window_id THEN counters.hits + 1 ELSE 1 END
                   WHERE counters.window_id < excluded.window_id
                      OR (counters.window_id = excluded.window_id AND counters.hits < %(total)s)
                   RETURNING hits
               ), swept AS (
                   DELETE FROM snippet_private.auth_limits WHERE bucket IN (
                       SELECT bucket FROM snippet_private.auth_limits
                       WHERE window_id < %(window)s - 1
                         AND bucket <> %(subject)s AND bucket IS DISTINCT FROM %(global)s::text
                       ORDER BY window_id, bucket LIMIT 64 FOR UPDATE SKIP LOCKED
                   )
               )
               SELECT EXISTS (SELECT 1 FROM subject)
                   AND (%(global)s::text IS NULL OR EXISTS (SELECT 1 FROM shared))""",
            {"subject": subject_bucket, "global": global_bucket, "window": window,
             "maximum": max_hits, "total": total_hits},
        )
        if not cur.fetchone()[0]:
            abort(429, "Too many attempts. Wait a few minutes and try again.")


def prune_credentials(cur, table):
    # Callers use these two fixed table names. Each has an expiry index.
    cur.execute(f"""DELETE FROM snippet_private.{table} WHERE handle_hash IN (
                       SELECT handle_hash FROM snippet_private.{table}
                       WHERE expires_at <= statement_timestamp()
                       ORDER BY expires_at LIMIT 64 FOR UPDATE SKIP LOCKED)""")


def account_lock(cur, owner):
    cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"auth-transition:{owner}",))


def stage_transition(owner, kind, *, flow=None):
    ticket = str(uuid4())
    # Commit the denial before an upstream mutation can start. A replacement
    # attempt invalidates the first ticket, including during its handoff gap.
    with store.cursor() as cur:
        account_lock(cur, owner)
        if flow and not read_email_flow(cur, flow):
            raise AuthError(401)
        cur.execute("SELECT pending FROM snippet_private.auth_transitions WHERE user_id = %s", (owner,))
        row = cur.fetchone()
        pending = row[0] if row else None
        if pending == "recovery" and kind == "oauth":
            raise AuthError(503)
        cur.execute("""INSERT INTO snippet_private.auth_transitions (user_id, pending, operation_id)
                       VALUES (%s, %s, %s) ON CONFLICT (user_id) DO UPDATE
                       SET pending = excluded.pending, operation_id = excluded.operation_id""",
                    (owner, kind, ticket))
    return ticket, pending


def lock_transition(cur, owner, ticket):
    account_lock(cur, owner)
    cur.execute("SELECT 1 FROM snippet_private.auth_transitions WHERE user_id = %s AND operation_id = %s",
                (owner, ticket))
    if not cur.fetchone():
        raise AuthError(503)


def finish_transition(cur, owner, *, revoked):
    client_id = current_app.config["SNIPPET_VSCODE_CLIENT_ID"] if revoked else None
    cur.execute("""UPDATE snippet_private.auth_transitions SET pending = NULL, operation_id = NULL,
                       oauth_invalid_through = CASE WHEN %s::uuid IS NOT NULL THEN greatest(
                           oauth_invalid_through, snippet_private.oauth_revocation_boundary(user_id, %s))
                       ELSE oauth_invalid_through END WHERE user_id = %s""", (client_id, client_id, owner))


def restore_transition(cur, owner, previous):
    if previous is None:
        finish_transition(cur, owner, revoked=False)
    elif previous == "oauth":
        cur.execute("UPDATE snippet_private.auth_transitions SET pending = 'oauth' WHERE user_id = %s", (owner,))


def revoke_provider_grant(token):
    path = "/user/oauth/grants?" + urlencode({"client_id": vscode_client()})
    try:
        provider("DELETE", path, token=token)
    except AuthError as exc:
        if exc.status != 404:
            raise


def confirmed_identity(user):
    if not user.get("email_confirmed_at"):
        raise AuthError(401)
    try:
        return str(UUID(user["id"]))
    except (KeyError, TypeError, ValueError):
        raise AuthError(401) from None


def token_claims(token):
    middle = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(middle + "=" * (-len(middle) % 4)))


def account_state(cur, owner):
    cur.execute(
        """SELECT EXISTS (SELECT 1 FROM snippet_private.legacy_email_holds WHERE user_id = %(owner)s),
                  (SELECT invalid_through FROM snippet_private.session_cutoffs WHERE user_id = %(owner)s),
                  EXISTS (SELECT 1 FROM snippet_private.auth_transitions
                          WHERE user_id = %(owner)s AND pending = 'recovery')""",
        {"owner": owner},
    )
    return cur.fetchone()


def check_account_access(cur, owner, verified_token):
    held, cutoff, recovering = account_state(cur, owner)
    if recovering:
        raise AuthError(503)
    check_access_state(held, cutoff, verified_token)


def check_access_state(held, invalid_through, verified_token):
    if held:
        raise AuthError(401, "legacy_email_hold")
    if invalid_through is not None:
        try:
            issued_at = token_claims(verified_token)["iat"]
        except (AttributeError, KeyError, IndexError, TypeError, ValueError):
            raise AuthError(401) from None
        if type(issued_at) is not int or issued_at <= invalid_through:
            raise AuthError(401)


def create_session(tokens):
    owner = confirmed_identity(tokens["user"])
    handle = secrets.token_urlsafe(32)
    with store.cursor() as cur:
        check_account_access(cur, owner, tokens["access_token"])
        if session.get("handle"):
            cur.execute("DELETE FROM snippet_private.web_sessions WHERE handle_hash = %s", (digest(session["handle"]),))
        prune_credentials(cur, "web_sessions")
        cur.execute(
            """INSERT INTO snippet_private.web_sessions
               VALUES (%s, %s, %s, %s, %s, now() + interval '7 days')""",
            (digest(handle), owner, tokens["access_token"], tokens["refresh_token"],
             int(time.time()) + int(tokens["expires_in"])),
        )
    session.clear()
    session.permanent = True
    session["handle"] = handle


def read_web_session(cur, handle_hash, *, lock=False):
    sql = """SELECT user_id, access_token, refresh_token, token_expires_at,
                    EXISTS (SELECT 1 FROM snippet_private.legacy_email_holds WHERE user_id = w.user_id),
                    (SELECT invalid_through FROM snippet_private.session_cutoffs WHERE user_id = w.user_id),
                    EXISTS (SELECT 1 FROM snippet_private.auth_transitions
                            WHERE user_id = w.user_id AND pending = 'recovery')
             FROM snippet_private.web_sessions w
             WHERE handle_hash = %s AND expires_at > clock_timestamp()"""
    cur.execute(sql + (" FOR UPDATE OF w" if lock else ""), (handle_hash,))
    return cur.fetchone()


def discard_web_session(cur, handle_hash, version):
    cur.execute("""DELETE FROM snippet_private.web_sessions WHERE handle_hash = %s
                   AND user_id = %s AND access_token = %s AND refresh_token = %s AND token_expires_at = %s""",
                (handle_hash, *version))


def refresh_web_session(cur, handle_hash, row):
    owner, access, refresh, expires, held, cutoff, recovering = row
    if recovering:
        raise AuthError(503)
    try:
        check_access_state(held, cutoff, access)
        tokens = provider("POST", "/token?grant_type=refresh_token", body={"refresh_token": refresh})
        if confirmed_identity(tokens["user"]) != owner:
            raise AuthError(401)
        # A token issued during refresh must not bypass a cutoff applied to its source session.
        check_account_access(cur, owner, access)
        access = tokens["access_token"]
        cur.execute("""UPDATE snippet_private.web_sessions
                       SET access_token = %s, refresh_token = %s, token_expires_at = %s
                       WHERE handle_hash = %s AND expires_at > clock_timestamp()""",
                    (access, tokens["refresh_token"], int(time.time()) + int(tokens["expires_in"]), handle_hash))
        if cur.rowcount:
            return access
    except AuthError as exc:
        if exc.status not in INVALID_SESSION_STATUSES:
            raise
        discard_web_session(cur, handle_hash, row[:4])
    return None


def web_identity():
    if not session.get("handle"):
        return None
    handle_hash = digest(session["handle"])
    for _ in range(3):
        with store.cursor() as cur:
            row = read_web_session(cur, handle_hash)
        if row is None:
            break
        owner, access, _, expires, held, cutoff, recovering = row
        if recovering:
            raise AuthError(503)
        if expires < time.time() + 45:
            with store.cursor() as cur:
                current = read_web_session(cur, handle_hash, lock=True)
                if current is None:
                    break
                if current[:4] != row[:4]:
                    continue
                access = refresh_web_session(cur, handle_hash, current)
            if access:
                g.web_token = access
                return owner
            break

        # Verify ordinary tokens with no open transaction or row lock.
        try:
            check_access_state(held, cutoff, access)
            if confirmed_identity(provider("GET", "/user", token=access)) != owner:
                raise AuthError(401)
            verified = True
        except AuthError as exc:
            if exc.status not in INVALID_SESSION_STATUSES:
                raise
            verified = False

        with store.cursor() as cur:
            current = read_web_session(cur, handle_hash)
            if current is None:
                break
            if current[:4] != row[:4]:
                continue
            if current[6]:
                raise AuthError(503)
            try:
                check_access_state(*current[4:6], access)
                if not verified:
                    raise AuthError(401)
            except AuthError:
                discard_web_session(cur, handle_hash, row[:4])
                break
        g.web_token = access
        return owner

    session.clear()
    return None


def api_identity():
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token or len(token) > 8192:
        raise AuthError(401)
    user = provider("GET", "/oauth/userinfo", token=token)
    try:
        owner = str(UUID(user["sub"]))
        # Read claims only after Supabase has authenticated this exact bearer token.
        claims = token_claims(token)
        provider_session_id = str(UUID(claims["session_id"]))
        if user["email_verified"] is not True or claims["sub"] != owner or claims["client_id"] != vscode_client():
            raise AuthError(401)
    except (KeyError, IndexError, TypeError, ValueError):
        raise AuthError(401) from None
    with store.cursor() as cur:
        cur.execute(
            """SELECT EXISTS (SELECT 1 FROM snippet_private.legacy_email_holds WHERE user_id = %(owner)s),
                      (SELECT invalid_through FROM snippet_private.session_cutoffs WHERE user_id = %(owner)s),
                      EXISTS (SELECT 1 FROM snippet_private.revoked_vscode_sessions WHERE id = %(session)s)
                      OR EXISTS (
                          SELECT 1 FROM snippet_private.auth_transitions WHERE user_id = %(owner)s AND
                          (pending IS NOT NULL OR (oauth_invalid_through IS NOT NULL AND
                           NOT snippet_private.oauth_session_after(%(session)s, %(owner)s, %(client)s,
                                                                   oauth_invalid_through))))""",
            {"session": provider_session_id, "owner": owner, "client": vscode_client()},
        )
        held, cutoff, denied = cur.fetchone()
        check_access_state(held, cutoff, token)
        if denied:
            raise AuthError(401)
    g.api_session_id = provider_session_id
    return owner


def revoke_vscode_session(owner, session_id):
    with store.cursor() as cur:
        cur.execute(
            "INSERT INTO snippet_private.revoked_vscode_sessions (id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (session_id, owner),
        )


@bp.post("/oauth/vscode/revoke")
def revoke_vscode_grant():
    owner = web_identity()
    if not owner:
        return redirect(url_for("auth.login"), code=303)
    vscode_client()
    dashboard = request.form.get("dashboard") == "1"
    try:
        ticket, _ = stage_transition(owner, "oauth")
        with store.cursor() as cur:
            lock_transition(cur, owner, ticket)
            revoke_provider_grant(g.web_token)
            finish_transition(cur, owner, revoked=True)
    except (AuthError, psycopg2.Error):
        if not dashboard:
            raise
        flash("Could not confirm that VS Code sessions were revoked. Try again.", "library-error")
    else:
        if dashboard:
            flash("All VS Code sessions revoked.", "library-success")
    if dashboard:
        return redirect(url_for("home", search=request.args.get("search"), category=request.args.get("category"),
                                scope=request.args.get("scope"), sort=request.args.get("sort")), code=303)
    return render_template("auth.html", mode="revoked")


def auth_page(mode, error=None, status=200, authorization_id=None, account_email=None):
    return render_template(
        "auth.html", mode=mode, error=error, authorization_id=authorization_id,
        account_email=account_email,
    ), status


def pending_authorization():
    values = request.values.getlist("authorization_id")
    if not values:
        return None
    if len(values) != 1 or not AUTHORIZATION_ID.fullmatch(values[0]):
        abort(400, "Invalid authorization request.")
    return values[0]


@bp.route("/login", methods=["GET", "POST"])
def login():
    authorization_id = pending_authorization()
    if request.method == "GET":
        return auth_page("login", authorization_id=authorization_id)
    email = form_email()
    password = request.form.get("password", "")
    if not valid_email(email) or not 1 <= len(password) <= 128:
        return auth_page("login", "Enter a valid email address and password.", 400, authorization_id=authorization_id)
    limit("login", email, 8, 150)
    try:
        tokens = provider("POST", "/token?grant_type=password", body={"email": email, "password": password})
        create_session(tokens)
    except AuthError as exc:
        if exc.status in (400, 401, 403, 422):
            return auth_page("login", "Sign-in failed. Check your credentials or request a new confirmation link.", 401,
                             authorization_id=authorization_id)
        raise
    if authorization_id:
        return redirect(url_for("auth.consent", authorization_id=authorization_id), code=303)
    return redirect(url_for("home"), code=303)


def form_email():
    raw = request.form.get("email", "")
    return raw.strip().lower() if len(raw) <= 320 else ""


def valid_email(email):
    return len(email) <= 254 and EMAIL.fullmatch(email)


@bp.route("/register", methods=["GET", "POST"])
def register():
    authorization_id = pending_authorization()
    if request.method == "GET":
        return auth_page("register", authorization_id=authorization_id)

    email = form_email()
    password = request.form.get("password", "")
    if not valid_email(email):
        return auth_page("register", "Enter a valid email address.", 400, authorization_id=authorization_id)
    if not password or len(password) > 72 or len(password.encode()) > 72:
        return auth_page("register", "Enter a password of up to 72 bytes.", 400, authorization_id=authorization_id)

    limit("register", email, 3, 40)
    try:
        if provider("GET", "/settings").get("mailer_autoconfirm") is not False:
            abort(503, "Email verification is unavailable.")
        tokens = provider("POST", email_provider_path("/signup", "signup"),
                          body={"email": email, "password": password})
    except AuthError as exc:
        # Return the same public response for a new address and a duplicate address.
        if exc.status == 429 or exc.code in ("user_already_exists", "email_exists"):
            tokens = {}
        elif exc.code == "weak_password":
            return auth_page("register", "Choose a longer or stronger password.", 400,
                             authorization_id=authorization_id)
        elif exc.code == "email_address_invalid":
            return auth_page("register", "Enter a valid email address.", 400, authorization_id=authorization_id)
        elif exc.status in (400, 422):
            return auth_page("register", "Check your email address and password and try again.", 400,
                             authorization_id=authorization_id)
        else:
            raise

    # Auto-confirmed signups can issue a session. Discard it and require explicit sign-in.
    if tokens.get("access_token"):
        try:
            provider("POST", "/logout?scope=local", token=tokens["access_token"])
        except AuthError:
            current_app.logger.warning("Could not revoke an unused registration session")

    return redirect(url_for("auth.verification_pending", authorization_id=authorization_id), code=303)


@bp.get("/verification-pending")
def verification_pending():
    return auth_page("verification_pending", authorization_id=pending_authorization())


def email_provider_path(path, kind):
    site = current_app.config["SNIPPET_SITE_URL"]
    return path + "?" + urlencode({"redirect_to": site + EMAIL_LINK_PATHS[kind]})


@bp.route("/resend-confirmation", methods=["GET", "POST"], endpoint="resend_confirmation")
@bp.route("/forgot-password", methods=["GET", "POST"], endpoint="forgot_password")
def request_email_link():
    recovery = request.endpoint == "auth.forgot_password"
    mode = "forgot" if recovery else "resend"
    authorization_id = None if recovery else pending_authorization()
    if request.method == "GET":
        return auth_page(mode, authorization_id=authorization_id)
    email = form_email()
    if not valid_email(email):
        return auth_page(mode, "Enter a valid email address.", 400, authorization_id=authorization_id)
    try:
        limit("recover" if recovery else "resend", email, 3, 30)
    except TooManyRequests:
        if recovery:
            raise
        return auth_page(mode, "Too many attempts. Wait a few minutes before requesting another link.", 429,
                         authorization_id=authorization_id)
    kind = "recovery" if recovery else "signup"
    body = {"email": email} if recovery else {"email": email, "type": "signup"}
    try:
        provider("POST", email_provider_path("/recover" if recovery else "/resend", kind), body=body)
    except AuthError as exc:
        # Provider responses can differ by account existence or email quota.
        if exc.status not in (400, 404, 422, 429):
            raise
    if not recovery:
        return redirect(url_for("auth.verification_pending", authorization_id=authorization_id), code=303)
    flash("If this address is eligible, check your inbox for the link. Allow a few minutes for delivery.", "registration")
    return redirect(url_for("auth.login"), code=303)


@bp.route(EMAIL_LINK_PATHS["signup"], methods=["GET", "POST"], endpoint="confirm_email")
@bp.route(EMAIL_LINK_PATHS["recovery"], methods=["GET", "POST"], endpoint="reset_password")
def email_link():
    recovery = request.endpoint == "auth.reset_password"
    kind = "recovery" if recovery else "signup"
    if request.method == "GET":
        return auth_page("recovery_link" if recovery else "confirm_link")

    hashes = request.form.getlist("token_hash")
    if len(hashes) != 1 or not EMAIL_TOKEN_HASH.fullmatch(hashes[0]):
        return auth_page("invalid_link", status=400)
    proof = hashes[0]
    limit("email-link", proof, 5, 120)
    try:
        tokens = provider("POST", "/verify", body={"token_hash": proof, "type": kind})
        owner = confirmed_identity(tokens.get("user", {}))
        access = tokens["access_token"]
    except AuthError as exc:
        if exc.status not in (400, 401, 403, 404, 422):
            raise
        return auth_page("invalid_link", status=400)

    if recovery:
        handle = secrets.token_urlsafe(32)
        with store.cursor() as cur:
            prune_credentials(cur, "email_flows")
            if session.get("email_flow"):
                cur.execute("DELETE FROM snippet_private.email_flows WHERE handle_hash = %s",
                            (digest(session["email_flow"]),))
            cur.execute(
                """INSERT INTO snippet_private.email_flows (handle_hash, owner_id, access_token, expires_at)
                   VALUES (%s, %s, %s, now() + interval '10 minutes')""",
                (digest(handle), owner, access),
            )
        session.clear()
        session["email_flow"] = handle
        return redirect(url_for("auth.new_password"), code=303)

    discard_provider_session(access)
    flash("Email verified. Sign in to continue. If you started in VS Code, start its sign-in again.", "registration")
    return redirect(url_for("auth.login"), code=303)


def read_email_flow(cur, handle_hash):
    cur.execute("""SELECT access_token, owner_id FROM snippet_private.email_flows
                   WHERE handle_hash = %s AND expires_at > clock_timestamp()""", (handle_hash,))
    return cur.fetchone()


@bp.route("/auth/new-password", methods=["GET", "POST"])
def new_password():
    handle = session.get("email_flow")
    if handle:
        handle_hash = digest(handle)
        with store.cursor() as cur:
            row = read_email_flow(cur, handle_hash)
        if row:
            if request.method == "GET":
                return auth_page("reset")
            return finish_password_reset(row[1], handle_hash)
        session.pop("email_flow", None)
    return auth_page("invalid_link", status=400)


def discard_provider_session(access):
    try:
        provider("POST", "/logout?scope=local", token=access)
    except AuthError:
        current_app.logger.warning("Could not revoke an unused email-flow session")


def finish_password_reset(owner, handle_hash):
    password = request.form.get("password", "")
    if (not password or len(password) > 72 or len(password.encode()) > 72
            or password != request.form.get("password_confirmation")):
        return auth_page("reset", "Enter matching passwords of up to 72 bytes.", 400)

    ticket, previous = stage_transition(owner, "recovery", flow=handle_hash)
    with store.cursor() as cur:
        lock_transition(cur, owner, ticket)
        row = read_email_flow(cur, handle_hash)
        if not row:
            # No upstream mutation has run for this ticket.
            restore_transition(cur, owner, previous)
            return auth_page("invalid_link", status=400)
        access = row[0]
        try:
            provider("PUT", "/user", token=access, body={"password": password})
        except AuthError as exc:
            weak = exc.code in ("weak_password", "same_password")
            invalid = exc.status in (401, 403, 404)
            if not (weak or invalid):
                raise
            restore_transition(cur, owner, previous)
            if weak:
                return auth_page("reset", "Choose a different, stronger password.", 400)
            cur.execute("DELETE FROM snippet_private.email_flows WHERE handle_hash = %s", (handle_hash,))
            session.pop("email_flow", None)
            return auth_page("invalid_link", status=400)

        if current_app.config["SNIPPET_VSCODE_CLIENT_ID"]:
            revoke_provider_grant(access)
        # If any provider or database step fails, the committed recovery barrier
        # survives. A fresh verified recovery can retry with a different password.
        cur.execute(
            """INSERT INTO snippet_private.session_cutoffs VALUES (%s, floor(extract(epoch FROM clock_timestamp()))::bigint)
               ON CONFLICT (user_id) DO UPDATE
               SET invalid_through = greatest(session_cutoffs.invalid_through, excluded.invalid_through)""",
            (owner,),
        )
        cur.execute("DELETE FROM snippet_private.web_sessions WHERE user_id = %s", (owner,))
        cur.execute("DELETE FROM snippet_private.email_flows WHERE owner_id = %s", (owner,))
        finish_transition(cur, owner, revoked=True)
    session.clear()
    discard_provider_session(access)
    flash("Password changed. Sign in again on the website and in VS Code.", "registration")
    return redirect(url_for("auth.login"), code=303)


def end_web_session():
    with store.cursor() as cur:
        cur.execute("DELETE FROM snippet_private.web_sessions WHERE handle_hash = %s", (digest(session["handle"]),))


@bp.post("/logout")
def logout():
    revoked = True
    try:
        if web_identity():
            provider("POST", "/logout?scope=local", token=g.web_token)
    except AuthError:
        revoked = False
    finally:
        if session.get("handle"):
            end_web_session()
        session.clear()
    if not revoked:
        return auth_page("login", "Signed out here. The provider could not confirm revocation.", 503)
    if request.form.get("dashboard") == "1":
        flash("Signed out of Snippo.", "registration")
    return redirect(url_for("auth.login"), code=303)


def vscode_client():
    client = current_app.config["SNIPPET_VSCODE_CLIENT_ID"]
    if not client:
        abort(503, "VS Code sign-in is unavailable.")
    return client


def callback_url():
    return current_app.config["SNIPPET_SITE_URL"] + CALLBACK_PATH


@bp.get("/oauth/vscode/config")
def vscode_config():
    return jsonify(provider=current_app.config["SUPABASE_URL"], clientId=vscode_client(), redirectUri=callback_url())


def valid_callback(value):
    if not isinstance(value, str):
        return False
    try:
        target = urlsplit(value)
        return target._replace(query="", fragment="").geturl() == callback_url() and not target.fragment
    except ValueError:
        return False


def callback_payload(params):
    state = params.get("state", [])
    codes = params.get("code", [])
    errors = params.get("error", [])
    if (len(state) != 1 or not re.fullmatch(r"[\w-]{43}", state[0], re.ASCII)
            or len(codes) + len(errors) != 1 or (codes and not re.fullmatch(r"[\w.-]{1,512}", codes[0], re.ASCII))):
        return None
    return {"state": state[0], **({"code": codes[0]} if codes else {"error": "access_denied"})}


@bp.route("/oauth/consent", methods=["GET", "POST"])
def consent():
    authorization_id = pending_authorization()
    if not authorization_id:
        abort(400, "Missing authorization request.")
    owner = web_identity()
    if not owner:
        return redirect(url_for("auth.login", authorization_id=authorization_id))
    with store.cursor() as cur:
        account_lock(cur, owner)
        cur.execute("""SELECT pending IS NOT NULL OR oauth_invalid_through > statement_timestamp()
                       FROM snippet_private.auth_transitions WHERE user_id = %s""", (owner,))
        row = cur.fetchone()
        if row and row[0]:
            abort(503, "VS Code authorization is temporarily unavailable. Try again shortly.")
        check_account_access(cur, owner, g.web_token)
        return consent_for_authorization(authorization_id)


def consent_for_authorization(authorization_id):
    path = "/oauth/authorizations/" + quote(authorization_id, safe="")
    fresh_approval = False
    try:
        details = provider("GET", path, token=g.web_token)
        if "redirect_url" not in details:
            if details.get("client", {}).get("id") != vscode_client() or details.get("redirect_uri") != callback_url():
                abort(400, "Unrecognized authorization client or callback.")
            if request.method == "GET":
                return auth_page("consent", authorization_id=authorization_id,
                                 account_email=details.get("user", {}).get("email"))
            action = request.form.get("action")
            if action not in ("approve", "deny"):
                abort(400, "Invalid consent action.")
            details = provider("POST", path + "/consent", token=g.web_token, body={"action": action})
            fresh_approval = action == "approve"
    except AuthError as exc:
        if exc.status in (400, 401, 403, 404, 422):
            abort(400, "Authorization expired or is invalid. Restart sign-in from VS Code.")
        raise
    target = details.get("redirect_url")
    if not valid_callback(target):
        abort(400, "Unrecognized authorization callback.")
    if fresh_approval:
        payload = callback_payload(parse_qs(urlsplit(target).query, keep_blank_values=True))
        if payload and "code" in payload:
            session[VSCODE_LAUNCH_SESSION_KEY] = {
                "digest": digest("vscode-launch:" + urlencode(payload)),
                "expires": int(time.time()) + VSCODE_LAUNCH_TTL,
            }
    return redirect(target, code=303)


@bp.get(CALLBACK_PATH)
def vscode_callback():
    if not request.args:
        return render_template("vscode_callback.html", callback_ended=True)

    payload = callback_payload(request.args.to_dict(flat=False))
    if not payload:
        abort(400, "Invalid authorization callback. Restart sign-in from VS Code.")
    query = urlencode(payload)
    authorized = "code" in payload
    launch = None
    eligibility = session.get(VSCODE_LAUNCH_SESSION_KEY)
    if eligibility:
        expires = eligibility["expires"]
        if expires <= time.time():
            session.pop(VSCODE_LAUNCH_SESSION_KEY)
        elif authorized and hmac.compare_digest(eligibility["digest"], digest("vscode-launch:" + query)):
            session.pop(VSCODE_LAUNCH_SESSION_KEY)
            launch = {"marker": digest("vscode-attempt:" + payload["state"]), "expires": expires}
    return render_template("vscode_callback.html", query=query, authorized=authorized, launch=launch)
