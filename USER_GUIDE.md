# Code Snippet Manager — Beginner User Guide

## 1. What is this project?

Imagine you're learning Python and you keep writing useful pieces of code:

```python
# Binary Search
def binary_search(arr, target):
    ...
````

Then later you need that code again.

Normally you might:

* search through old `.py` files
* search Google
* keep a huge `notes.txt`
* copy code from somewhere
* forget where you saved it 😭

**Code Snippet Manager gives you one place to save useful pieces of code and quickly retrieve them.**

It has two main ways to use your snippets:

```text
                    Code Snippet Manager
                           │
             ┌─────────────┴─────────────┐
             ↓                           ↓
       Web Application              VS Code Extension
       Manage snippets              Use snippets while coding
             │                           │
             └─────────────┬─────────────┘
                           ↓
                    Cloud Database
```

The website is mainly for **managing your snippets**.

The VS Code extension is mainly for **finding and using them while coding**.

---

# 2. Do I need to know Computer Science?

**No.**

You don't need to understand:

* Flask
* PostgreSQL
* REST APIs
* Vercel
* Supabase
* TypeScript

to use the project.

Those are the technologies working behind the scenes.

As a normal user, you mainly need:

```text
VS Code
+
Code Snippet Manager extension
```

That's it.

---

# 3. What is a snippet?

A snippet is simply a **small piece of reusable code**.

For example:

### Python — Read a file

```python
with open("data.txt", "r") as file:
    data = file.read()
```

### Python — Reverse a string

```python
text = "hello"
reversed_text = text[::-1]
```

### Python — Binary Search

```python
def binary_search(arr, target):
    left = 0
    right = len(arr) - 1

    while left <= right:
        mid = (left + right) // 2

        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1

    return -1
```

Instead of keeping useful code scattered across your computer, you can store it in Code Snippet Manager.

---

# 4. What can I do with it?

The project currently provides two interfaces.

## Website

The website lets you:

```text
View snippets
Add snippets
Search snippets
Filter by category
Delete snippets
```

## VS Code Extension

The extension lets you:

```text
Show snippets
Search snippets
Insert snippets directly into VS Code
```

A simple way to remember it:

```text
Website
   ↓
Manage your snippets

VS Code Extension
   ↓
Use your snippets while coding
```

---

# 5. Installing the VS Code Extension

You don't need to install Python, Flask, PostgreSQL, Node.js, or anything else just to use the extension.

You only need:

```text
VS Code
+
the Code Snippet Manager .vsix file
```

A `.vsix` file is the installable package for a VS Code extension.

It will look something like:

```text
code-snippet-manager-0.0.1.vsix
```

---

## Step 1 — Get the VSIX

Obtain the latest `.vsix` package for Code Snippet Manager.

Keep the file somewhere easy to find, such as:

```text
Downloads/
```

---

## Step 2 — Open VS Code

Open:

```text
VS Code
```

Press:

```text
Ctrl + Shift + P
```

This opens the **Command Palette**.

Search for:

```text
Extensions: Install from VSIX...
```

Select it.

---

## Step 3 — Select the VSIX

Find:

```text
code-snippet-manager-0.0.1.vsix
```

and select it.

VS Code will install the extension.

If VS Code asks you to reload, allow it.

---

# 6. How do I know the extension installed correctly?

Open the Command Palette:

```text
Ctrl + Shift + P
```

Search for:

```text
Code Snippet Manager
```

You should see:

```text
Code Snippet Manager: Show Snippets

Code Snippet Manager: Search Snippets

Code Snippet Manager: Insert Snippet
```

If you can see these commands, the extension is installed.

---

# 7. Your first use

Let's say the database already contains:

```text
Binary Search
Two Sum
Palindrome Check
File Reading
BFS
DFS
```

Open VS Code and press:

```text
Ctrl + Shift + P
```

Then search:

```text
Code Snippet Manager: Show Snippets
```

You should get a selection menu containing your snippets.

For example:

```text
Select a snippet...

> Binary Search
  Two Sum
  Palindrome Check
  File Reading
  BFS
  DFS
```

Select a snippet to view it.

---

# 8. Searching for a snippet

This becomes much more useful when you have lots of snippets.

Open:

```text
Ctrl + Shift + P
```

Run:

```text
Code Snippet Manager: Search Snippets
```

You will see:

```text
Search snippets...
```

Suppose you type:

```text
binary
```

The extension searches the available snippets and displays matching results.

For example:

```text
Search results

> Binary Search
```

So instead of scrolling through hundreds of snippets:

```text
Search
   ↓
Find
   ↓
Use
```

---

# 9. Inserting a snippet ⭐

This is one of the main reasons to use the extension.

Suppose you're writing Python:

```python
def solve():
    |
```

Your cursor is at:

```text
|
```

Open:

```text
Ctrl + Shift + P
```

Run:

```text
Code Snippet Manager: Insert Snippet
```

Select:

```text
Binary Search
```

The extension inserts the saved code at your cursor.

For example:

```python
def solve():
    def binary_search(arr, target):
        left = 0
        right = len(arr) - 1

        while left <= right:
            mid = (left + right) // 2

            if arr[mid] == target:
                return mid
            elif arr[mid] < target:
                left = mid + 1
            else:
                right = mid - 1

        return -1
```

You don't need to:

```text
Open browser
    ↓
Search for code
    ↓
Copy
    ↓
Switch back to VS Code
    ↓
Paste
```

You can find and insert it directly from VS Code.

---

# 10. Using the website

The web application is useful when you want to manage your collection.

You can:

```text
Add a snippet
     ↓
Give it a name
     ↓
Choose a category
     ↓
Save the code
```

You can then:

```text
Search snippets
Filter by category
View snippets
Delete snippets
```

The snippets managed through the website are also available to the VS Code extension because both use the same cloud backend.

---

# 11. Website vs VS Code Extension

You can think of the two interfaces like this:

| Feature                     | Website | VS Code Extension |
| --------------------------- | ------- | ----------------- |
| View snippets               | ✅       | ✅                 |
| Add snippets                | ✅       | ❌                 |
| Search snippets             | ✅       | ✅                 |
| Filter by category          | ✅       | —                 |
| Delete snippets             | ✅       | ❌                 |
| Insert directly into editor | ❌       | ✅                 |

### Simple rule

Use the **website** when you want to:

```text
Manage your collection
```

Use the **VS Code extension** when you want to:

```text
Find and use your snippets while coding
```

---

# 12. Do I need the Flask server running?

**No.**

This is an important part of the current version.

The older version of the project worked locally:

```text
VS Code
   ↓
Local Flask
   ↓
SQLite
```

That meant the Flask server had to be running on your computer.

The current version uses the cloud:

```text
VS Code
   ↓
Internet
   ↓
Vercel
   ↓
Flask REST API
   ↓
Supabase PostgreSQL
```

Therefore, as a normal user:

**you do not need to run:**

```bash
python main.py
```

You don't need to start a local database either.

The extension communicates with the deployed application automatically.

---

# 13. Where are my snippets stored?

Your snippets are stored in the project's **cloud PostgreSQL database**.

They are not stored inside VS Code.

The basic flow is:

```text
You
 ↓
VS Code Extension
 ↓
Internet / HTTPS
 ↓
REST API
 ↓
Cloud Database
```

This means your snippets are available through the cloud rather than being tied to one local file such as:

```text
snippets.json
```

or:

```text
snippets.db
```

---

# 14. Do I need to understand the cloud/database?

**No.**

You may see terms such as:

```text
PostgreSQL
Supabase
Vercel
Flask
REST API
```

These describe how the application works internally.

As a user, you can simply think:

```text
My snippets
      ↓
Cloud
      ↓
Available through the app
```

---

# 15. A realistic example for a student

Imagine you're learning Python.

Over several months you learn:

```text
Week 1
String reversal

Week 2
Lists

Week 3
Dictionaries

Week 4
Binary Search

Week 5
Sorting

Week 6
File Handling

Week 7
OOP

Week 8
Recursion
```

Whenever you find a useful piece of code, save it.

Eventually you might have:

```text
Algorithms
├── Binary Search
├── BFS
├── DFS
├── Two Sum
└── Merge Sort

Python
├── Read File
├── Write File
├── Dictionary Counter
└── List Comprehension
```

Then months later:

> "Wait, how did I write that BFS code?"

Instead of searching your entire computer:

```text
Ctrl + Shift + P
        ↓
Search Snippets
        ↓
BFS
        ↓
Found
```

Or:

```text
Insert Snippet
      ↓
BFS
      ↓
Code appears in editor
```

---

# 16. Why is this useful for someone learning programming?

There are two benefits.

## As a tool

It helps you:

```text
Organize useful code
        ↓
Find it quickly
        ↓
Reuse it
        ↓
Avoid repetitive searching
```

## As a learning project

The project itself demonstrates how a simple program can gradually become a real application.

It evolved from:

```text
Python program
```

into:

```text
Python
   ↓
JSON
   ↓
SQLite
   ↓
Flask
   ↓
REST API
   ↓
PostgreSQL
   ↓
Cloud deployment
   ↓
VS Code Extension
```

You don't need to learn all of these technologies at once.

They are simply the technologies that make the application work.

---

# 17. If I'm learning Python, how should I use it?

Use it as your personal programming toolbox.

For example, you learn:

```python
def factorial(n):
    if n == 0:
        return 1
    return n * factorial(n - 1)
```

Instead of throwing it away after solving an exercise:

```text
Understand it
     ↓
Save it
     ↓
Give it a useful name
     ↓
Choose a category
```

Later:

```text
You're solving a problem
        ↓
Need factorial logic
        ↓
Open VS Code
        ↓
Search Snippets
        ↓
factorial
        ↓
Insert
```

---

# 18. Don't use it as a replacement for learning

This is important if you're a beginner.

Don't turn the project into a place where you save everything just so you never have to understand it.

The goal should be:

```text
Learn
 ↓
Understand
 ↓
Save useful/reusable code
 ↓
Reuse later
```

For example, if you're learning binary search, don't just save the implementation.

Also understand:

```text
Why binary search works
When it can be used
What its time complexity is
```

Then the saved snippet becomes a useful reference rather than a replacement for learning.

---

# 19. When will this become more useful?

The usefulness increases as your collection grows.

```text
10 snippets
→ Nice

50 snippets
→ Useful

100+ snippets
→ Very useful

Several hundred snippets
→ Search becomes extremely valuable
```

The more useful code you collect, the more valuable quick search and insertion become.

---

# 20. A simple beginner workflow

A good workflow is:

```text
Learn something
      ↓
Understand it
      ↓
Write/use the code
      ↓
Decide if it is worth keeping
      ↓
Save it in Code Snippet Manager
      ↓
Give it a useful name/category
      ↓
Continue learning
```

Later:

```text
Need the code again
      ↓
Open VS Code
      ↓
Search Snippets
      ↓
Find it
      ↓
Insert it
      ↓
Continue coding
```

---

# 21. Simplest way to understand the whole project

If all the technical terms are confusing, forget Flask, PostgreSQL, REST, Vercel, etc.

Think of it like this:

```text
                  YOUR SNIPPETS
                       │
          ┌────────────┴────────────┐
          ↓                         ↓
       WEBSITE                  VS CODE
     Manage them                Use them
          │                         │
          └────────────┬────────────┘
                       ↓
                  CLOUD STORAGE
```

The website helps you **manage** your snippets.

The VS Code extension helps you **use** your snippets.

The cloud keeps the data available to both.

---

# 22. Is it useful enough to keep installed?

For someone who regularly uses VS Code to learn or program:

**Yes — especially once you build up a decent collection of snippets.**

The main advantage is that your useful code is no longer scattered across:

```text
Old Python files
Notes
Text files
Browser bookmarks
Random folders
```

Instead, you have one searchable collection.

And the **Insert Snippet** feature means you can use those snippets without leaving VS Code.

---

# 23. Quick Start

If you just want the shortest possible instructions:

```text
1. Install VS Code
        ↓
2. Get the Code Snippet Manager .vsix
        ↓
3. Open VS Code
        ↓
4. Ctrl + Shift + P
        ↓
5. Extensions: Install from VSIX...
        ↓
6. Select the .vsix file
        ↓
7. Reload VS Code if asked
        ↓
8. Ctrl + Shift + P
        ↓
9. Search "Code Snippet Manager"
        ↓
10. Use Show / Search / Insert
```

You do **not** need to:

```text
Install Flask
Install PostgreSQL
Install Supabase
Run Python
Run a local server
Run a local database
```

for normal use of the extension.

---

# TL;DR

As a student, your workflow is simply:

```text
1. Learn something
       ↓
2. Write useful code
       ↓
3. Save it in Code Snippet Manager
       ↓
4. Later open VS Code
       ↓
5. Search for it
       ↓
6. Insert it directly into your code
```

**Install the VSIX → open VS Code → use the three commands.**

The cloud/API/database side happens behind the scenes.

You can focus on learning and coding instead of worrying about how the application stores and retrieves the snippets.

````

### One thing I'd definitely change from your original

I would **not call it `README2.md`**.

Use:

```text
USER_GUIDE.md
````

Your repository would then look clean:

```text
snippet_manager/
│
├── README.md              ← Project / developer documentation
├── USER_GUIDE.md          ← Beginner user guide
│
├── main.py
├── migrate.py
├── requirements.txt
│
└── vscode_extension/
    └── README.md          ← Extension-specific documentation
```