from flask import Flask, render_template, request, redirect, jsonify
import psycopg2
import os

app = Flask(__name__)

def get_db_connection():
    return psycopg2.connect(os.environ["DATABASE_URL"])

@app.route("/")
def home():
    category = request.args.get("category")
    search = request.args.get("search")

    conn = get_db_connection()
    cursor = conn.cursor()

    if search:
        cursor.execute(
            """
            SELECT * FROM snippets
            WHERE name ILIKE %s OR code ILIKE %s
            """,
            (f"%{search}%", f"%{search}%")
        )
    elif category:
        cursor.execute(
            "SELECT * FROM snippets WHERE cat = %s",
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

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO snippets (name, cat, code) VALUES (%s, %s, %s)",
        (name, cat, code)
    )

    conn.commit()
    conn.close()

    return redirect("/")


@app.route("/delete/<int:sno>", methods=["POST"])
def delete(sno):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM snippets WHERE sno = %s",
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

    conn = get_db_connection()
    cursor = conn.cursor()

    if search:
        cursor.execute(
            """
            SELECT * FROM snippets
            WHERE name ILIKE %s OR code ILIKE %s
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
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM snippets WHERE sno = %s",
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

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM snippets WHERE name = %s",
        (name,)
    )

    if cursor.fetchone():
        conn.close()
        return jsonify({
            "error": "Snippet already exists"
        }), 409

    cursor.execute(
        """
        INSERT INTO snippets (name, cat, code)
        VALUES (%s, %s, %s)
        RETURNING sno
        """,
        (name, cat, code)
    )

    sno = cursor.fetchone()[0]

    conn.commit()
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
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM snippets WHERE sno = %s",
        (sno,)
    )

    if cursor.fetchone() is None:
        conn.close()
        return jsonify({
            "error": "Snippet not found"
        }), 404

    cursor.execute(
        "DELETE FROM snippets WHERE sno = %s",
        (sno,)
    )

    conn.commit()
    conn.close()

    return jsonify({
        "message": "Snippet deleted"
    }), 200


app.run(debug=True)