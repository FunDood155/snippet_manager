# Changelog

## 1.1.1

- Preserve a selected-code save while the same Snippo session renews. Stop when the server or account changes and distinguish that case from an unconfirmed save.
- Add configurable editor chords for Show, Search, Insert, and Save Selected Code. The palette reports invalid selections.

## 1.1.0

- Save explicitly selected code from the editor with a name, category and optional language.
- Show recent successful uses and language labels in the picker.
- Insert opt-in named placeholders with native VS Code tab stops.

## 1.0.1

- Shows a cancellable loading picker while Show, Search, and Insert fetch authorized snippets.
- Shares equivalent overlapping requests and discards results when the session or server changes.

## 1.0.0 — Release candidate

- Introduces Snippo under the `dineshkaarthik.snippo-code-snippets` extension ID.
- Uses the existing Snippet Manager account and private snippet library for Show, Search, and Insert commands.
- Updates the browser handoff for VS Code Desktop and Insiders and retains persistent sign-in, token renewal, and sign-out.
- Adds installation, service dependency, and data-handling documentation.

Uninstall earlier Snippo private-test builds or the original Code Snippet Manager extension, then reload VS Code and sign in again after installing Snippo. Your existing account and snippets remain available.
