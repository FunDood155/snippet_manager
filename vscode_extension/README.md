# Code Snippet Manager — VS Code Extension

A VS Code extension that lets you access, search, and insert your saved Code Snippet Manager snippets directly inside Visual Studio Code.

The extension communicates with the deployed Code Snippet Manager REST API instead of accessing the database directly.

---

## ✨ Features

- 📋 Show all saved snippets
- 🔍 Search snippets
- 📥 Insert snippets directly into the active editor
- ☁️ Works with the deployed cloud API
- 🔐 Uses HTTPS communication
- ⚡ No local Flask server required for the production extension

---

# 🚀 Commands

Open the VS Code Command Palette:

```text
Ctrl + Shift + P
````

The extension provides three commands:

```text
Code Snippet Manager: Show Snippets

Code Snippet Manager: Search Snippets

Code Snippet Manager: Insert Snippet
```

---

## 📋 Show Snippets

Displays all snippets currently stored in the Code Snippet Manager database.

The extension retrieves the snippets through the REST API and displays them using the VS Code Quick Pick interface.

Example:

```text
Select a snippet...

binary search
algorithms

reverse string
python

two sum
leetcode
```

---

## 🔍 Search Snippets

Allows you to search your snippets directly from VS Code.

Example:

```text
Search snippets...
```

If you search:

```text
binary
```

the extension sends a request to the API:

```http
GET /api/snippets?search=binary
```

Matching snippets are then displayed in VS Code.

---

## 📥 Insert Snippet

Allows you to select a snippet and insert its code directly at the current cursor position.

Flow:

```text
Select snippet
      ↓
Select code
      ↓
Active editor
      ↓
Code inserted at cursor
```

No copy-paste is required.

---

# 🏗️ Architecture

The extension is one component of the larger Code Snippet Manager project.

```text
┌─────────────────────────┐
│      VS Code            │
│      Extension          │
└───────────┬─────────────┘
            │
            │ HTTPS
            ↓
┌─────────────────────────┐
│        Vercel           │
│                         │
│     Flask REST API      │
└───────────┬─────────────┘
            │
            ↓
┌─────────────────────────┐
│       Supabase          │
│      PostgreSQL         │
└─────────────────────────┘
```

The extension **does not connect directly to PostgreSQL**.

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

This keeps the database credentials away from the extension.

---

# 🌐 Production API

The production API is hosted on Vercel.

Base URL:

```text
https://snippet-manager-tan.vercel.app
```

Main snippets endpoint:

```text
https://snippet-manager-tan.vercel.app/api/snippets
```

The extension currently uses this deployed API.

---

# 🔌 API Requests

## Get all snippets

```http
GET /api/snippets
```

Used by:

```text
Show Snippets
Insert Snippet
```

---

## Search snippets

```http
GET /api/snippets?search=<query>
```

Used by:

```text
Search Snippets
```

---

# 📂 Extension Structure

```text
vscode_extension/
│
├── src/
│   ├── extension.ts
│   └── test/
│       └── extension.test.ts
│
├── package.json
├── package-lock.json
├── tsconfig.json
├── .gitignore
├── .vscodeignore
└── README.md
```

### Important files

### `src/extension.ts`

Contains the main extension logic.

It handles:

* Registering commands
* Calling the REST API
* Processing API responses
* Displaying snippets
* Searching snippets
* Inserting code into the active editor

---

### `package.json`

Contains the extension configuration.

It defines:

* Extension name
* Version
* Description
* Main entry point
* Commands
* Activation events
* Scripts
* Dependencies

---

### `tsconfig.json`

TypeScript compiler configuration.

It controls how the TypeScript source code is compiled into JavaScript.

---

### `package-lock.json`

Locks the exact dependency versions installed by npm.

---

### `.vscodeignore`

Controls which files are excluded when creating the VSIX package.

---

# 🛠️ Development Setup

## Requirements

You need:

* Node.js
* npm
* VS Code
* Git

---

## 1. Open the extension folder

Open:

```text
snippet_manager/vscode_extension
```

in VS Code.

---

## 2. Install dependencies

From the extension directory:

```bash
npm install
```

This installs the dependencies listed in `package.json`.

---

## 3. Compile TypeScript

Run:

```bash
npm run compile
```

The TypeScript source is compiled into JavaScript.

The compiled output is placed in:

```text
out/
```

---

# 🧪 Testing the Extension

The extension can be tested using the VS Code Extension Development Host.

After compiling:

```bash
npm run compile
```

Press:

```text
F5
```

VS Code will open a new window:

```text
Extension Development Host
```

This is a separate VS Code instance used for testing the extension.

---

## Test Commands

Inside the Extension Development Host, open:

```text
Ctrl + Shift + P
```

Test:

```text
Code Snippet Manager: Show Snippets
```

Then:

```text
Code Snippet Manager: Search Snippets
```

Then:

```text
Code Snippet Manager: Insert Snippet
```

All three commands should communicate with the production REST API.

---

# 📦 Packaging

The extension can be packaged into a VSIX file.

First compile:

```bash
npm run compile
```

Then package:

```bash
npm run package
```

A file similar to this will be generated:

```text
code-snippet-manager-0.0.1.vsix
```

---

# 📥 Installing the VSIX

To install the packaged extension:

1. Open VS Code
2. Press:

```text
Ctrl + Shift + P
```

3. Search:

```text
Extensions: Install from VSIX...
```

4. Select:

```text
code-snippet-manager-0.0.1.vsix
```

5. Install the extension

---

# 🔄 Development → VSIX Workflow

The normal development workflow is:

```text
Modify extension.ts
        ↓
Save
        ↓
npm run compile
        ↓
F5
        ↓
Test in Extension Development Host
        ↓
Fix / modify if needed
        ↓
npm run compile
        ↓
npm run package
        ↓
Generate .vsix
        ↓
Install VSIX
        ↓
Test in normal VS Code
```

---

# 🌍 Local vs Production

### Earlier development setup

The extension originally communicated with the local Flask server:

```text
VS Code
   ↓
127.0.0.1:5000
   ↓
Local Flask
   ↓
SQLite
```

This required the Flask application to be running on the local computer.

---

### Current production setup

The extension now communicates with:

```text
VS Code
   ↓ HTTPS
Vercel
   ↓
Flask REST API
   ↓
Supabase PostgreSQL
```

Therefore, the production extension does **not** require:

```bash
python main.py
```

to be running locally.

---

# 🔐 Security

The extension does not contain the PostgreSQL database credentials.

The extension only communicates with the public REST API.

Database credentials remain on the backend and are stored using environment variables.

```text
VS Code Extension
       ↓
Public API
       ↓
Backend
       ↓
Private Database Credentials
       ↓
Supabase
```

Never place:

```text
.env
DATABASE_URL
Database passwords
```

inside the extension source code.

---

# 🧠 How the Extension Works

The extension registers commands using the VS Code API.

For example:

```text
Command Palette
      ↓
Command registered by extension.ts
      ↓
fetch()
      ↓
REST API
      ↓
JSON response
      ↓
QuickPick
```

For insertion:

```text
User selects snippet
      ↓
Snippet code retrieved
      ↓
Active Text Editor
      ↓
editor.edit()
      ↓
Code inserted at cursor
```

---

# 🧪 Testing Checklist

Before packaging a new version:

```text
☐ npm install
☐ npm run compile
☐ F5
☐ Show Snippets works
☐ Search Snippets works
☐ Insert Snippet works
☐ Test without local Flask server
☐ npm run package
☐ Install generated VSIX
☐ Test again in normal VS Code
```

---

# 📌 Current Status

```text
Show Snippets       ✅
Search Snippets     ✅
Insert Snippet      ✅

REST API connection ✅
Vercel deployment   ✅
Supabase database   ✅

F5 testing          ✅
VSIX packaging      ✅
Normal VS Code      ✅
```

---

# 🔮 Future Improvements

Possible future features:

* Add snippets directly from VS Code
* Edit snippets from VS Code
* Delete snippets from VS Code
* Better search
* Tags
* Favorites
* Syntax highlighting
* Language detection
* User authentication
* User-specific snippets
* Extension settings
* VS Code Marketplace publishing

---

# 📚 Related Project

This extension is part of the larger:

```text
Code Snippet Manager
```

The complete project contains:

```text
Flask Web Application
        +
REST API
        +
Supabase PostgreSQL
        +
VS Code Extension
        +
Vercel Deployment
```

See the main project README in:

```text
../README.md
```

for the complete architecture, backend, database, deployment, API, Git workflow, and project history.

---

# 👨‍💻 Project Goal

The goal of the extension is to bring the Code Snippet Manager directly into the developer's workflow.

Instead of leaving VS Code to find and copy a frequently used piece of code, snippets can be searched and inserted directly from the editor.

The extension is also a practical implementation of:

```text
TypeScript
VS Code Extension API
REST APIs
HTTP / HTTPS
JSON
Node.js
npm
Git
Cloud Deployment
```

````

### After saving it

Since this is a **new README change**, don't mix it with anything else.

Run:

```bash
git status
````

You should see:

```text
modified: vscode_extension/README.md
```

Then commit it separately:

```bash
git add vscode_extension/README.md
git commit -m "document vscode extension"
git push
```

That gives you a nice separation in your history:

```text
ignore local files
        ↓
connect extension to deployed api
        ↓
update main project readme
        ↓
document vscode extension
```

Much cleaner for your daily-commit habit.
