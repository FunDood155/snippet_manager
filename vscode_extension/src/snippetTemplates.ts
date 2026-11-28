type Part = { text: string } | { name: string };

// Only paired ASCII identifiers are interpreted. VS Code escapes the literal parts.
export function templateParts(code: string): Part[] | undefined {
    const parts: Part[] = [];
    let end = 0;
    let count = 0;
    for (const match of code.matchAll(/(?<!\{)\{\{([A-Za-z_][A-Za-z0-9_]{0,23})\}\}(?!\})/g)) {
        const text = code.slice(end, match.index);
        if (text.includes('{{') || text.includes('}}') || ++count > 20) return;
        parts.push({ text }, { name: match[1] });
        end = match.index + match[0].length;
    }
    const text = code.slice(end);
    if (!count || text.includes('{{') || text.includes('}}')) return;
    return [...parts, { text }];
}

export function buildTemplate(code: string, builder: {
    appendText(text: string): unknown;
    appendPlaceholder(name: string, number: number): unknown;
    appendTabstop(number: number): unknown;
}): boolean {
    const parts = templateParts(code);
    if (!parts) return false;
    const fields = new Map<string, number>();
    for (const part of parts) {
        if ('text' in part) {
            builder.appendText(part.text);
        } else {
            const number = fields.get(part.name) ?? fields.size + 1;
            fields.set(part.name, number);
            builder.appendPlaceholder(part.name, number);
        }
    }
    builder.appendTabstop(0);
    return true;
}
