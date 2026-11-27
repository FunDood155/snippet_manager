import logging
import os
from datetime import timedelta
from urllib.parse import urlsplit

import psycopg2
from dotenv import load_dotenv
from flask import Flask, abort, g, jsonify, redirect, render_template, request, url_for

import auth
import store

load_dotenv()


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
    app.register_blueprint(auth.bp)
    app.jinja_env.globals["csrf_token"] = auth.csrf_token

    @app.before_request
    def authorize():
        if request.endpoint == "static":
            return
        settings = app.config
        if (len(app.secret_key) < 32 or not settings["SUPABASE_PUBLISHABLE_KEY"]
                or not valid_origin(settings["SUPABASE_URL"], local_http)
                or not valid_origin(settings["SNIPPET_SITE_URL"], local_http)):
            abort(503, "Authentication is unavailable.")
        if request.path.startswith("/api/"):
            g.owner = auth.api_identity()
        elif request.method == "POST":
            auth.protect_form()
        if request.endpoint in {"home", "add", "delete", "account_deletion"}:
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

    @app.get("/")
    def home():
        snippets, categories = store.list_snippets(
            g.owner, request.args.get("search"), request.args.get("category"), include_categories=True,
        )
        return render_template("index.html", snippets=snippets, categories=categories,
                               default_id_min=store.DEFAULT_ID_MIN)

    @app.get("/account/deletion")
    def account_deletion():
        return render_template("account_deletion.html")

    @app.post("/add")
    def add():
        fields, error = snippet_fields(request.form)
        if error:
            abort(400, error)
        store.add_snippet(g.owner, *fields)
        return redirect(url_for("home"), code=303)

    @app.post("/delete/<int:sno>")
    def delete(sno):
        if not valid_id(sno) or not store.delete_snippet(g.owner, sno):
            abort(404)
        return redirect(url_for("home"), code=303)

    @app.get("/api/snippets")
    def get_snippets():
        rows, _ = store.list_snippets(g.owner, request.args.get("search"), request.args.get("category"))
        return jsonify([snippet_json(row) for row in rows])

    @app.get("/api/snippets/<int:sno>")
    def get_snippet(sno):
        row = store.get_snippet(g.owner, sno) if valid_id(sno) else None
        if row is None:
            return jsonify(error="Snippet not found"), 404
        return jsonify(snippet_json(row))

    @app.post("/api/snippets")
    def add_snippet():
        data = request.get_json(silent=True)
        if not data or not isinstance(data, dict):
            return jsonify(error="Request body is required"), 400
        fields, error = snippet_fields(data)
        if error:
            return jsonify(error=error), 400
        sno = store.add_snippet(g.owner, *fields, reject_duplicate=True)
        if sno is None:
            return jsonify(error="Snippet already exists"), 409
        return jsonify(message="Snippet added", **snippet_json((sno, *fields))), 201

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


def valid_id(sno):
    return 0 <= sno <= 2147483647


def snippet_json(row):
    return dict(zip(("sno", "name", "cat", "code"), row))


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
    return fields, None


app = create_app()

if __name__ == "__main__":
    # OAuth callback query strings contain short-lived authorization codes.
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    app.run()
