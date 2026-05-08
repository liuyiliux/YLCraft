from pathlib import Path
import re
import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger()

TOOLS_DIR = Path('app/services/agent/tools')

def remove_parameters_block(content: str) -> tuple[str, int]:
    """Remove parameters={...}, block before category= using brace counting."""
    result = []
    total_fixes = 0
    i = 0
    while i < len(content):
        # Find parameters={
        idx = content.find('parameters={', i)
        if idx == -1:
            result.append(content[i:])
            break

        # Append everything before parameters={
        result.append(content[i:idx])

        # Skip the parameters={...} block using brace counting
        j = idx + len('parameters={')
        depth = 1
        while j < len(content) and depth > 0:
            c = content[j]
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
            j += 1

        # Now content[j] is the character after the closing }
        # Skip whitespace + newline, find category=
        rest = content[j:]
        m = re.search(r'\n(\s+)category=', rest)
        if m:
            # Keep the newline + indent + category=
            indent = m.group(1)
            j = j + m.start() + 1  # include the newline
            result.append(f'\n{indent}category=')
            total_fixes += 1
        else:
            # No category= found, append rest as-is
            result.append(rest)
            break

        i = j + (m.end() - m.start() if m else 0)

    return ''.join(result), total_fixes

def main():
    total = 0
    for py_file in sorted(TOOLS_DIR.glob('*.py')):
        if py_file.name == '__init__.py':
            continue
        with open(py_file, 'r', encoding='utf-8') as f:
            content = f.read()

        new_content, n = remove_parameters_block(content)
        if n > 0:
            with open(py_file, 'w', encoding='utf-8') as f:
                f.write(new_content)
            logger.info(f'  Fixed {py_file.name}: {n} occurrence(s)')
            total += n
        else:
            logger.info(f'  Skipped {py_file.name}: no parameters block')

    logger.info(f'Total: {total} fix(es) applied')

main()
