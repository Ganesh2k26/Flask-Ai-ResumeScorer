from flask import Flask, render_template, request, redirect, url_for, session,flash
import csv, os, re
import fitz  # PyMuPDF
import google.generativeai as genai
from dotenv import load_dotenv
import markdown

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "super_secret_key_123")  # Required for session support
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Gemini API Setup
gemini_key = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=gemini_key)

CSV_PATH = os.path.join(os.path.dirname(__file__), 'user.csv')

skills = {
    "technical": {
        "keywords": ["python", "flask", "api", "machine learning", "deep learning", "nlp", "html", "css", "javascript", "git", "github", "sql", "rest api", "tensorflow", "pandas", "numpy"],
        "weight": 0.3
    },
    "soft": {
        "keywords": ["communication", "teamwork", "problem-solving", "leadership", "collaboration", "adaptability"],
        "weight": 0.2
    },
    "education": {
        "keywords": ["bachelor", "b.tech", "be", "mca", "degree", "computer science", "information technology"],
        "weight": 0.2
    },
    "experience": {
        "keywords": ["internship", "worked", "experience", "developed", "deployed", "built", "led", "contributed"],
        "weight": 0.15
    },
    "portfolio": {
        "keywords": ["portfolio", "github", "website", "demo", "live link", "repo", "project"],
        "weight": 0.15
    }
}

priority_keywords = ["flask", "api", "github", "deploy", "sql", "tensorflow", "rest api"]

def score_section(resume_text, keyword_list):
    found = [kw for kw in keyword_list if re.search(r'\b' + re.escape(kw) + r'\b', resume_text, re.IGNORECASE)]
    score = len(found) / (len(keyword_list) + 0.1) * 100
    bonus = len(set(priority_keywords).intersection(found)) * 2
    return min(score + bonus, 100), found

def generate_gemini_suggestion(resume_text, missing_keywords):
    if not missing_keywords:
        return "✅ Great work! Your resume covers all important skill areas."
    prompt = f"""
You are an AI resume reviewer. The candidate's resume is missing these keywords: {', '.join(missing_keywords)}.

Resume excerpt:
{resume_text[:3000]}

Please respond with exactly **4 concise bullet points**, formatted with markdown (**), each containing:
- One specific resume improvement suggestion
- Natural usage of missing keywords
- Short and professional phrasing (max 2–3 sentences per point)

Do not include introductions, summaries, or long explanations.
"""
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"⚠️ Gemini Error: {str(e)}"

def extract_text_from_pdf(pdf_path):
    try:
        with fitz.open(pdf_path) as doc:
            return "".join(page.get_text() for page in doc)
    except Exception as e:
        return f"Error extracting text: {str(e)}"
    
def valid_email(email):
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return re.match(pattern, email)

def valid_password(password):
    if len(password) < 8:
        return False
    if not re.search(r'[A-Z]', password):
        return False
    if not re.search(r'[a-z]', password):
        return False
    if not re.search(r'\d', password):
        return False
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False
    return True

def unique_username(name):
    name = name.strip().lower()
    if not name:
        return False
    if len(name) < 3 or len(name) > 20:
        return False
    if not re.match(r'^[a-zA-Z\s]+$', name):
        return False   
    with open(CSV_PATH, 'r') as file:
        for row in csv.reader(file):
            if row and row[0].strip().lower() == name:
                return False
    return True
    

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name'].strip().title()
        email = request.form['email'].strip()
        password = request.form['pass']
        if not unique_username(name):
            flash("Username already exists or is invalid", 'error')
            return redirect(url_for('register'))
        if not valid_email(email):
            flash("Invalid email format", 'error')
            return redirect(url_for('register'))
        if not valid_password(password):
            flash("Password must be at least 8 characters long, contain uppercase, lowercase, digits, and special characters", 'error')
            return redirect(url_for('register'))
        
        with open(CSV_PATH, 'a', newline='') as file:
            csv.writer(file).writerow([name, email, password])
        return render_template('results.html', name=name)
    return render_template('reg.html')

@app.route('/admin')
def admin():
    try:
        with open(CSV_PATH, 'r') as file:
            users = [row for row in csv.reader(file) if len(row) == 3]
    except FileNotFoundError:
        users = []
    return render_template('admin.html', users=users)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('pass', '').strip()
        try:
            with open(CSV_PATH, 'r') as file:
                for row in csv.reader(file):
                    if len(row) == 3 and row[1].lower() == email.lower() and row[2] == password:
                        session['user'] = row[0].strip().title()
                        return redirect(url_for('resume'))
            return "<h3>Invalid credentials</h3>"
        except FileNotFoundError:
            return "<h3>No users registered yet</h3>"
    return render_template('login.html')

@app.route('/resume', methods=['GET', 'POST'])
def resume():
    if 'user' not in session:
        return redirect(url_for('login'))

    resume_text = ""
    analysis = {}
    suggestion = None

    if request.method == "POST":
        if "resume_file" in request.files:
            file = request.files["resume_file"]
            if file.filename.endswith(".pdf"):
                file_path = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
                file.save(file_path)
                resume_text = extract_text_from_pdf(file_path)
        elif "resume" in request.form:
            resume_text = request.form["resume"].lower()

        total_weighted_score = 0
        missing_keywords_all = []

        for category, config in skills.items():
            cat_score, matched_keywords = score_section(resume_text, config["keywords"])
            weighted = (cat_score / 100) * config["weight"]
            total_weighted_score += weighted
            missing = [k for k in config["keywords"] if k not in matched_keywords]
            missing_keywords_all.extend(missing)

            analysis[category] = {
                "score": round(cat_score, 2),
                "weight": config["weight"],
                "matched": matched_keywords,
                "missing": missing
            }

        final_score = round(total_weighted_score * 100, 2)

        if final_score >= 75:
            level = "✅ Excellent Match"
        elif final_score >= 50:
            level = "⚠️ Average Match"
        else:
            level = "❌ Weak Resume Match"

        suggestion = generate_gemini_suggestion(resume_text, missing_keywords_all)

        return render_template("result.html", final_score=final_score, analysis=analysis,
                               level=level, suggestion=suggestion, user=session['user'])

    return render_template("index.html", user=session['user'])

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/reset', methods=['POST'])
def reset():
    try:
        with open(CSV_PATH, 'w', newline='') as file:
            csv.writer(file).writerow(['Name', 'Email', 'Password'])
        return "<h3>Data reset successfully</h3>"
    except Exception as e:
        return f"<h3>Error resetting data: {str(e)}</h3>"
    
@app.route('/chat', methods=['GET', 'POST'])
def chat():
    if 'user' not in session:
        return redirect(url_for('login'))

    chat_history = session.get('chat_history', [])
    response = ""

    if request.method == 'POST':
        user_msg = request.form.get('user_msg', '').strip()
        if user_msg:
            try:
                model = genai.GenerativeModel("gemini-1.5-flash")
                convo = model.start_chat(history=[])
                result = convo.send_message(user_msg)

                # Safely access .text
                response = markdown.markdown(result.text.strip())
            except Exception as e:
                response = f"⚠️ Gemini Error: {str(e)}"

            chat_history.append({'user': user_msg, 'assistant': response})
            session['chat_history'] = chat_history

    return render_template('chat.html', chat_history=chat_history)


if __name__ == '__main__':
    app.run(debug=True, port=5000)
