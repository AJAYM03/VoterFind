# VoterFind 🔍
**A tool to make the 2002 Kerala Electoral Rolls (SIR) actually searchable.**

![Python](https://img.shields.io/badge/Python-3.9%2B-blue) ![Flask](https://img.shields.io/badge/Flask-Web%20App-green) ![Selenium](https://img.shields.io/badge/Selenium-Automation-orange)

## 📖 The Story

This project started with a frustrated morning. My parents were trying to find their names in the **2002 Special Intensive Revision (SIR)** electoral rolls to verify their details.

They downloaded the PDFs, opened them, and saw their names clearly in Malayalam. But when they used **Ctrl+F** to search... **0 results.**

### The Problem
The PDFs were deceptive. To the human eye, the text looked like Malayalam. To the computer, it was gibberish.

* **Visual:** `രതീശ്` (Ratheesh)
* **Actual Data:** `cXoiv`

The government data used **legacy ASCII encoding (specifically the ISM/Karthika format)**. Instead of standard Unicode, English keystrokes were mapped to Malayalam character shapes. On top of that, the table formatting was broken—house names were split across multiple lines, creating "ghost rows" that messed up the data structure.

### The Solution: VoterFind
I built this Python pipeline to bridge the gap between 2002 data and modern technology. It essentially "fixes" the PDF by:
1.  **Extracting** the raw table data.
2.  **Merging** broken rows (fixing the "hanging suffix" issue).
3.  **Decoding** the legacy ASCII text back to Unicode Malayalam.
4.  **Generating** a clean, fully searchable A3 PDF.

---

## 🛠️ How It Works

VoterFind uses a robust 3-stage pipeline:

1.  **Smart Extraction (`pdfplumber`):**
    * Extracts tables while strictly respecting grid lines.
    * **Header Nuke:** Automatically detects and removes repeated page headers that corrupt data sorting.
    * **Ghost Row Merge:** Detects rows with missing IDs (often just a house name suffix like "il" or "puram") and merges them back to the previous voter entry.

2.  **The Decoder (`Selenium`):**
    * Connects to a legacy-to-unicode converter.
    * Batches data to convert Names, Relations, and House Names from `cXoiv` -> `രതീശ്`.
    * **Smart Fix:** Converts mixed formats (e.g., `81U` -> `81 ഡി`) correctly.

3.  **PDF Generation (Headless Chrome):**
    * Generates a clean HTML table with all **15 original columns**.
    * Uses Chrome's native print engine to save a **Searchable A3 PDF** that preserves Malayalam rendering perfectly.

---

## 🚀 Installation & Usage

### Prerequisites
* Python 3.x
* Google Chrome installed on your machine (for Selenium)

### Steps
1.  **Clone the repo**
    ```bash
    git clone [https://github.com/yourusername/VoterFind.git](https://github.com/yourusername/VoterFind.git)
    cd VoterFind
    ```
2.  **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    ```
3.  **Run the App**
    ```bash
    python app.py
    ```
4.  **Open in Browser**
    Go to `http://127.0.0.1:5000`
5.  **Drag & Drop**
    Upload your SIR 2002 PDF. Wait for the processing (Chrome will open briefly). Download your fixed file!

---

## 🙏 Credits
* **Decoder Logic:** Powered by the [Nandakumar ISM Converter](https://nandakumar.co.in/software/unirev/web/). This project automates the usage of this excellent tool to handle the font mapping.

## 📄 License
MIT License. Feel free to use this to help your own parents!
