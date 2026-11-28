"""Metadata and bounded named placeholders shared by web and API validation."""
import re

LANGUAGES = {
    "python": "Python", "javascript": "JavaScript", "typescript": "TypeScript",
    "html": "HTML", "css": "CSS", "sql": "SQL", "json": "JSON",
    "shellscript": "Shell", "plaintext": "Plain text",
}
LANGUAGE_ALIASES = {"javascriptreact": "javascript", "typescriptreact": "typescript", "shell": "shellscript"}
PLACEHOLDER = re.compile(r"(?<!\{)\{\{[A-Za-z_][A-Za-z0-9_]{0,23}\}\}(?!\})")


def normalize_language(value):
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    value = LANGUAGE_ALIASES.get(value, value)
    return value if value in LANGUAGES else None


def valid_template(code):
    end = count = 0
    for match in PLACEHOLDER.finditer(code):
        literal = code[end:match.start()]
        if "{{" in literal or "}}" in literal or count == 20:
            return False
        end = match.end()
        count += 1
    return count > 0 and "{{" not in code[end:] and "}}" not in code[end:]
