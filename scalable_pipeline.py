import pdfplumber
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import os
import time
import re

# ================= CONFIGURATION =================
INPUT_PDF = r"C:\Users\ajaym\Downloads\S11A90P143.pdf"
OUTPUT_HTML = "Final_Full_Voter_List.html"
CONVERTER_URL = "https://nandakumar.co.in/software/unirev/web/"

STD_COLUMNS = [
    "AC", "Part", "SL", "HouseNo", "Secn", 
    "Name", "Last", "RelType", "RelName", "RelLast", 
    "IDCard", "Link", "Sex", "Age", "HouseName"
]
# =================================================

def extract_and_clean_pdf():
    print("--- Phase 1: Extraction & Header Removal ---")
    path = INPUT_PDF.strip('"')
    if not os.path.exists(path):
        print("❌ Error: PDF not found.")
        return None

    all_rows = []
    
    with pdfplumber.open(path) as pdf:
        print(f"📄 Processing {len(pdf.pages)} pages...")
        for page in pdf.pages:
            tables = page.extract_table(table_settings={"vertical_strategy": "lines", "horizontal_strategy": "lines"})
            if tables:
                for row in tables:
                    clean_row = [str(cell).replace('\n', ' ').strip() if cell else "" for cell in row]
                    
                    # --- DROP HEADERS ---
                    # If row contains "RELATION" or "SEX", it is a header. Skip it.
                    row_str = "".join(clean_row).upper()
                    if "RELATION" in row_str or "SEX" in row_str or "AGE" in row_str:
                        continue 
                        
                    all_rows.append(clean_row)

    df = pd.DataFrame(all_rows)
    
    # --- FIX: DO NOT DROP FIRST ROW (df[1:]) ---
    # Since we already filtered headers in the loop, row 0 is REAL DATA (Ratheesh).
    # We only need to ensure column count matches.
    
    if df.empty:
        print("❌ Error: No data found!")
        return None

    if df.shape[1] > 15: df = df.iloc[:, :15]
    elif df.shape[1] < 15:
        for _ in range(15 - df.shape[1]): df[len(df.columns)] = ""
        
    df.columns = STD_COLUMNS
    
    print("🧹 Merging split rows...")
    data = df.to_dict('records')
    cleaned_data = []
    
    if data: cleaned_data.append(data[0])
        
    for i in range(1, len(data)):
        current = data[i]
        prev = cleaned_data[-1]
        
        sl = str(current.get("SL", "")).strip()
        id_card = str(current.get("IDCard", "")).strip()
        
        # Valid Row Check
        is_sl_valid = sl.isdigit()
        is_id_valid = len(id_card) > 3 and "ID_CARD" not in id_card
        
        if is_sl_valid or is_id_valid:
            cleaned_data.append(current)
        else:
            # Merge UP
            if current.get("Name"): prev["Name"] += " " + current["Name"]
            if current.get("RelName"): prev["RelName"] += " " + current["RelName"]
            if current.get("HouseName"): prev["HouseName"] += " " + current["HouseName"]
                
    print(f"✅ Final Rows: {len(cleaned_data)}")
    return pd.DataFrame(cleaned_data)

def decode_house_numbers(driver, data_list):
    """Smart Decoder for House Numbers (81U -> 81 ഡി)"""
    print(f"   Processing House Numbers ({len(data_list)} items)...")
    final_results = list(data_list)
    
    indices_to_fix = []
    suffixes_to_decode = []
    numbers_part = []
    
    for idx, val in enumerate(data_list):
        val_str = str(val).strip()
        match = re.match(r"^(\d+)([a-zA-Z]+)$", val_str)
        if match:
            indices_to_fix.append(idx)
            numbers_part.append(match.group(1))
            suffixes_to_decode.append(match.group(2))
            
    if not suffixes_to_decode: return final_results

    decoded_suffixes = decode_column_batch(driver, suffixes_to_decode, "HouseSuffixes")
    
    for i, original_idx in enumerate(indices_to_fix):
        final_results[original_idx] = f"{numbers_part[i]}{decoded_suffixes[i]}"
        
    return final_results

def decode_column_batch(driver, data_list, col_name):
    if col_name != "HouseSuffixes": print(f"   Decoding '{col_name}'...")
    results = []
    BATCH_SIZE = 100
    
    for i in range(0, len(data_list), BATCH_SIZE):
        batch = data_list[i:i+BATCH_SIZE]
        text_block = "\n".join(batch)
        try:
            input_box = driver.find_elements(By.TAG_NAME, "textarea")[0]
            input_box.clear()
            driver.execute_script("arguments[0].value = arguments[1];", input_box, text_block)
            
            convert_btns = driver.find_elements(By.XPATH, "//input[@type='button' or @type='submit']")
            if convert_btns: convert_btns[0].click()
            else: input_box.submit()
            
            time.sleep(1.5)
            
            output_box = driver.find_elements(By.TAG_NAME, "textarea")
            res = output_box[1].get_attribute("value") if len(output_box) > 1 else input_box.get_attribute("value")
            
            batch_res = res.split("\n")
            while len(batch_res) < len(batch): batch_res.append("")
            results.extend(batch_res[:len(batch)])
            
        except:
            results.extend(batch)
            
    return results

def main_pipeline():
    df = extract_and_clean_pdf()
    if df is None or df.empty: return

    print("\n--- Phase 2: Smart Decoding ---")
    options = Options()
    options.add_argument("--start-maximized")
    driver = webdriver.Chrome(options=options)
    
    try:
        driver.get(CONVERTER_URL)
        time.sleep(3)
        
        df['Decoded_Name'] = decode_column_batch(driver, df['Name'].fillna("").astype(str).tolist(), "Name")
        df['Decoded_RelType'] = decode_column_batch(driver, df['RelType'].fillna("").astype(str).tolist(), "RelType")
        df['Decoded_RelName'] = decode_column_batch(driver, df['RelName'].fillna("").astype(str).tolist(), "RelName")
        df['Decoded_House'] = decode_column_batch(driver, df['HouseName'].fillna("").astype(str).tolist(), "HouseName")
        df['Decoded_HouseNo'] = decode_house_numbers(driver, df['HouseNo'].fillna("").astype(str).tolist())

    finally:
        driver.quit()

    print("\n--- Phase 3: Generating Final Report ---")
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
    final['RELATION LAST NAME'] = df['RelLast']
    final['ID CARD NO'] = df['IDCard']
    final['PART LINK NO'] = df['Link']
    final['SEX'] = df['Sex']
    final['AGE'] = df['Age']
    final['HOUSE NAME'] = df['Decoded_House']
    
    # Final Check: Filter out any stray header rows that might have slipped through merge
    final = final[final['ID CARD NO'].astype(str) != "ID_CARD_NO"]

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Kerala Voter List</title>
        <style>
            :root {{ --primary: #0056b3; }}
            body {{ font-family: Arial, sans-serif; padding: 20px; background: #f4f4f9; }}
            .container {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); overflow-x: auto; }}
            table {{ width: 100%; border-collapse: collapse; font-size: 13px; white-space: nowrap; }}
            th {{ background: var(--primary); color: white; padding: 12px; text-align: left; position: sticky; top: 0; }}
            td {{ border-bottom: 1px solid #eee; padding: 10px; color: #333; }}
            tr:nth-child(even) {{ background: #f9f9f9; }}
            tr:hover {{ background: #eef6fc; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2 style="color: #333;">🗳️ Final Voter List</h2>
            <p><strong>Total Records:</strong> {len(final)}</p>
            {final.to_html(index=False, border=0)}
        </div>
    </body>
    </html>
    """
    
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"🎉 COMPLETE! Open: {OUTPUT_HTML}")

if __name__ == "__main__":
    main_pipeline()