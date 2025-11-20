import os
import time
import re
import base64
import pdfplumber
import pandas as pd
from flask import Flask, render_template, request, send_file, jsonify
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from werkzeug.utils import secure_filename

app = Flask(__name__)

# ================= CONFIGURATION =================
UPLOAD_FOLDER = 'uploads'
PROCESSED_FOLDER = 'processed'
CONVERTER_URL = "https://nandakumar.co.in/software/unirev/web/"

STD_COLUMNS = [
    "AC", "Part", "SL", "HouseNo", "Secn", 
    "Name", "Last", "RelType", "RelName", "RelLast", 
    "IDCard", "Link", "Sex", "Age", "HouseName"
]

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)

def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    return webdriver.Chrome(options=options)

def extract_and_clean_pdf(path):
    all_rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            tables = page.extract_table(table_settings={"vertical_strategy": "lines", "horizontal_strategy": "lines"})
            if tables:
                for row in tables:
                    clean_row = [str(cell).replace('\n', ' ').strip() if cell else "" for cell in row]
                    
                    # STRICT HEADER REMOVAL
                    row_str = "".join(clean_row).upper()
                    if "RELATION" in row_str and "SEX" in row_str:
                        continue 
                    all_rows.append(clean_row)

    df = pd.DataFrame(all_rows)
    
    if df.shape[1] > 15: df = df.iloc[:, :15]
    elif df.shape[1] < 15:
        for _ in range(15 - df.shape[1]): df[len(df.columns)] = ""
    df.columns = STD_COLUMNS
    
    data = df.to_dict('records')
    cleaned_data = []
    if data: cleaned_data.append(data[0]) 
        
    for i in range(1, len(data)):
        current = data[i]
        prev = cleaned_data[-1]
        
        sl = str(current.get("SL", "")).strip()
        id_card = str(current.get("IDCard", "")).strip()
        age = str(current.get("Age", "")).strip()
        
        # Life Signs Check
        is_real_row = (sl.isdigit()) or \
                      (len(id_card) > 3 and "ID_CARD" not in id_card) or \
                      (age.isdigit() and int(age) > 17)
        
        if is_real_row:
            cleaned_data.append(current)
        else:
            if current.get("Name"): prev["Name"] += " " + current["Name"]
            if current.get("RelName"): prev["RelName"] += " " + current["RelName"]
            if current.get("RelLast"): prev["RelLast"] += " " + current["RelLast"]
            if current.get("HouseName"): prev["HouseName"] += " " + current["HouseName"]
            
    return pd.DataFrame(cleaned_data)

def decode_column_batch(driver, data_list, col_name="Column"):
    if col_name != "HouseSuffixes": print(f"   Processing '{col_name}'...")
    indices = []
    values = []
    
    for idx, val in enumerate(data_list):
        val_str = str(val).strip()
        
        # --- FIX: DECODE EVERYTHING EXCEPT NUMBERS ---
        # Old check: re.search(r'[a-zA-Z]', val_str) -> Missed `
        # New check: if not val_str.isdigit() -> Catches ` and letters
        if val_str and not val_str.isdigit():
            indices.append(idx)
            values.append(val_str)
            
    if not values: return data_list

    decoded_vals = []
    BATCH_SIZE = 150 
    for i in range(0, len(values), BATCH_SIZE):
        batch = values[i:i+BATCH_SIZE]
        text_block = "\n".join(batch)
        try:
            input_box = driver.find_elements(By.TAG_NAME, "textarea")[0]
            input_box.clear()
            driver.execute_script("arguments[0].value = arguments[1];", input_box, text_block)
            
            convert_btns = driver.find_elements(By.XPATH, "//input[@type='button' or @type='submit']")
            if convert_btns: convert_btns[0].click()
            else: input_box.submit()
            time.sleep(0.8)
            
            output_box = driver.find_elements(By.TAG_NAME, "textarea")
            res = output_box[1].get_attribute("value") if len(output_box) > 1 else input_box.get_attribute("value")
            batch_res = res.split("\n")
            while len(batch_res) < len(batch): batch_res.append("")
            decoded_vals.extend(batch_res[:len(batch)])
        except: decoded_vals.extend(batch)

    final_list = list(data_list)
    for i, original_idx in enumerate(indices):
        if i < len(decoded_vals): final_list[original_idx] = decoded_vals[i]
    return final_list

def decode_house_numbers(driver, data_list):
    final_results = list(data_list)
    indices = []
    suffixes = []
    numbers = []
    for idx, val in enumerate(data_list):
        val_str = str(val).strip()
        match = re.match(r"^(\d+)(.*)$", val_str)
        if match and match.group(2):
            indices.append(idx)
            numbers.append(match.group(1))
            suffixes.append(match.group(2))
    if not suffixes: return final_results
    decoded_suf = decode_column_batch(driver, suffixes, "HouseSuffixes")
    for i, idx in enumerate(indices):
        final_results[idx] = f"{numbers[i]}{decoded_suf[i]}"
    return final_results

def generate_pdf_from_html(html_filename):
    html_path = os.path.abspath(os.path.join(PROCESSED_FOLDER, html_filename))
    pdf_filename = html_filename.replace('.html', '.pdf')
    pdf_path = os.path.join(PROCESSED_FOLDER, pdf_filename)
    driver = get_driver()
    try:
        driver.get(f"file:///{html_path}")
        pdf_data = driver.execute_cdp_cmd("Page.printToPDF", {
            "landscape": True, "printBackground": True,
            "paperWidth": 16.5, "paperHeight": 11.7, "scale": 0.7,
            "marginTop": 0.3, "marginBottom": 0.3, "marginLeft": 0.3, "marginRight": 0.3
        })
        with open(pdf_path, "wb") as f: f.write(base64.b64decode(pdf_data['data']))
        return pdf_filename
    finally: driver.quit()

def process_pdf_pipeline(filepath):
    df = extract_and_clean_pdf(filepath)
    if df is None or df.empty: raise Exception("Extraction Failed")
    
    options = Options()
    options.add_argument("--start-maximized")
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(CONVERTER_URL)
        time.sleep(2)
        df['Decoded_Name'] = decode_column_batch(driver, df['Name'].fillna("").astype(str).tolist(), "Name")
        df['Decoded_RelType'] = decode_column_batch(driver, df['RelType'].fillna("").astype(str).tolist(), "RelType")
        df['Decoded_RelName'] = decode_column_batch(driver, df['RelName'].fillna("").astype(str).tolist(), "RelName")
        df['Decoded_RelLast'] = decode_column_batch(driver, df['RelLast'].fillna("").astype(str).tolist(), "RelLast")
        df['Decoded_House'] = decode_column_batch(driver, df['HouseName'].fillna("").astype(str).tolist(), "House")
        df['Decoded_HouseNo'] = decode_house_numbers(driver, df['HouseNo'].fillna("").astype(str).tolist())
    finally:
        driver.quit()
        
    final = pd.DataFrame()
    final['AC CODE'] = df['AC']
    final['PART CODE'] = df['Part']
    final['SL NO'] = range(1, len(df) + 1)
    final['HOUSE NO'] = df['Decoded_HouseNo']
    final['SECN CODE'] = df['Secn']
    final['FIRST NAME'] = df['Decoded_Name']
    final['LAST NAME'] = df['Last']
    final['RELATION TYPE'] = df['Decoded_RelType']
    final['RELATION FIRST NAME'] = df['Decoded_RelName']
    final['RELATION LAST NAME'] = df['Decoded_RelLast']
    final['ID CARD NO'] = df['IDCard']
    final['PART LINK NO'] = df['Link']
    final['SEX'] = df['Sex']
    final['AGE'] = df['Age']
    final['HOUSE NAME'] = df['Decoded_House']
    
    final = final[final['ID CARD NO'].astype(str) != "ID_CARD_NO"]
    
    output_filename = f"Processed_{int(time.time())}.html"
    output_path = os.path.join(PROCESSED_FOLDER, output_filename)
    
    html_template = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><title>Voter List</title>
    <style>
        body {{ font-family: Arial, sans-serif; padding: 20px; font-size: 11px; }}
        h2 {{ text-align: center; color: #2c3e50; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th {{ background-color: #2c3e50; color: white; padding: 6px; text-align: left; white-space: nowrap; font-size: 10px; }}
        td {{ border-bottom: 1px solid #eee; padding: 6px; border-right: 1px solid #eee; }}
        tr:nth-child(even) {{ background-color: #f9f9f9; }}
    </style></head>
    <body>
        <h2>🗳️ VoterFind List ({len(final)} Records)</h2>
        {final.to_html(index=False, border=0)}
    </body></html>
    """
    with open(output_path, "w", encoding="utf-8") as f: f.write(html_template)
    return output_filename

# --- ROUTES ---
@app.route('/')
def index(): return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files: return jsonify({'error': 'No file'}), 400
    file = request.files['file']
    if file.filename == '': return jsonify({'error': 'No filename'}), 400
    filename = secure_filename(file.filename)
    path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(path)
    try:
        html_file = process_pdf_pipeline(path)
        return jsonify({'status': 'success', 'redirect_url': f'/view/{html_file}'})
    except Exception as e: return jsonify({'error': str(e)}), 500

@app.route('/view/<filename>')
def view_file(filename):
    with open(os.path.join(PROCESSED_FOLDER, filename), 'r', encoding='utf-8') as f: content = f.read()
    btn = f"""<div style="position:fixed;top:20px;right:20px;"><a href="/convert_pdf/{filename}" style="background:#e74c3c;color:white;padding:12px;text-decoration:none;border-radius:5px;font-family:sans-serif;font-weight:bold;box-shadow:0 4px 6px rgba(0,0,0,0.1);">📄 Download PDF</a></div>"""
    return btn + content

@app.route('/convert_pdf/<filename>')
def convert_to_pdf(filename):
    pdf_file = generate_pdf_from_html(filename)
    return send_file(os.path.join(PROCESSED_FOLDER, pdf_file), as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True, port=5000)