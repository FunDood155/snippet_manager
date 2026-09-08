import sqlite3


# Connect to database
conn = sqlite3.connect("snippets.db")
cursor = conn.cursor()


# Create table
cursor.execute("""
CREATE TABLE IF NOT EXISTS snippets (
    sno INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    cat TEXT,
    code TEXT
)
""")

conn.commit()


def add():
    name = input("Enter snippet name : ")
    cat = input("Enter snippet category : ")
    code = input("Enter snippet content : ")

    cursor.execute(
        "SELECT * FROM snippets WHERE name = ?",
        (name,)
    )

    if cursor.fetchone():
        print("Snippet already exists")
    else:
        cursor.execute(
            "INSERT INTO snippets (name, cat, code) VALUES (?, ?, ?)",
            (name, cat, code)
        )
        conn.commit()
        print("Snippet added")


def remove():
    x = input("Which snippet u wanna remove : ")

    cursor.execute(
        "SELECT * FROM snippets WHERE name = ?",
        (x,)
    )

    if cursor.fetchone():
        cursor.execute(
            "DELETE FROM snippets WHERE name = ?",
            (x,)
        )
        conn.commit()
        print("Snippet ", x, " removed")
    else:
        print("Snippet not found")


def display():
    cursor.execute("SELECT * FROM snippets")

    snippets = cursor.fetchall()

    for i in snippets:
        print("Sno  : ", i[0])
        print("Name : ", i[1])
        print("Cat  : ", i[2])
        print("Code : ", i[3])
        print()


def show_category():
    cursor.execute("SELECT DISTINCT cat FROM snippets")

    categories = cursor.fetchall()

    for cat in categories:
        print(cat[0])


def show_snippets():
    cursor.execute("SELECT name FROM snippets")

    snippets = cursor.fetchall()

    for i in snippets:
        print(i[0])


print("1.Add")
print("2.Remove")
print("3.Display")
print("4.Show all category")
print("5.Show all snippets")

ch = True
while ch:
    ch = input("Enter ur choice : ")
    if ch == '1':
        add()
    elif ch == '2':
        remove()
    elif ch == '3':
        display()
    elif ch == '4':
        show_category()
    elif ch == '5':
        show_snippets()
    else:
        break

conn.close()