# Code Snippet Manager

A VS Code extension that connects to a Flask REST API to manage and insert code snippets directly into the editor.

## Features

- Show all saved snippets
- Search snippets
- Insert snippets directly at the cursor
- Uses a Flask REST API
- Uses SQLite for persistent storage

## Commands

- `Code Snippet Manager: Show Snippets`
- `Code Snippet Manager: Search Snippets`
- `Code Snippet Manager: Insert Snippet`

## Architecture

```text
VS Code Extension
        ↓
     Flask API
        ↓
     SQLite