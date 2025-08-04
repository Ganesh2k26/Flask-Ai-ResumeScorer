from flask import Flask, render_template, request, redirect, url_for, session
import csv, os, re
import fitz  # PyMuPDF
import google.generativeai as genai

app = Flask(__name__)
app.secret_key = 'AIzaSyA11QmLodaY2S2imhsBAIlsns4WDHzB43w'
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Gemini API Setup
genai.configure(api_key="AIzaSyA11QmLodaY2S2imhsBAIlsns4WDHzB43w")

CSV_PATH = r'D:\GANESH\MINI PROJECTS\Flask\portal\user.csv'
import re

# Define skill categories with keyword lists and weights
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

# Score a single category with high-value keyword boost
def score_section(resume_text, keyword_list):
    found = [kw for kw in keyword_list if re.search(r'\b' + re.escape(kw) + r'\b', resume_text, re.IGNORECASE)]
    score = len(found) / (len(keyword_list) + 0.1) * 100
    high_value = set(priority_keywords)
    bonus_keywords = high_value.intersection(found)
    bonus = len(bonus_keywords) * 2
    return min(score + bonus, 100), found

# Main evaluation function
def evaluate_resume(resume_text):
    analysis = {}
    total_weighted_score = 0

    for category, config in skills.items():
        cat_score, matched = score_section(resume_text, config["keywords"])
        weighted_score = (cat_score / 100) * config["weight"]
        total_weighted_score += weighted_score
        analysis[category] = {
            "score": round(cat_score, 2),
            "matched_keywords": matched,
            "missing_keywords": [kw for kw in config["keywords"] if kw not in matched]
        }

    # Clamp final score between 1 and 100
        final_score = max(1, min(round(total_weighted_score * 100, 2), 100)) * 100


    # Rating logic
    if analysis["technical"]["score"] < 50 or analysis["portfolio"]["score"] < 25:
        rating = "❌ Resume missing core skills"
    elif final_score >= 75:
        rating = "✅ Excellent Match"
    elif final_score >= 50:
        rating = "⚠️ Average Match"
    else:
        rating = "❌ Weak Resume Match"

    # Suggestions
    missing_critical = [kw for kw in priority_keywords if not re.search(r'\b' + re.escape(kw) + r'\b', resume_text, re.IGNORECASE)]
    suggestions = ""
    if missing_critical:
        suggestions += f"⚠️ Missing critical keywords: {', '.join(missing_critical)}\nConsider adding relevant projects or experience that include these terms."

    return {
        "final_score": final_score,
        "rating": rating,
        "analysis": analysis,
        "suggestions": suggestions
    }

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

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name'].strip().title()
        email = request.form['email'].strip()
        password = request.form['pass']
        with open(CSV_PATH, 'a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow([name, email, password])
        return render_template('results.html', name=name)
    return render_template('reg.html')

@app.route('/admin')
def admin():
    users = []
    try:
        with open(CSV_PATH, 'r') as file:
            reader = csv.reader(file)
            users = [row for row in reader if len(row) == 3]
    except FileNotFoundError:
        pass
    return render_template('admin.html', users=users)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('pass', '').strip()
        try:
            with open(CSV_PATH, 'r') as file:
                reader = csv.reader(file)
                for row in reader:
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
    total_weighted_score = 0
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

        final_score = round(total_weighted_score, 2)

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

def extract_text_from_pdf(pdf_path):
    text = ""
    try:
        with fitz.open(pdf_path) as doc:
            for page in doc:
                text += page.get_text()
    except Exception as e:
        text = f"Error extracting text: {str(e)}"
    return text

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/reset', methods=['POST'])
def reset():
    try:
        with open(CSV_PATH, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['Name', 'Email', 'Password'])
        return "<h3>Data reset successfully</h3>"
    except Exception as e:
        return f"<h3>Error resetting data: {str(e)}</h3>"

if __name__ == '__main__':
    app.run(debug=True, port=5000)
