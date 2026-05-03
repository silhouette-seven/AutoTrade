"""
services.reporting -- PDF generation utility for analyst reports.
"""

import os
from datetime import datetime
from fpdf import FPDF


def generate_analyst_pdf(analyst_name: str, symbol: str,
                         raw_data: dict, report_dict: dict) -> str:
    """
    Generate a PDF report for a given analyst's output.
    
    Args:
        analyst_name: Name of the analyst (e.g., "Sentiment Analyst").
        symbol: The stock symbol (e.g., "AAPL").
        raw_data: The initial data provided to the analyst.
        report_dict: The final report dictionary containing verdict, QA, etc.
        
    Returns:
        The absolute path to the generated PDF file.
    """
    # 1) Create timestamped folder
    # We use a single shared folder per "run" if called close together,
    # but for simplicity, we'll just use the current minute.
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # We want a base reports directory in the project root
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    reports_dir = os.path.join(base_dir, "reports", timestamp_str)
    os.makedirs(reports_dir, exist_ok=True)
    
    filename = f"{analyst_name.replace(' ', '_')}_{symbol}.pdf"
    filepath = os.path.join(reports_dir, filename)

    # 2) Initialize PDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # Fonts
    # fpdf2 defaults: Arial/Helvetica
    pdf.set_font("helvetica", "B", 16)
    
    # Title
    pdf.cell(0, 10, f"{analyst_name} Report: {symbol}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("helvetica", "", 10)
    pdf.cell(0, 10, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(10)
    
    import textwrap
    
    # Helper for writing text blocks safely
    def _write_section(title, content):
        pdf.set_font("helvetica", "B", 12)
        pdf.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("helvetica", "", 10)
        safe_content = str(content).encode('latin-1', 'replace').decode('latin-1')
        for line in safe_content.split('\n'):
            wrapped = textwrap.wrap(line, width=90)
            for w_line in wrapped:
                pdf.cell(0, 6, w_line, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(5)

    # 3) Write Verdict
    verdict = report_dict.get("verdict", "N/A")
    prob = report_dict.get("buy_probability", 0.0)
    conf = report_dict.get("confidence", 0.0)
    
    pdf.set_font("helvetica", "B", 14)
    pdf.cell(0, 10, "1. Final Verdict", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_font("helvetica", "", 11)
    pdf.cell(0, 8, f"Verdict: {verdict.upper()}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"Buy Probability: {prob:.2f}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"Confidence: {conf:.2f}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    
    _write_section("Reasoning:", report_dict.get("reasoning", ""))
    
    # Key Factors
    factors = report_dict.get("key_factors", [])
    if factors:
        pdf.set_font("helvetica", "B", 12)
        pdf.cell(0, 10, "Key Factors:", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("helvetica", "", 10)
        for f in factors:
            safe_f = str(f).encode('latin-1', 'replace').decode('latin-1')
            wrapped = textwrap.wrap(f"- {safe_f}", width=90)
            for w_line in wrapped:
                pdf.cell(0, 6, w_line, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(5)
        
    # Risks
    risks = report_dict.get("risks", [])
    if risks:
        pdf.set_font("helvetica", "B", 12)
        pdf.cell(0, 10, "Risks:", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("helvetica", "", 10)
        for r in risks:
            safe_r = str(r).encode('latin-1', 'replace').decode('latin-1')
            wrapped = textwrap.wrap(f"- {safe_r}", width=90)
            for w_line in wrapped:
                pdf.cell(0, 6, w_line, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(5)

    # 4) Write Research Q&A or Indicators
    pdf.add_page()
    if "indicators" in report_dict:
        pdf.set_font("helvetica", "B", 14)
        pdf.cell(0, 10, "2. Technical Indicators", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(5)
        for ind, val in report_dict.get("indicators", {}).items():
            pdf.set_font("helvetica", "B", 12)
            pdf.cell(0, 8, f"{ind}:", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("helvetica", "", 10)
            s_val = str(val).encode('latin-1', 'replace').decode('latin-1')
            for line in s_val.split('\n'):
                wrapped = textwrap.wrap(line, width=90)
                for w_line in wrapped:
                    pdf.cell(0, 6, w_line, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(5)
    else:
        pdf.set_font("helvetica", "B", 14)
        pdf.cell(0, 10, "2. Grounded Research Q&A", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(5)
        
        qa_list = report_dict.get("research_qa", [])
        for i, qa in enumerate(qa_list, 1):
            _write_section(f"Q{i}: {qa.get('topic', 'Topic')}", qa.get("question", ""))
            pdf.set_font("helvetica", "B", 10)
            pdf.cell(0, 8, "Answer:", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("helvetica", "", 10)
            ans = str(qa.get("answer", "")).encode('latin-1', 'replace').decode('latin-1')
            for line in ans.split('\n'):
                wrapped = textwrap.wrap(line, width=90)
                for w_line in wrapped:
                    pdf.cell(0, 6, w_line, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(10)
        
    # 5) Write Raw Data
    pdf.add_page()
    pdf.set_font("helvetica", "B", 14)
    pdf.cell(0, 10, "3. Raw Input Data", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    
    # Just dump the dictionary as formatted strings
    pdf.set_font("helvetica", "", 9)
    for key, val in raw_data.items():
        if isinstance(val, list):
            pdf.set_font("helvetica", "B", 10)
            pdf.cell(0, 8, f"{key}:", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("helvetica", "", 9)
            for item in val:
                s_item = str(item).encode('latin-1', 'replace').decode('latin-1')
                wrapped = textwrap.wrap(f"  - {s_item}", width=100)
                for w_line in wrapped:
                    pdf.cell(0, 5, w_line, new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_font("helvetica", "B", 10)
            pdf.cell(0, 8, f"{key}:", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("helvetica", "", 9)
            s_val = str(val).encode('latin-1', 'replace').decode('latin-1')
            wrapped = textwrap.wrap(f"  {s_val}", width=100)
            for w_line in wrapped:
                pdf.cell(0, 5, w_line, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    # 6) Output
    pdf.output(filepath)
    print(f"[reporting] Saved PDF: {filepath}")
    return filepath
