import os
from fpdf import FPDF
from datetime import datetime

class CodePDF(FPDF):
    def header(self):
        self.set_font("Courier", "B", 12)
        self.cell(0, 10, "AutoTrade - Code Implementation", border=0, ln=1, align="C")

    def footer(self):
        self.set_y(-15)
        self.set_font("Courier", "I", 8)
        self.cell(0, 10, f"Page {self.page_no()}", border=0, ln=0, align="C")

def main():
    pdf = CodePDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    base_dir = r"c:\Users\exam11\project\AutoTrade"
    
    # Title Page
    pdf.set_font("Courier", "B", 16)
    pdf.cell(0, 10, "Project: AutoTrade", border=0, ln=1, align="L")
    pdf.set_font("Courier", "", 12)
    pdf.cell(0, 10, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", border=0, ln=1, align="L")
    pdf.multi_cell(0, 10, "This document contains the source code and implementation details of the AutoTrade project.")
    pdf.add_page()
    pdf.set_font("Courier", "", 9)
    
    for root, dirs, files in os.walk(base_dir):
        # Exclude hidden and cache dirs
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ("__pycache__", "venv", "reports")]
        
        for file in files:
            if file.endswith(".py") or file == "requirements.txt" or file.endswith(".example"):
                filepath = os.path.join(root, file)
                rel_path = os.path.relpath(filepath, base_dir)
                
                # Exclude the script itself
                if rel_path == "generate_pdf.py":
                    continue
                
                pdf.set_font("Courier", "B", 11)
                pdf.set_fill_color(200, 220, 255)
                pdf.cell(0, 10, f"File: {rel_path}", border=0, ln=1, align="L", fill=True)
                pdf.set_font("Courier", "", 9)
                
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                        for line in lines:
                            # Replace tabs and newlines
                            line = line.replace('\t', '    ').rstrip()
                            # Replace unencodable characters
                            line = line.encode('latin-1', 'replace').decode('latin-1')
                            pdf.cell(0, 4, txt=line, border=0, ln=1)
                except Exception as e:
                    pdf.cell(0, 4, txt=f"Error reading file: {e}", border=0, ln=1)
                
                pdf.ln(5)

    output_path = os.path.join(base_dir, "AutoTrade_Implementation.pdf")
    pdf.output(output_path)
    print(f"PDF generated successfully at: {output_path}")

if __name__ == "__main__":
    main()
