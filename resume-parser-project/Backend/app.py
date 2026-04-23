from flask import Flask, request, jsonify, send_from_directory, session
from flask_cors import CORS
import PyPDF2
import re
import spacy
import os
from io import BytesIO
from pathlib import Path
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app, supports_credentials=True)

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "resume-parser-dev-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL",
    f"sqlite:///{(Path(__file__).resolve().parent / 'resume_parser.db').as_posix()}"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

UPLOADS_DIR = Path(__file__).resolve().parent / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ResumeUpload(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    saved_path = db.Column(db.String(500), nullable=False)
    extracted_name = db.Column(db.String(120), nullable=False)
    extracted_email = db.Column(db.String(120), nullable=False)
    skills_csv = db.Column(db.Text, nullable=False, default="")
    ats_score = db.Column(db.Integer, nullable=False, default=0)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)


with app.app_context():
    db.create_all()

nlp = spacy.load("en_core_web_sm")

# 🔹 Home route
@app.route('/')
def home():
    frontend_dir = Path(__file__).resolve().parent.parent / "Frontend"
    frontend_index = frontend_dir / "index.html"
    if frontend_index.exists():
        return send_from_directory(frontend_dir, "index.html")
    return jsonify({"message": "Resume Parser API is running", "upload_endpoint": "/upload"})


@app.route('/<path:filename>')
def frontend_assets(filename):
    frontend_dir = Path(__file__).resolve().parent.parent / "Frontend"
    target_file = frontend_dir / filename
    if target_file.exists() and target_file.is_file():
        return send_from_directory(frontend_dir, filename)
    return jsonify({"error": "Not found"}), 404

# 🔹 Extract text
def extract_text(file_bytes):
    reader = PyPDF2.PdfReader(BytesIO(file_bytes))
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


def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return db.session.get(User, user_id)


@app.route('/auth/signup', methods=['POST'])
def signup():
    payload = request.get_json(silent=True) or {}
    full_name = (payload.get("full_name") or "").strip()
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""

    if not full_name or not email or not password:
        return jsonify({"error": "Full name, email, and password are required"}), 400

    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        return jsonify({"error": "Email already registered"}), 409

    user = User(
        full_name=full_name,
        email=email,
        password_hash=generate_password_hash(password)
    )
    db.session.add(user)
    db.session.commit()
    session["user_id"] = user.id

    return jsonify({
        "message": "Signup successful",
        "user": {"id": user.id, "full_name": user.full_name, "email": user.email}
    }), 201


@app.route('/auth/login', methods=['POST'])
def login():
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "Invalid email or password"}), 401

    session["user_id"] = user.id
    return jsonify({
        "message": "Login successful",
        "user": {"id": user.id, "full_name": user.full_name, "email": user.email}
    })


@app.route('/auth/logout', methods=['POST'])
def logout():
    session.pop("user_id", None)
    return jsonify({"message": "Logged out"})


@app.route('/auth/me', methods=['GET'])
def current_user():
    user = get_current_user()
    if not user:
        return jsonify({"authenticated": False}), 401
    return jsonify({
        "authenticated": True,
        "user": {"id": user.id, "full_name": user.full_name, "email": user.email}
    })


@app.route('/resumes', methods=['GET'])
def list_resumes():
    user = get_current_user()
    if not user:
        return jsonify({"error": "Please log in first"}), 401

    entries = (
        ResumeUpload.query
        .filter_by(user_id=user.id)
        .order_by(ResumeUpload.uploaded_at.desc())
        .all()
    )
    return jsonify({
        "resumes": [
            {
                "id": entry.id,
                "filename": entry.original_filename,
                "name": entry.extracted_name,
                "email": entry.extracted_email,
                "skills": [item for item in entry.skills_csv.split(",") if item],
                "ats_score": entry.ats_score,
                "uploaded_at": entry.uploaded_at.isoformat()
            }
            for entry in entries
        ]
    })

# 🔹 Upload API
@app.route('/upload', methods=['POST'])
def upload_resume():
    try:
        user = get_current_user()
        if not user:
            return jsonify({"error": "Please log in to upload resumes"}), 401

        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400

        file = request.files['file']
        if not file or not file.filename:
            return jsonify({"error": "No file selected"}), 400

        if not file.filename.lower().endswith('.pdf'):
            return jsonify({"error": "Please upload a PDF resume"}), 400

        file_bytes = file.read()
        text = extract_text(file_bytes)
        if not text.strip():
            return jsonify({"error": "Could not read text from the PDF"}), 400

        name = extract_name(text)
        email = extract_email(text)
        skills = extract_skills(text)

        # 🔹 Simple ATS score
        ats_score = min(len(skills) * 20, 100)

        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        safe_name = secure_filename(file.filename)
        stored_filename = f"{user.id}_{timestamp}_{safe_name}"
        file_path = UPLOADS_DIR / stored_filename
        file_path.write_bytes(file_bytes)

        resume_entry = ResumeUpload(
            user_id=user.id,
            original_filename=file.filename,
            saved_path=str(file_path),
            extracted_name=name,
            extracted_email=email,
            skills_csv=",".join(skills),
            ats_score=ats_score
        )
        db.session.add(resume_entry)
        db.session.commit()

        return jsonify({
            "name": name,
            "email": email,
            "skills": skills,
            "ats_score": ats_score,
            "resume_id": resume_entry.id
        })
    except Exception as error:
        app.logger.exception("Upload failed")
        return jsonify({"error": f"Upload failed on server: {str(error)}"}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
