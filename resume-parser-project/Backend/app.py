from flask import Flask, request, jsonify
from flask_cors import CORS
import PyPDF2
import re
import spacy
import os
from io import BytesIO
from pathlib import Path
from flask import send_from_directory

app = Flask(__name__)
CORS(app)

nlp = spacy.load("en_core_web_sm")

# 🔹 Home route
@app.route('/')
def home():
    frontend_dir = Path(__file__).resolve().parent.parent / "Frontend"
    frontend_index = frontend_dir / "index.html"
    if frontend_index.exists():
        return send_from_directory(frontend_dir, "index.html")
    return jsonify({"message": "Resume Parser API is running", "upload_endpoint": "/upload"})

# 🔹 Extract text
def extract_text(file):
    reader = PyPDF2.PdfReader(BytesIO(file.read()))
    text = ""
    for page in reader.pages:
        if page.extract_text():
            text += page.extract_text()
    return text

# 🔹 Extract email
def extract_email(text):
    match = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,4}", text)
    return match[0] if match else "Not found"

# 🔹 Extract name using NLP
def extract_name(text):
    doc = nlp(text)
    for ent in doc.ents:
        if ent.label_ == "PERSON":
            return ent.text
    return "Not found"

# 🔹 Extract skills (basic)
skills_list = ["Python", "Java", "SQL", "Machine Learning", "Excel", "Power BI"]

def extract_skills(text):
    found = []
    for skill in skills_list:
        if skill.lower() in text.lower():
            found.append(skill)
    return found

# 🔹 Upload API
@app.route('/upload', methods=['POST'])
def upload_resume():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400

        file = request.files['file']
        if not file or not file.filename:
            return jsonify({"error": "No file selected"}), 400

        if not file.filename.lower().endswith('.pdf'):
            return jsonify({"error": "Please upload a PDF resume"}), 400

        text = extract_text(file)
        if not text.strip():
            return jsonify({"error": "Could not read text from the PDF"}), 400

        name = extract_name(text)
        email = extract_email(text)
        skills = extract_skills(text)

        # 🔹 Simple ATS score
        ats_score = min(len(skills) * 20, 100)

        return jsonify({
            "name": name,
            "email": email,
            "skills": skills,
            "ats_score": ats_score
        })
    except Exception as error:
        app.logger.exception("Upload failed")
        return jsonify({"error": f"Upload failed on server: {str(error)}"}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
