#!/usr/bin/env python3
import json

# Read the file
with open('src/sentinel/agent.py', 'r') as f:
    content = f.read()

# Find the _handle_scripted_fallback method's JavaScript
start_marker = 'js_code = f"""async () => {{'
start_idx = content.find(start_marker)
if start_idx == -1:
    print("Could not find start marker")
    exit(1)

# Find the end - look for the closing braces followed by the evaluate call
# The pattern is }}""" followed by newline and then result = await self._page.evaluate(js_code)
end_marker = '}}"""'
end_idx = content.find(end_marker, start_idx + len(start_marker))
if end_idx == -1:
    print("Could not find end marker")
    exit(1)

# Extract the JavaScript (excluding the f-string wrapper)
js_code = content[start_idx + len('js_code = f"""'):end_idx + 3]

# Print first 300 lines with line numbers
lines = js_code.split('\n')
print(f"Total JavaScript lines: {len(lines)}")
print()

# Find lines with await
for i, line in enumerate(lines, 1):
    if 'await' in line and 'new Promise' in line:
        # Check the context - is this inside an async function?
        # Look backwards for function definitions
        context_start = max(0, i-5)
        context = '\n'.join([f"{j+1}: {lines[j]}" for j in range(context_start, i)])
        print(f"Line {i}: {line.strip()}")
        print(f"Context:\n{context}")
        print("-" * 50)
