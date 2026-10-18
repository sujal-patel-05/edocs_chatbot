import re
from pathlib import Path
from typing import List
from bs4 import BeautifulSoup

def extract_all_fields_from_html(
    doc_id: str,
    release: str,
    html: str,
    title: str = "",
    breadcrumbs: list[str] | None = None,
) -> list[dict]:
    records: list[dict] = []

    # 1. Check for var dta_ array (Symitar Table of Fields)
    if "var dta_" in html:
        # Extract PowerOn record name
        m_pon = re.search(
            r"PowerOn record name[^<]*:[^<]*<ul[^>]*>\s*<li[^>]*>([^<]+)</li>",
            html,
            re.IGNORECASE,
        )
        if m_pon:
            record_name = m_pon.group(1).strip()
        else:
            # Fallback from title: e.g. "Loan Record Fields" -> "LOAN"
            clean_title = title.replace("Record Fields", "").replace("Fields", "").strip()
            record_name = clean_title.upper() if clean_title else "GENERAL"

        # Regex to extract items in dta_
        pattern = re.compile(
            r"\[\s*'([^']*)'\s*,\s*'(\d+)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*'([^']*)'"
        )
        matches = pattern.findall(html)

        # Index section positions for fast lookups without parsing 1.5MB DOM repeatedly
        sec_pattern = re.compile(r'id=["\']([^"\']+)["\']')

        for sec_id, order, fld_name, fld_num, mnem, dtype, help_no in matches:
            if not fld_name or fld_name == "&nbsp;":
                continue

            # Look up section text in html
            desc = ""
            source = None
            default_val = None
            default_ctrl = None
            sym_mnem = None

            pos = html.find(f'id="{sec_id}"')
            if pos != -1:
                # Get chunk until next section
                next_pos = html.find('class="section"', pos + 25)
                sec_chunk = html[pos:next_pos] if next_pos != -1 else html[pos:pos+4000]

                # Extract paragraph description
                p_m = re.search(r'<p[^>]*>(.*?)</p>', sec_chunk, re.DOTALL)
                if p_m:
                    desc_text = re.sub(r'<[^>]+>', ' ', p_m.group(1))
                    desc = re.sub(r'\s+', ' ', desc_text).strip()

                # Extract table key-values if present in section
                for tr_m in re.finditer(r'<tr[^>]*>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>(.*?)</td>\s*</tr>', sec_chunk, re.DOTALL):
                    lbl = re.sub(r'<[^>]+>', ' ', tr_m.group(1)).strip().lower()
                    val = re.sub(r'<[^>]+>', ' ', tr_m.group(2)).strip()
                    if "source" in lbl:
                        source = val
                    elif "default value" in lbl:
                        default_val = val
                    elif "default control" in lbl:
                        default_ctrl = val
                    elif "symxchange" in lbl:
                        sym_mnem = val

            clean_mnem = None if mnem in ("N/A", "None", "") else mnem
            clean_num = None if fld_num in ("N/A", "None", "") else fld_num
            clean_help = None if help_no in ("N/A", "None", "") else help_no

            records.append({
                "release": release,
                "record": record_name,
                "field_name": fld_name.strip(),
                "field_number": clean_num,
                "poweron_mnemonic": clean_mnem,
                "symxchange_mnemonic": sym_mnem,
                "data_type": dtype.strip() if dtype else None,
                "source": source,
                "help_file": clean_help,
                "default_control": default_ctrl,
                "default_value": default_val,
                "description": desc or fld_name.strip(),
                "doc_id": doc_id,
            })

    return records

# Test on LoanRecFields_R.html
loan_file = Path("data/extracted/edocs/xml/Fields/LoanRecFields_R.html")
loan_html = loan_file.read_text(encoding="utf-8", errors="ignore")
loan_fields = extract_all_fields_from_html(
    doc_id="edocs/xml/fields/loanrecfields_r.html",
    release="2023.00",
    html=loan_html,
    title="Loan Record Fields",
)

print(f"Extracted {len(loan_fields)} fields from LoanRecFields_R.html!")
for f in loan_fields[:10]:
    print(f"  Field #{f['field_number']}: {f['field_name']} | Mnem: {f['poweron_mnemonic']} | Type: {f['data_type']} | Source: {f['source']}")
    print(f"    Desc: {f['description'][:100]}...\n")
