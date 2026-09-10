from flask import Flask, render_template, request, redirect
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

app.run(debug=True)