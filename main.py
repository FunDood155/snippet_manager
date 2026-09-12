from flask import Flask, render_template, request, redirect, jsonify
import sqlite3

app = Flask(__name__)


@app.route("/")
def home():
    category = request.args.get("category")
    search = request.args.get("search")

    conn = sqlite3.connect("snippets.db")
    cursor = conn.cursor()

    if search:
        cursor.execute(
            """
            SELECT * FROM snippets
            WHERE name LIKE ? OR code LIKE ?
            """,
            (f"%{search}%", f"%{search}%")
        )
    elif category:
        cursor.execute(
            "SELECT * FROM snippets WHERE cat = ?",
            (category,)
        )
    else:
        cursor.execute("SELECT * FROM snippets")

    snippets = cursor.fetchall()

    cursor.execute("SELECT DISTINCT cat FROM snippets")
    categories = cursor.fetchall()

    conn.close()

    return render_template(
        "index.html",
        snippets=snippets,
        categories=categories
    )


@app.route("/add", methods=["POST"])
def add():
    name = request.form["name"]
    cat = request.form["cat"]
    code = request.form["code"]

    conn = sqlite3.connect("snippets.db")
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO snippets (name, cat, code) VALUES (?, ?, ?)",
        (name, cat, code)
    )

    conn.commit()
    conn.close()

    return redirect("/")


@app.route("/delete/<int:sno>", methods=["POST"])
def delete(sno):
    conn = sqlite3.connect("snippets.db")
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM snippets WHERE sno = ?",
        (sno,)
    )

    conn.commit()
    conn.close()

    return redirect("/")


# ==================== V5 API ====================


# V5.1 - Get all snippets
@app.route("/api/snippets", methods=["GET"])
def get_snippets():
    search = request.args.get("search")

    conn = sqlite3.connect("snippets.db")
    cursor = conn.cursor()

    if search:
        cursor.execute(
            """
            SELECT * FROM snippets
            WHERE name LIKE ? OR code LIKE ?
            """,
            (f"%{search}%", f"%{search}%")
        )
    else:
        cursor.execute("SELECT * FROM snippets")

    snippets = cursor.fetchall()

    conn.close()

    result = []

    for snippet in snippets:
        result.append({
            "sno": snippet[0],
            "name": snippet[1],
            "cat": snippet[2],
            "code": snippet[3]
        })

    return jsonify(result)


# V5.2 - Get one snippet
@app.route("/api/snippets/<int:sno>", methods=["GET"])
def get_snippet(sno):
    conn = sqlite3.connect("snippets.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM snippets WHERE sno = ?",
        (sno,)
    )

    snippet = cursor.fetchone()

    conn.close()

    if snippet is None:
        return jsonify({"error": "Snippet not found"}), 404

    result = {
        "sno": snippet[0],
        "name": snippet[1],
        "cat": snippet[2],
        "code": snippet[3]
    }

    return jsonify(result)


# V5.3 + V5.6 - Add snippet with validation
@app.route("/api/snippets", methods=["POST"])
def add_snippet():
    data = request.get_json()

    if not data:
        return jsonify({
            "error": "Request body is required"
        }), 400

    if "name" not in data or "cat" not in data or "code" not in data:
        return jsonify({
            "error": "name, cat and code are required"
        }), 400

    name = data["name"]
    cat = data["cat"]
    code = data["code"]

    if not isinstance(name, str) or not isinstance(cat, str) or not isinstance(code, str):
        return jsonify({
            "error": "name, cat and code must be strings"
        }), 400

    if not name.strip() or not cat.strip() or not code.strip():
        return jsonify({
            "error": "name, cat and code cannot be empty"
        }), 400

    conn = sqlite3.connect("snippets.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM snippets WHERE name = ?",
        (name,)
    )

    if cursor.fetchone():
        conn.close()
        return jsonify({
            "error": "Snippet already exists"
        }), 409

    cursor.execute(
        "INSERT INTO snippets (name, cat, code) VALUES (?, ?, ?)",
        (name, cat, code)
    )

    conn.commit()

    sno = cursor.lastrowid

    conn.close()

    return jsonify({
        "message": "Snippet added",
        "sno": sno,
        "name": name,
        "cat": cat,
        "code": code
    }), 201


# V5.4 - Delete snippet
@app.route("/api/snippets/<int:sno>", methods=["DELETE"])
def delete_snippet(sno):
    conn = sqlite3.connect("snippets.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM snippets WHERE sno = ?",
        (sno,)
    )

    if cursor.fetchone() is None:
        conn.close()
        return jsonify({
            "error": "Snippet not found"
        }), 404

    cursor.execute(
        "DELETE FROM snippets WHERE sno = ?",
        (sno,)
    )

    conn.commit()
    conn.close()

    return jsonify({
        "message": "Snippet deleted"
    }), 200


app.run(debug=True)