import re
from pathlib import Path
from bs4 import BeautifulSoup

file_path = Path("data/extracted/edocs/xml/Fields/LoanRecFields_R.html")
content = file_path.read_text(encoding="utf-8", errors="ignore")

# 1. Extract PowerOn record name
m_pon = re.search(r"PowerOn record name[^<]*:[^<]*<ul[^>]*>\s*<li[^>]*>([^<]+)</li>", content, re.IGNORECASE)
record_name = m_pon.group(1).strip() if m_pon else "LOAN"

# 2. Extract Title and Summary
soup = BeautifulSoup(content[:10000], "lxml")
title = soup.find("h1")
title_text = title.get_text(" ").strip() if title else "Loan Record Fields"
p_desc = soup.find("p", class_="shortDesc")
summary = p_desc.get_text(" ").strip() if p_desc else ""

print(f"Record Name: {record_name}")
print(f"Title: {title_text}")
print(f"Summary: {summary}")

# 3. Extract all fields from dta_ array
pattern = re.compile(
    r"\[\s*'([^']*)'\s*,\s*'(\d+)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'"
)
matches = pattern.findall(content)
print(f"Extracted {len(matches)} fields from dta_ array!")

# Sample first 5
for m in matches[:5]:
    sec_id, order, fld_name, fld_num, mnem, dtype, help_no = m
    print(f"  Field {fld_num}: {fld_name} (Mnemonic: {mnem}, Type: {dtype}, Help: {help_no})")

# Sample specific key fields: LOAN TYPE, LOAN ID, LOAN CODE, INTEREST RATE, PAYMENT, BALANCE
target_mnems = {"TYPE", "ID", "LOANCODE", "INTERESTRATE", "PAYMENT", "BALANCE"}
for m in matches:
    sec_id, order, fld_name, fld_num, mnem, dtype, help_no = m
    if mnem in target_mnems:
        # Extract section description
        pos = content.find(f'id="{sec_id}"')
        desc = ""
        if pos != -1:
            next_pos = content.find('class="section"', pos + 20)
            chunk = content[pos:next_pos] if next_pos != -1 else content[pos:pos+3000]
            desc = re.sub(r"<[^>]+>", " ", chunk)
            desc = re.sub(r"\s+", " ", desc).strip()
        print(f"\n-> Found target {mnem}: {fld_name} (#{fld_num}) [{dtype}]")
        print(f"   Excerpt: {desc[:250]}...")

