import os
import re
from markdown_pdf import MarkdownPdf, Section

def build_toc(markdown_text):
    lines = markdown_text.split("\n")
    toc_lines = ["# Table of Contents\n"]
    for line in lines:
        if line.startswith("##"):
            level = len(line) - len(line.lstrip("#"))
            title = line.strip("#").strip()
            indent = "&nbsp;&nbsp;&nbsp;&nbsp;" * (level - 2)
            toc_lines.append(f"{indent}- {title}<br>")
    return "\n".join(toc_lines)

def fix_bullets(text):
    """Replace markdown lists with escaped hyphens and two trailing spaces for manual newlines,
    preventing markdown-pdf from using the unsupported standard bullet character."""
    lines = text.split('\n')
    out = []
    for line in lines:
        # Match lines like "- item" or "  * item"
        m = re.match(r'^(\s*)([-*])\s+(.*)', line)
        if m and not line.strip().startswith('---'):
            indent = m.group(1).replace(' ', '&nbsp;')
            # Escape the hyphen so it renders as literal text, add two spaces for line break
            out.append(indent + r"\- " + m.group(3) + "  ")
        else:
            out.append(line)
    return '\n'.join(out)

def generate():
    md_path = r"C:\Users\exam11\.gemini\antigravity\brain\b2f76a56-b781-4a13-b03d-f689824c7409\AutoTrade_Project_Report.md"
    pdf_path = r"c:\Users\exam11\project\AutoTrade\AutoTrade_Project_Report.pdf"

    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Apply bullet fix
    content = fix_bullets(content)

    # 2. Extract TOC
    toc_content = build_toc(content)

    # 3. Split content by Level 2 headers (## ) to ensure each starts on a new page
    parts = re.split(r'\n(?=## )', content)
    
    # 4. Title Page
    title_page = """
<div style="text-align: center;">
  <br><br><br><br><br><br><br><br><br><br>
  <h1>AutoTrade Project Report</h1>
  <h2>Autonomous Trading Workflow</h2>
  <br>
  <h3>Software Engineering Project</h3>
</div>
"""

    pdf = MarkdownPdf(toc_level=2)
    
    # Add Title Page
    pdf.add_section(Section(title_page, toc=False))

    # Add TOC Page
    pdf.add_section(Section(toc_content, toc=False))

    # Add Content Sections
    for part in parts:
        if part.strip():
            pdf.add_section(Section(part.strip(), toc=True))

    pdf.meta["title"] = "AutoTrade Project Report"
    pdf.save(pdf_path)
    print(f"Successfully saved to {pdf_path}")

if __name__ == "__main__":
    generate()
