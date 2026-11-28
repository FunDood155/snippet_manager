import logging
import os
from datetime import timedelta
from urllib.parse import urlsplit

import psycopg2
from dotenv import load_dotenv
from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, url_for

import auth
import store
from snippet_highlighting import highlight
from snippet_metadata import LANGUAGES, normalize_language, valid_template

load_dotenv()

PAGE_SIZE = 40
FRAGMENT_HEADER = "X-Snippo-Fragment"


def valid_origin(value, allow_local_http):
    try:
        url = urlsplit(value)
        return (
            bool(url.hostname) and not url.username and not url.password
            and not (url.path or url.query or url.fragment)
            and (url.scheme == "https" or (
                allow_local_http and url.scheme == "http" and url.hostname in ("localhost", "127.0.0.1", "::1")
            ))
        )
    except ValueError:
        return False


def create_app(config=None):
    app = Flask(__name__)
    local_http = os.getenv("SNIPPET_LOCAL_HTTP") == "1" and not os.getenv("VERCEL")
    app.config.update(
        SECRET_KEY=os.getenv("SNIPPET_SESSION_KEY", ""),
        SUPABASE_URL=os.getenv("SUPABASE_URL", "").rstrip("/"),
        SUPABASE_PUBLISHABLE_KEY=os.getenv("SUPABASE_PUBLISHABLE_KEY", ""),
        SNIPPET_SITE_URL=os.getenv("SNIPPET_SITE_URL", "").rstrip("/"),
        SNIPPET_VSCODE_CLIENT_ID=os.getenv("SNIPPET_VSCODE_CLIENT_ID", ""),
        SESSION_COOKIE_NAME="snippet_session_local" if local_http else "__Host-snippet_session",
        SESSION_COOKIE_SECURE=not local_http,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_REFRESH_EACH_REQUEST=False,
        PERMANENT_SESSION_LIFETIME=timedelta(days=7),
        MAX_CONTENT_LENGTH=1024 * 1024,
    )
    if config:
        app.config.update(config)
    app.json.ensure_ascii = False
    app.register_blueprint(auth.bp)
    app.teardown_request(store.close_request_connection)
    app.jinja_env.globals["csrf_token"] = auth.csrf_token
    app.jinja_env.filters["highlight_snippet"] = highlight
    app.jinja_env.globals["snippet_languages"] = LANGUAGES
    editor_endpoints = {"edit", "duplicate"}
    library_endpoints = {"home", "add", "delete", "hide_default", "restore_default", "restore_defaults",
                         "favorite", "change_categories"} | editor_endpoints

    @app.before_request
    def authorize():
        if request.endpoint == "static":
            return
        vercel_environment = os.getenv("VERCEL_ENV")
        if ((os.getenv("VERCEL") or vercel_environment) and vercel_environment != "production"
                and os.getenv("SNIPPET_ISOLATED_PREVIEW") != "1"):
            abort(503, "This Preview requires an isolated database.")
        settings = app.config
        if (len(app.secret_key) < 32 or not settings["SUPABASE_PUBLISHABLE_KEY"]
                or not valid_origin(settings["SUPABASE_URL"], local_http)
                or not valid_origin(settings["SNIPPET_SITE_URL"], local_http)):
            abort(503, "Authentication is unavailable.")
        if request.path.startswith("/api/"):
            g.owner = auth.api_identity()
        elif request.method == "POST":
            if request.blueprint == "auth":
                request.max_content_length = 16 * 1024
            auth.protect_form()
        if request.endpoint in library_endpoints | {"account_deletion", "recent_web"}:
            g.owner = auth.web_identity()
            if not g.owner:
                return redirect(url_for("auth.login"), code=303)

    @app.after_request
    def private_response(response):
        if request.endpoint != "static":
            response.headers["Cache-Control"] = "no-store"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; style-src 'self'; form-action 'self'; "
                "base-uri 'none'; frame-ancestors 'none'"
            )
            if request.endpoint in {"auth.confirm_email", "auth.reset_password", "auth.vscode_callback"}:
                response.headers["Content-Security-Policy"] += "; script-src 'self'"
            if request.endpoint in library_endpoints:
                response.headers["Content-Security-Policy"] += "; script-src 'self'; img-src 'self'; connect-src 'self'"
                response.vary.add(FRAGMENT_HEADER)
        return response

    @app.errorhandler(auth.AuthError)
    def provider_error(error):
        status = {400: 401, 401: 401, 403: 401, 404: 401, 422: 401, 429: 429}.get(error.status, 503)
        return service_error(status)

    @app.errorhandler(503)
    @app.errorhandler(429)
    def http_service_error(error):
        return service_error(error.code)

    @app.errorhandler(psycopg2.Error)
    def database_error(_error):
        if request.endpoint in library_endpoints and getattr(g, "owner", None):
            draft = request.form if request.method == "POST" and request.endpoint in editor_endpoints | {"add"} else None
            editor = request.endpoint if request.endpoint in editor_endpoints and draft is not None else "add"
            return library_page(draft=draft, error="The library is temporarily unavailable. Try again shortly.",
                                editor=editor, source_id=(request.view_args or {}).get("sno"),
                                unavailable=True, status=503)
        return service_error(503)

    def service_error(status):
        message = {
            401: "Authentication required",
            429: "Too many attempts. Try again later.",
            503: "The service is temporarily unavailable. Try again later.",
        }[status]
        if request.path.startswith("/api/"):
            response = jsonify(error=message)
            if status == 401:
                response.headers["WWW-Authenticate"] = "Bearer"
            return response, status
        return render_template("service_error.html", message=message), status

    def filters():
        search = request.args.get("search", "")
        category = request.args.get("category", "")
        scope = request.args.get("scope", "all")
        selection = {
            "search": search if len(search) <= 256 and "\x00" not in search else "",
            "category": category if "\x00" not in category else "",
            "scope": scope if scope in ("all", "personal", "defaults", "favorites") else "all",
        }
        language = normalize_language(request.args.get("language"))
        if language:
            selection["language"] = language
        sort = request.args.get("sort")
        if sort in store.SNIPPET_ORDERS and sort != "default":
            selection["sort"] = sort
        return selection

    def is_fragment():
        return request.headers.get(FRAGMENT_HEADER) == "library"

    def library_page(draft=None, error=None, unavailable=False, status=200, editor="add",
                     source_id=None, manage=None, reset_page=False, category_change=None):
        selection = filters()
        page = 1 if reset_page else min(2_147_483_647, max(1, request.args.get("page", 1, type=int)))
        snippets, recent, categories, hidden, total, revision = [], [], [], [], 0, None
        manage_categories = request.endpoint == "change_categories" or request.args.get("categories") == "1"
        personal_categories, shared_categories = [], []
        if not unavailable:
            snippets, recent, categories, hidden, total, page, revision = store.library_page(
                g.owner, page, PAGE_SIZE, revision=request.args.get("revision"), **selection)
            if manage_categories:
                personal_categories, shared_categories = store.category_counts(g.owner)
        manage = request.args.get("manage") == "1" if manage is None else manage
        location = url_for("home" if editor == "add" else editor, sno=source_id, **selection,
                           page=page if page > 1 else None, revision=revision if page > 1 else None,
                           manage=1 if manage else None, categories=1 if manage_categories else None,
                           _anchor="hidden-defaults" if manage else None)
        template = "library_fragment.html" if is_fragment() else "index.html"
        return render_template(template, snippets=snippets, recent=recent, categories=categories, total=total,
                               manage_categories=manage_categories, personal_categories=personal_categories,
                               shared_categories=shared_categories, category_change=category_change,
                               page=page, pages=max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE), revision=revision,
                               library_location=location, default_id_min=store.DEFAULT_ID_MIN,
                               selection=selection, hidden=hidden, manage_hidden=manage, draft=draft,
                               error=error, unavailable=unavailable, editor=editor, source_id=source_id), status

    def library_redirect(manage=False):
        if is_fragment():
            return library_page(manage=manage, reset_page=True)
        return redirect(url_for("home", **filters(), manage=1 if manage else None,
                                _anchor="hidden-defaults" if manage else None), code=303)

    @app.get("/")
    def home():
        return library_page()

    @app.get("/account/deletion")
    def account_deletion():
        return render_template("account_deletion.html")

    @app.post("/add")
    def add():
        fields, error = snippet_fields(request.form)
        metadata, error = (None, error) if error else snippet_metadata(request.form, fields[2], web=True)
        if error:
            return library_page(draft=request.form, error=error, status=400)
        try:
            store.add_snippet(g.owner, *fields, **metadata)
        except store.LibraryQuotaExceeded:
            return library_page(draft=request.form, error=QUOTA_MESSAGE, status=409)
        flash("Snippet added.", "library-success")
        return library_redirect()

    @app.post("/delete/<int:sno>")
    def delete(sno):
        if not valid_id(sno) or not store.delete_snippet(g.owner, sno):
            return library_page(error="Personal snippet not found.", status=404)
        flash("Snippet deleted.", "library-success")
        return library_redirect()

    @app.route("/edit/<int:sno>", methods=["GET", "POST"], endpoint="edit")
    @app.route("/duplicate/<int:sno>", methods=["GET", "POST"], endpoint="duplicate")
    def snippet_editor(sno):
        duplicating = request.endpoint == "duplicate"
        if not valid_id(sno) or (not duplicating and sno >= store.DEFAULT_ID_MIN):
            return library_page(error="Snippet not found.", status=404)
        source = store.get_snippet(g.owner, sno, extended=True)
        if source is None:
            return library_page(error="Snippet not found.", status=404)
        _, name, category, original, language, template = source
        if request.method == "GET":
            draft = {"name": name + " (copy)" if duplicating else name, "cat": category, "code": original,
                     "language": language, "template": template}
            return library_page(draft=draft, editor=request.endpoint, source_id=sno)

        fields, error = snippet_fields(request.form)
        metadata, error = (None, error) if error else snippet_metadata(request.form, fields[2], web=True)
        if error:
            return library_page(draft=request.form, editor=request.endpoint, source_id=sno, error=error, status=400)
        name, category, code = fields
        # HTML forms normalize textarea newlines. Keep the original bytes for unchanged code.
        if normal_newlines(code) == normal_newlines(original):
            code = original
        try:
            if duplicating:
                store.add_snippet(g.owner, name, category, code, **metadata)
                flash("Snippet duplicated.", "library-success")
            elif store.edit_snippet(g.owner, sno, name, category, code, **metadata):
                flash("Snippet updated.", "library-success")
            else:
                return library_page(error="Snippet not found.", status=404)
        except store.LibraryQuotaExceeded:
            return library_page(draft=request.form, editor=request.endpoint, source_id=sno,
                                error=QUOTA_MESSAGE, status=409)
        return library_redirect()

    @app.post("/favorites/<int:sno>")
    def favorite(sno):
        action = request.form.get("action")
        if action not in ("add", "remove"):
            return library_page(error="Choose whether to add or remove the favorite.", status=400)
        if not valid_id(sno) or not store.set_favorite(g.owner, sno, favorite=action == "add"):
            return library_page(error="Snippet not found.", status=404)
        flash("Added to favorites." if action == "add" else "Removed from favorites.", "library-success")
        return library_redirect()

    @app.post("/defaults/<int:sno>/hide")
    def hide_default(sno):
        if not store.DEFAULT_ID_MIN <= sno <= 2147483647 or not store.hide_default(g.owner, sno):
            return library_page(error="Shared default not found.", status=404)
        flash("Default hidden. Restore it under Hidden defaults.", "library-success")
        return library_redirect()

    @app.post("/defaults/<int:sno>/restore")
    def restore_default(sno):
        if not store.DEFAULT_ID_MIN <= sno <= 2147483647 or not store.restore_default(g.owner, sno):
            return library_page(error="Shared default not found.", status=404)
        flash("Default restored.", "library-success")
        return library_redirect(manage=True)

    @app.post("/defaults/restore-all")
    def restore_defaults():
        count = store.restore_all_defaults(g.owner)
        flash("All defaults restored." if count else "There are no hidden defaults to restore.",
              "library-success" if count else "library-info")
        return library_redirect(manage=True)

    def record_use(sno):
        return ("", 204) if valid_id(sno) and store.record_recent(g.owner, sno) else ("", 404)

    @app.post("/recent/<int:sno>")
    def recent_web(sno):
        return record_use(sno)

    @app.post("/api/snippets/<int:sno>/recent")
    def recent_api(sno):
        return record_use(sno)

    @app.post("/categories")
    def change_categories():
        raw_ids = request.form.getlist("snippet_ids")
        source = request.form.get("source", "")
        destination = request.form.get("destination", "")
        if (not valid_category(destination) or len(raw_ids) > PAGE_SIZE
                or any(not value.isascii() or not value.isdecimal() or len(value) > 10 for value in raw_ids)
                or (not raw_ids and (not valid_category(source) or source == destination))):
            return library_page(error="Choose personal snippets or a source category and a different destination.", status=400)
        ids = sorted(set(map(int, raw_ids)))
        if len(ids) != len(raw_ids) or any(not 0 < sno < store.DEFAULT_ID_MIN for sno in ids):
            return library_page(error="Select valid personal snippets.", status=400)
        confirmed = request.form.get("confirm") == "1"
        expected = request.form.get("expected", type=int) if confirmed else None
        if confirmed and (expected is None or not 0 < expected <= 2147483647 or (ids and expected != len(ids))):
            return library_page(error="Review the affected snippets again before confirming.", status=400)
        try:
            with store.cursor(g.owner) as cur:
                affected = store.category_targets(cur, g.owner, source, ids, expected, destination)
        except store.LibraryQuotaExceeded:
            return library_page(error=QUOTA_MESSAGE, status=409)
        if not affected or (ids and affected != len(ids)):
            return library_page(error="The selected personal snippets changed. Review and try again.", status=409)
        if confirmed:
            flash(f"Moved {affected} {'snippet' if affected == 1 else 'snippets'}.", "library-success")
            return redirect(url_for("home", categories=1, scope="personal", category=destination), code=303)
        return library_page(category_change=dict(ids=ids, source=source, destination=destination, count=affected))

    @app.get("/api/snippets")
    def get_snippets():
        extended = request.args.get("v") == "2"
        search, category = request.args.get("search"), request.args.get("category")
        if any(value and (len(value) > 256 or "\x00" in value) for value in (search, category)):
            return jsonify(error="Use search and category filters of up to 256 characters."), 400
        after, limit = request.args.get("after"), request.args.get("limit")
        if after is not None or limit is not None:
            after = bounded_integer(after if after is not None else "0", 2147483647)
            limit = bounded_integer(limit if limit is not None else "40", 40)
            if after is None or not limit:
                return jsonify(error="Use an integer after cursor and a limit from 1 to 40."), 400
        auth.limit("library-list", g.owner, 300, None)
        try:
            rows, cursor = store.api_library(
                g.owner, after=after, limit=limit, search=search, category=category, extended=extended,
                language=normalize_language(request.args.get("language")) if extended else None,
            )
        except store.LibraryResponseTooLarge:
            return jsonify(error="The result is too large. Narrow your search or use the web library."), 413
        response = jsonify([snippet_json(row, extended) for row in rows])
        if cursor is not None:
            response.headers["X-Snippo-Next-After"] = str(cursor)
        return response

    @app.get("/api/snippets/<int:sno>")
    def get_snippet(sno):
        extended = request.args.get("v") == "2"
        row = store.get_snippet(g.owner, sno, extended=extended) if valid_id(sno) else None
        if row is None:
            return jsonify(error="Snippet not found"), 404
        return jsonify(snippet_json(row, extended))

    @app.post("/api/snippets")
    def add_snippet():
        data = request.get_json(silent=True)
        if not data or not isinstance(data, dict):
            return jsonify(error="Request body is required"), 400
        fields, error = snippet_fields(data)
        if error:
            return jsonify(error=error), 400
        extended = request.args.get("v") == "2"
        metadata, error = snippet_metadata(data, fields[2]) if extended else ({}, None)
        if error:
            return jsonify(error=error), 400
        try:
            sno = store.add_snippet(g.owner, *fields, reject_duplicate=True, **metadata)
        except store.LibraryQuotaExceeded:
            return jsonify(error=QUOTA_MESSAGE), 422
        if sno is None:
            return jsonify(error="Snippet already exists"), 409
        row = (sno, *fields, metadata.get("language"), metadata.get("template"), None)
        return jsonify(message="Snippet added", **snippet_json(row, extended)), 201

    @app.delete("/api/snippets/<int:sno>")
    def delete_snippet(sno):
        if not valid_id(sno) or not store.delete_snippet(g.owner, sno):
            return jsonify(error="Snippet not found"), 404
        return jsonify(message="Snippet deleted")

    @app.get("/api/session")
    def api_session():
        return jsonify(signedIn=True)

    @app.post("/api/logout")
    def api_logout():
        auth.revoke_vscode_session(g.owner, g.api_session_id)
        return "", 204

    return app


QUOTA_MESSAGE = "Your library storage limit was reached. Delete a personal snippet or reduce its size and try again."


def bounded_integer(value, maximum):
    if len(value) <= 10 and value.isascii() and value.isdecimal():
        number = int(value)
        if number <= maximum:
            return number
    return None


def valid_id(sno):
    return 0 <= sno <= 2147483647


def normal_newlines(value):
    return value.replace("\r\n", "\n").replace("\r", "\n")


def snippet_json(row, extended=False):
    result = dict(zip(("sno", "name", "cat", "code"), row))
    if extended:
        result.update(language=row[4], template=row[5], used_at=row[6].isoformat() if len(row) > 6 and row[6] else None)
    return result


def valid_category(value):
    return bool(value.strip()) and "\x00" not in value


def snippet_metadata(data, code, web=False):
    template = data.get("template", False)
    if web:
        template = template == "on"
    elif not isinstance(template, bool):
        return None, "Template mode must be true or false."
    if template and not valid_template(code):
        return None, "Use 1–20 named placeholders such as {{name}}. Names use letters, digits, or underscores and start with a letter or underscore."
    return {"language": normalize_language(data.get("language")), "template": template}, None


def snippet_fields(data):
    keys = ("name", "cat", "code")
    if any(key not in data for key in keys):
        return None, "name, cat and code are required"
    fields = tuple(data[key] for key in keys)
    if any(not isinstance(value, str) for value in fields):
        return None, "name, cat and code must be strings"
    if any(not value.strip() for value in fields):
        return None, "name, cat and code cannot be empty"
    if any("\x00" in value for value in fields):
        return None, "name, cat and code cannot contain null characters"
    try:
        for value in fields:
            value.encode("utf-8")
    except UnicodeEncodeError:
        return None, "name, cat and code must contain valid text"
    return fields, None


app = create_app()

if __name__ == "__main__":
    # OAuth callback query strings contain short-lived authorization codes.
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    app.run()
