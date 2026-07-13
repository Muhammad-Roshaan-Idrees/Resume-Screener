# Resume-Screener

A powerful, intelligent resume screening application that automatically filters and categorizes resumes based on degree, specialization, job category, and experience requirements.

[![Deployed on Render](https://img.shields.io/badge/Deployed%20on-Render-46C3C8.svg)](https://matrix-ats.onrender.com)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Flask 2.3.3](https://img.shields.io/badge/flask-2.3.3-green.svg)](https://flask.palletsprojects.com/)

---

## 🚀 Live Demo

**Public URL:** [https://matrix-ats.onrender.com](https://matrix-ats.onrender.com)

---

## ✨ Features

- 📤 **Batch Upload** – Upload multiple resumes at once (PDF, DOCX, JPG, PNG, WEBP)
- 🔍 **Smart Filtering** – Filter by Degree, Specialization, Job Category, and Experience
- 🤖 **Intelligent Matching** – Uses comprehensive global dictionaries for degrees, subjects, and job roles
- 📊 **Real‑time Results** – Instantly see Accepted (Qualified) and Rejected (Not Qualified) candidates
- 👁️ **Resume Preview** – View any uploaded resume with one click
- 📦 **Export Qualified Candidates** – Download all accepted resumes as a ZIP file
- 💾 **Persistent Storage** – SQLite database stores all screening results
- 🌐 **Deployment Ready** – Easily deploy to Render, PythonAnywhere, or any cloud platform

---

## 🛠️ Tech Stack

| Technology               | Purpose                                 |
| ------------------------ | --------------------------------------- |
| **Python 3.11+**         | Backend language                        |
| **Flask**                | Web framework                           |
| **SQLite**               | Database for storing candidate data     |
| **pdfplumber / PyPDF2**  | PDF text extraction                     |
| **python-docx**          | DOCX text extraction                    |
| **Pillow + pytesseract** | Image OCR (text extraction from images) |
| **Tailwind CSS**         | Modern, responsive UI styling           |
| **Choices.js**           | Searchable dropdowns                    |
| **Font Awesome**         | Icons for professional UI               |
| **Gunicorn**             | Production WSGI server                  |

---

## 📋 How It Works

1. **Upload Resumes** – Drag & drop or select multiple files
2. **Set Filters** – Choose Degree, Subject, Job Category, and Minimum Experience
3. **Screen** – Click "Process" – the system extracts text from each file
4. **Match** – Compares extracted text against your filters using intelligent matching
5. **Sort** – Automatically places candidates into **Qualified** or **Not Qualified** pools
6. **Review** – Click "View" to open any resume; click "Export Qualified" to download all accepted candidates

---

## 📁 Project Structure

resume-screener/
├── templates/
│ └── index.html
├── uploads/
├── .gitignore
├── app.py
├── README.md
├── requirements.txt
├── resume_screening.db

---

## 🚀 Local Development Setup

### Prerequisites

- **Python 3.11 or higher** ([Download](https://www.python.org/downloads/))
- **Git** ([Download](https://git-scm.com/downloads))
- **Tesseract OCR** (for image text extraction – optional)
  - **Windows:** [Download from UB-Mannheim](https://github.com/UB-Mannheim/tesseract/wiki)
  - **Mac:** `brew install tesseract`
  - **Linux:** `sudo apt install tesseract-ocr`

### Installation

1. **Clone the repository:**

   ```bash
   git clone https://github.com/Muhammad-Roshaan-Idrees/Resume-Screener.git
   cd Resume-Screener

   ```

2. **Create a virtual environment (recommended):**

   ```bash
   python -m venv venv
   source venv/bin/activate   # On Windows: venv\Scripts\activate

   ```

3. **Install dependencies:**

   ```bash
   pip install -r requirements.txt

   ```

4. **Run the application:**

   ```bash
   python app.py

   ```

5. **Open in browser:**
   ```bash
   http://127.0.0.1:5000


   ```
