# Code Snippet Manager

A full-stack code snippet management application built with Flask, PostgreSQL, REST APIs, and a VS Code extension.

The project started as a simple Python snippet manager and gradually evolved into a cloud-connected application with a web interface, REST API, PostgreSQL database, and VS Code integration.

---

## 🚀 Features

### Web Application

- View saved snippets
- Add new snippets
- Search snippets
- Filter snippets by category
- Delete snippets
- Persistent cloud database

### REST API

- Get all snippets
- Get a single snippet
- Search snippets
- Add snippets
- Delete snippets
- JSON-based communication
- Tested using Postman

### VS Code Extension

- Show saved snippets inside VS Code
- Search snippets
- Insert snippets directly into the active editor
- Uses the deployed REST API
- Works without running the Flask server locally

---

# 🏗️ Architecture

The current production architecture is:

```text
                         ┌─────────────────┐
                         │   Web Browser   │
                         └────────┬────────┘
                                  │
                                  ↓
                         ┌─────────────────┐
                         │     Vercel      │
                         │                 │
                         │ Flask Backend   │
                         │ REST API        │
                         └────────┬────────┘
                                  │
                                  ↓
                         ┌─────────────────┐
                         │    Supabase     │
                         │   PostgreSQL    │
                         └─────────────────┘
                                  ↑
                                  │
                         HTTPS API Requests
                                  │
                         ┌─────────────────┐
                         │  VS Code        │
                         │  Extension      │
                         └─────────────────┘
````

The web application and VS Code extension both communicate with the Flask REST API. The API handles communication with the Supabase PostgreSQL database.

The VS Code extension does not access the database directly.

---

# 🧩 Technologies

## Backend

* Python
* Flask
* psycopg2
* REST API

## Frontend

* HTML
* CSS
* Jinja Templates

## Database

* PostgreSQL
* Supabase

## VS Code Extension

* TypeScript
* VS Code Extension API
* Node.js
* npm

## Deployment

* Vercel
* Supabase

## Development / Testing

* VS Code
* Git
* GitHub
* Postman

---

# 📁 Project Structure

```text
snippet_manager/
│
├── static/
│   └── CSS / frontend assets
│
├── templates/
│   └── HTML / Jinja templates
│
├── vscode_extension/
│   ├── src/
│   │   └── extension.ts
│   ├── package.json
│   ├── package-lock.json
│   ├── tsconfig.json
│   ├── .gitignore
│   ├── .vscodeignore
│   └── README.md
│
├── main.py
├── migrate.py
├── requirements.txt
├── .gitignore
├── .env
└── README.md
```

---

# 🐍 Flask Backend

The Flask application is contained in:

```text
main.py
```

It handles:

* Web pages
* REST API routes
* Database communication
* Searching
* Adding snippets
* Deleting snippets
* Returning JSON responses

The backend is deployed on Vercel.

---

# 🌐 REST API

Production API:

```text
https://snippet-manager-tan.vercel.app
```

Main endpoint:

```text
https://snippet-manager-tan.vercel.app/api/snippets
```

## GET all snippets

```http
GET /api/snippets
```

Returns all snippets.

Example:

```json
[
    {
        "sno": 1,
        "name": "binary search",
        "cat": "algorithms",
        "code": "..."
    }
]
```

## GET one snippet

```http
GET /api/snippets/<id>
```

Example:

```text
GET /api/snippets/1
```

## Search snippets

```http
GET /api/snippets?search=<query>
```

Example:

```text
GET /api/snippets?search=binary
```

## Add a snippet

```http
POST /api/snippets
```

Example:

```json
{
    "name": "binary search",
    "cat": "algorithms",
    "code": "def binary_search(arr, target): ..."
}
```

## Delete a snippet

```http
DELETE /api/snippets/<id>
```

Example:

```text
DELETE /api/snippets/1
```

---

# 🗄️ Database

The production application uses:

```text
Supabase PostgreSQL
```

The database stores the snippets used by the web application and VS Code extension.

Conceptually:

```text
snippets
├── sno
├── name
├── cat
└── code
```

---

# 🔄 Database Migration

The project originally used SQLite during development.

The migration script:

```text
migrate.py
```

was used to move the existing data into Supabase PostgreSQL.

Migration flow:

```text
SQLite
  ↓
migrate.py
  ↓
Supabase PostgreSQL
```

The migration was completed and the migrated data was verified through the application and API.

SQLite is no longer used as the production database.

---

# 💻 VS Code Extension

The VS Code extension is located in:

```text
vscode_extension/
```

It provides:

* Show Snippets
* Search Snippets
* Insert Snippet

The extension communicates with the deployed REST API rather than accessing the database directly.

For complete extension documentation, development instructions, testing, and VSIX packaging, see:

```text
vscode_extension/README.md
```

---

# 🔐 Environment Variables

Database credentials are stored using environment variables.

Local development uses:

```text
.env
```

Example:

```env
DATABASE_URL=your_database_connection_string
```

The `.env` file is ignored by Git.

Production database credentials are configured through Vercel environment variables.

### Important

Never commit:

```text
.env
```

to GitHub.

---

# 🔒 Ignored Local Files

The following files are intentionally ignored:

```text
.env
snippets.db
snippets.json
__pycache__/
*.pyc
```

The SQLite and JSON files are local development/backup files and are not used by the production application.

---

# 🧪 API Testing

The REST API was tested using Postman.

Tested operations:

```text
GET all snippets       ✅
GET one snippet        ✅
Search snippets        ✅
POST snippet           ✅
DELETE snippet         ✅
```

The production API was also tested after deployment.

---

# 🚀 Deployment

## Backend

The Flask application is deployed using:

```text
Vercel
```

Production domain:

```text
https://snippet-manager-tan.vercel.app
```

## Database

The production database is hosted using:

```text
Supabase PostgreSQL
```

## VS Code Extension

The extension is packaged as a:

```text
.vsix
```

file and can be installed manually in VS Code.

See:

```text
vscode_extension/README.md
```

for extension-specific instructions.

---

# 🔄 Project Evolution

This project was built incrementally:

```text
V1
Python Terminal Application
        ↓
V2
JSON Persistence
        ↓
V3
SQLite Database
        ↓
V4
Flask Web Application
        ↓
V5
REST API
        ↓
V6
VS Code Extension
        ↓
V7
Supabase PostgreSQL
        ↓
V8
Vercel Deployment
        ↓
Production VS Code Extension
```

Each stage introduced a new concept while keeping the project functional.

---

# 🧠 Why the Architecture Changed

The project originally used local SQLite storage because it was simple, lightweight, and easy to use during development.

For production, the application needed a remotely accessible database so that the website and VS Code extension could access the same data from anywhere.

The database was therefore migrated from:

```text
SQLite
```

to:

```text
Supabase PostgreSQL
```

The Flask REST API was then deployed to:

```text
Vercel
```

This created the current cloud architecture:

```text
Client
  ↓
Vercel
  ↓
Flask REST API
  ↓
Supabase PostgreSQL
```

---

# 📌 Current Status

```text
Flask Website             ✅
Add snippets              ✅
Search snippets           ✅
Filter snippets           ✅
Delete snippets           ✅

REST API                  ✅
GET all                   ✅
GET one                   ✅
Search                    ✅
POST                      ✅
DELETE                    ✅

SQLite → PostgreSQL       ✅
Supabase                  ✅
Vercel deployment         ✅

VS Code Extension         ✅
Show snippets             ✅
Search snippets           ✅
Insert snippets           ✅
Production API connection ✅
VSIX packaging            ✅
```

---

# 🔮 Future Improvements

Possible future improvements:

* User authentication
* User-specific snippets
* Snippet editing
* Creating snippets directly from VS Code
* Updating snippets from VS Code
* Tags
* Favorites
* Syntax highlighting
* Better search
* Language-specific snippets
* Cloud synchronization
* VS Code Marketplace publishing
* API authentication

---

# 🎯 Project Goal

The long-term goal of Code Snippet Manager is to provide a convenient way to store and access reusable code snippets across projects.

The project also serves as a practical learning project covering:

```text
Python
Flask
REST APIs
HTTP
JSON
SQL
SQLite
PostgreSQL
Supabase
TypeScript
VS Code Extension Development
Git
GitHub
Vercel
Cloud Deployment
```

---

# 👨‍💻 Project

**Code Snippet Manager**

A full-stack learning and portfolio project that evolved from a simple Python program into a cloud-connected application with:

```text
Web Application
+
REST API
+
PostgreSQL Database
+
VS Code Extension
+
Cloud Deployment
```
