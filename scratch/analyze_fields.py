import re
from pathlib import Path

fields_dir = Path("data/extracted/edocs/xml/fields")
pattern = re.compile(
    r"\[\s*'([^']*)'\s*,\s*'(\d+)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'"
)

total_fields = 0
results = []
for html_file in sorted(fields_dir.rglob("*.html")):
    content = html_file.read_text(encoding="utf-8", errors="ignore")
    matches = pattern.findall(content)
    if matches:
        total_fields += len(matches)
        results.append((html_file.name, len(matches)))

print(f"Total files with table-of-fields array: {len(results)}")
print(f"TOTAL STRUCTURED FIELDS IN RECORD PAGES: {total_fields}")
for name, cnt in sorted(results, key=lambda x: -x[1])[:25]:
    print(f"  {name:45}: {cnt} fields")
