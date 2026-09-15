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

- Show all snippets inside VS Code
- Search snippets
- Insert snippets directly into the active editor
- Uses the deployed REST API
- Does not require the Flask server to run locally

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

### Production flow

```text
VS Code Extension
       ↓
HTTPS Request
       ↓
Vercel
       ↓
Flask REST API
       ↓
Supabase PostgreSQL
       ↓
JSON Response
       ↓
VS Code Extension
```

---

# 🧩 Technologies

## Backend

* Python
* Flask
* psycopg2
* REST API

## Database

* PostgreSQL
* Supabase

## Frontend

* HTML
* CSS
* Jinja templates

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
│   │
│   ├── src/
│   │   └── extension.ts
│   │
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

Flask handles:

* Web pages
* REST API routes
* Database communication
* Searching
* Adding snippets
* Deleting snippets
* Returning JSON responses

The Flask application is deployed on Vercel.

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

---

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

---

## GET one snippet

```http
GET /api/snippets/<id>
```

Returns a single snippet.

Example:

```text
GET /api/snippets/1
```

---

## Search snippets

```http
GET /api/snippets?search=<query>
```

Example:

```text
GET /api/snippets?search=binary
```

---

## Add a snippet

```http
POST /api/snippets
```

Example JSON:

```json
{
    "name": "binary search",
    "cat": "algorithms",
    "code": "def binary_search(arr, target): ..."
}
```

---

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

The database contains the snippet data used by both the web application and VS Code extension.

Conceptually:

```text
snippets
├── sno
├── name
├── cat
└── code
```

Example:

```text
sno  → 1
name → binary search
cat  → algorithms
code → ...
```

---

# 🔐 Environment Variables

Database credentials are never stored directly in the source code.

Local development uses:

```text
.env
```

Example:

```env
DATABASE_URL=your_database_connection_string
```

The `.env` file is ignored by Git.

The production `DATABASE_URL` is configured directly inside Vercel's environment variables.

### Important

Never commit:

```text
.env
```

to GitHub.

---

# 🔄 Database Migration

The project originally used SQLite during development.

The migration script is:

```text
migrate.py
```

It was used to move the existing SQLite snippet data into Supabase PostgreSQL.

The migration process was:

```text
SQLite
  ↓
migrate.py
  ↓
Supabase PostgreSQL
```

The migration was completed and the migrated data was verified through the application and API.

---

# 💻 VS Code Extension

The VS Code extension is located in:

```text
vscode_extension/
```

Its main source file is:

```text
vscode_extension/src/extension.ts
```

The extension communicates with the production REST API.

It does not directly access the PostgreSQL database.

Instead:

```text
VS Code Extension
       ↓
REST API
       ↓
Flask
       ↓
Supabase PostgreSQL
```

---

# VS Code Commands

Open the VS Code Command Palette:

```text
Ctrl + Shift + P
```

Available commands:

```text
Code Snippet Manager: Show Snippets

Code Snippet Manager: Search Snippets

Code Snippet Manager: Insert Snippet
```

---

## Show Snippets

Retrieves snippets through:

```http
GET /api/snippets
```

The snippets are displayed using VS Code's Quick Pick interface.

---

## Search Snippets

The user enters a search query.

The extension sends:

```http
GET /api/snippets?search=<query>
```

The matching snippets are displayed inside VS Code.

---

## Insert Snippet

The extension retrieves the snippets and displays them in a Quick Pick menu.

After selecting a snippet, its code is inserted at the current cursor position in the active VS Code editor.

---

# 🧪 Testing the Extension

The extension can be tested using the VS Code Extension Development Host.

Open:

```text
vscode_extension/
```

Then install dependencies:

```bash
npm install
```

Compile:

```bash
npm run compile
```

Press:

```text
F5
```

This opens:

```text
Extension Development Host
```

Test:

```text
Code Snippet Manager: Show Snippets
Code Snippet Manager: Search Snippets
Code Snippet Manager: Insert Snippet
```

The extension can be tested without running the local Flask server because it communicates with the deployed API.

---

# 📦 Packaging the VS Code Extension

From:

```text
vscode_extension/
```

Compile:

```bash
npm run compile
```

Package:

```bash
npm run package
```

This creates a VSIX package similar to:

```text
code-snippet-manager-0.0.1.vsix
```

The VSIX can be installed manually through:

```text
Ctrl + Shift + P
```

then:

```text
Extensions: Install from VSIX...
```

---

# 📦 What is a VSIX?

A `.vsix` file is the packaged version of a VS Code extension.

It contains the files required to install and run the extension.

Conceptually:

```text
TypeScript source
       ↓
npm run compile
       ↓
JavaScript output
       ↓
vsce package
       ↓
.vsix
       ↓
Install into VS Code
```

It is similar in concept to a packaged installer for an application, but specifically for VS Code extensions.

---

# 🌍 Production vs Local Development

## Earlier development setup

The extension originally communicated with:

```text
http://127.0.0.1:5000
```

which required the Flask server to be running locally.

The architecture was:

```text
VS Code
   ↓
Local Flask
   ↓
SQLite
```

---

## Current production setup

The extension now communicates with:

```text
https://snippet-manager-tan.vercel.app
```

The architecture is:

```text
VS Code
   ↓ HTTPS
Vercel
   ↓
Flask REST API
   ↓
Supabase PostgreSQL
```

Therefore, the production VS Code extension does not require:

```bash
python main.py
```

to be running on the user's computer.

---

# 🔄 Project Evolution

This project was built incrementally.

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

Each stage introduced a new concept while keeping the existing project functional.

---

# 🧠 Why the Architecture Changed

The project originally used local SQLite storage.

SQLite was useful during development because it is:

* Simple
* Lightweight
* File-based
* Easy to use with Flask

However, the production application needed a remotely accessible database.

The database was therefore migrated from:

```text
SQLite
```

to:

```text
Supabase PostgreSQL
```

The Flask API was then deployed to:

```text
Vercel
```

This allowed the VS Code extension to access the application from anywhere through HTTPS.

---

# 🔒 Files That Should Not Be Committed

The following files are intentionally ignored:

```text
.env
snippets.db
snippets.json
__pycache__/
*.pyc
```

The `.env` file contains sensitive database credentials.

The SQLite and JSON files are local development/backup files and are no longer used as the production database.

---

# 🔧 Git Workflow

The project is developed incrementally using Git.

The general workflow is:

```bash
git status
```

Review changes.

Stage specific files:

```bash
git add <file>
```

Commit:

```bash
git commit -m "description of changes"
```

Push:

```bash
git push
```

The project uses commits to track blocks of small-to-major changes rather than making one huge commit at the end.

---

# 🧪 API Testing

The REST API was tested using Postman.

Tested operations include:

```text
GET all snippets       ✅
GET one snippet        ✅
Search snippets        ✅
POST snippet           ✅
DELETE snippet         ✅
```

The production API was also tested after deployment to Vercel.

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

## Extension

The VS Code extension is packaged as:

```text
.vsix
```

and can be installed manually in VS Code.

---

# 🛠️ Local Development

## Backend

Install Python dependencies:

```bash
python -m pip install -r requirements.txt
```

Make sure `.env` contains:

```env
DATABASE_URL=your_database_connection_string
```

Run Flask locally:

```bash
python main.py
```

The local application normally runs at:

```text
http://127.0.0.1:5000
```

---

## Extension

Move into the extension directory:

```bash
cd vscode_extension
```

Install dependencies:

```bash
npm install
```

Compile:

```bash
npm run compile
```

Run the Extension Development Host:

```text
F5
```

Package:

```bash
npm run package
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
* Snippet categories
* Cloud synchronization
* VS Code Marketplace publishing
* Extension settings
* API authentication

---

# 🎯 Project Goal

The long-term goal of Code Snippet Manager is to provide a convenient way to store and access reusable code snippets across projects.

The VS Code extension brings the snippets directly into the developer's workflow so that frequently used code can be searched and inserted without leaving the editor.

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

A personal full-stack learning and portfolio project that evolved from a simple Python program into a cloud-connected application with:

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
