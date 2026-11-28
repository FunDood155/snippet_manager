"""Return text tokens for Jinja to escape. Snippet source is never executed."""
import re

from pygments.lexers import BashLexer, CssLexer, HtmlLexer, JavascriptLexer, JsonLexer, PythonLexer, SqlLexer, TypeScriptLexer
from pygments.token import Comment, Keyword, Literal, Name, Operator, String

LEXERS = {
    "python": PythonLexer, "py": PythonLexer,
    "javascript": JavascriptLexer, "js": JavascriptLexer,
    "html": HtmlLexer, "css": CssLexer, "sql": SqlLexer, "json": JsonLexer,
}
EXPLICIT_LEXERS = {**LEXERS, "typescript": TypeScriptLexer, "shellscript": BashLexer}
TOKEN_STYLES = (
    (Comment, "comment"), (Keyword, "keyword"), (String, "string"), (Literal, "literal"),
    (Name.Function, "name"), (Name.Builtin, "name"), (Name.Tag, "name"), (Operator, "operator"),
)
PYTHON = re.compile(r'(?m)^[ \t]*(?:def\s+\w+\([^\n]*\):|for\s+\w+\s+in\s+[^\n]+:|except\s+\w+[^\n]*:|print\(["\'])')


def highlight(code, category, language=None):
    if len(code) > 12000:
        return None
    lexer = EXPLICIT_LEXERS.get(language) if language is not None else LEXERS.get(category.strip().casefold())
    if language is None and lexer is None and PYTHON.search(code):
        lexer = PythonLexer
    if lexer is None:
        return None
    return [
        (next((style for group, style in TOKEN_STYLES if kind in group), ""), value)
        for _, kind, value in lexer().get_tokens_unprocessed(code)
    ]
