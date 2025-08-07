from flask import Flask, request, jsonify
import pandas as pd
import requests
from flask_cors import CORS
import traceback
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import json

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app)

# Gemini & Email Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")

# ✅ Firebase Admin Setup (from environment variable for Render)
    # ✅ Firebase Admin Setup: Supports both local (file) and Render (env variable)
if not firebase_admin._apps:
    if os.getenv("FIREBASE_CREDENTIALS_JSON"):
        # Running on Render – load from environment variable
        firebase_dict = json.loads(os.getenv("FIREBASE_CREDENTIALS_JSON"))
        cred = credentials.Certificate(firebase_dict)
    else:
        # Running locally – load from local file
        cred = credentials.Certificate("firebase-key.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()


# Load course data
try:
    df = pd.read_csv("course_data.csv")
    print("✅ course_data.csv loaded successfully.")
except Exception as e:
    print("❌ Failed to load CSV:", e)
    df = pd.DataFrame()

@app.route('/')
def home():
    return "🎓 EdTech backend is running!"

@app.route('/analyze-profile', methods=['POST'])
def analyze_profile():
    try:
        data = request.get_json()
        print("✅ Received profile:", data)

        personality = data.get("personality", "").upper()
        gpa = float(data.get("gpa", 0))
        goal = data.get("career_goal", "").lower().strip()
        budget = int(data.get("budget", 0))
        style = data.get("learning_style", "").lower().strip()

        def run_filter(strict=True, drop_style=False, relax_budget=False):
            query = (df['career_goal'].str.lower().str.contains(goal)) & (df['personality_min_gpa'] <= gpa)
            if not relax_budget:
                query &= (df['min_budget'] <= budget) & (df['max_budget'] >= budget)
            if not drop_style:
                query &= (df['learning_style'].str.lower() == style)
            return df[query]

        matched = run_filter()
        if matched.empty:
            matched = run_filter(drop_style=True)
        if matched.empty:
            matched = run_filter(drop_style=True, relax_budget=True)
        if matched.empty:
            return jsonify({"error": "No close matches found."}), 404

        top = matched.head(3)
        return jsonify({
            "recommended_courses": top['recommended_course'].tolist(),
            "top_universities": top['university'].tolist(),
            "recommended_countries": top['country'].tolist(),
            "match_score": min(100, int(gpa * 10))
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": "Profile analysis failed"}), 500

@app.route('/generate-plan', methods=['POST'])
def generate_plan():
    try:
        data = request.get_json()
        print("📩 Received plan request:", data)
        print("🔑 GEMINI_API_KEY:", GEMINI_API_KEY)

        exam = data.get("exam_type", "GRE")
        score = data.get("target_score", "300")
        weeks = data.get("weeks", "6")
        weak_areas = data.get("weak_areas", "")

        prompt = (
            f"You are an expert {exam} mentor.\n"
            f"Create a personalized plan to score {score} in {weeks} weeks.\n"
            f"Weak areas: {weak_areas or 'general preparation'}.\n"
            f"1. Motivation intro\n"
            f"2. Weekly table: Week | Focus | Hours/day\n"
            f"3. Tips & resources\n"
            f"Format clean & human-like."
        )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.7,
                "candidateCount": 1,
                "maxOutputTokens": 2048
            }
        }

        response = requests.post(url, headers=headers, json=payload, timeout=60)

        if response.status_code != 200:
            print("❌ Gemini Error Response:", response.text)
            return jsonify({"error": "Gemini API failed", "details": response.text}), 500

        gemini_response = response.json()
        print("🔁 Gemini raw response:", gemini_response)

        if 'candidates' in gemini_response and gemini_response['candidates']:
            parts = gemini_response['candidates'][0]['content']['parts']
            plan_text = parts[0]['text'] if parts and 'text' in parts[0] else "(No content)"
            return jsonify({"plan": plan_text})
        else:
            return jsonify({"error": "No insights from Gemini", "raw": gemini_response}), 500

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Failed to generate plan: {str(e)}"}), 500

@app.route('/send-email', methods=['POST'])
def send_email():
    try:
        data = request.get_json()
        to_email = data.get("to_email")
        to_name = data.get("to_name")
        plan_text = data.get("plan_text")
        exam_type = data.get("type")

        if not all([to_email, plan_text, exam_type]):
            return jsonify({"error": "Missing email parameters"}), 400

        msg = MIMEMultipart("alternative")
        msg['Subject'] = f"Your AI {exam_type} Plan"
        msg['From'] = EMAIL_USER
        msg['To'] = to_email

        html_content = f"""
        <html>
          <body>
            <p>Hello {to_name or 'Student'},</p>
            <p>Here is your personalized <b>{exam_type}</b> plan generated by ED-TECH 🤖</p>
            <pre style=\"background:#f6f6f6; padding:12px; border:1px solid #ddd;\">{plan_text}</pre>
            <p>– ED-TECH AI Team</p>
          </body>
        </html>
        """
        msg.attach(MIMEText(html_content, "html"))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.sendmail(EMAIL_USER, to_email, msg.as_string())
        server.quit()

        return jsonify({"message": "Email sent successfully"}), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": "Failed to send email"}), 500

@app.route('/submit-feedback', methods=['POST'])
def submit_feedback():
    try:
        data = request.get_json()
        print("📝 Feedback received:", data)

        feedback_entry = {
            "timestamp": firestore.SERVER_TIMESTAMP,
            "exam_type": data.get("exam_type"),
            "rating": data.get("rating"),
            "comment": data.get("comment"),
            "plan_excerpt": data.get("plan_text", "")[:100]
        }

        db.collection("feedback").add(feedback_entry)

        return jsonify({"message": "Feedback stored in Firebase"}), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": "Feedback submission failed"}), 500

@app.route('/career-insights', methods=['POST'])
def career_insights():
    try:
        data = request.get_json()
        goal = data.get("goal", "").strip().lower()

        if not goal:
            return jsonify({"error": "Career goal missing"}), 400

        prompt = (
            f"You are a career mentor.\n"
            f"Provide structured insights for the goal: '{goal}'. Include:\n"
            f"1. Career path options (step-by-step)\n"
            f"2. Important skills to learn\n"
            f"3. Study tips or certifications\n\n"
            f"Present each section clearly with bullet points."
        )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.6,
                "candidateCount": 1,
                "maxOutputTokens": 1500
            }
        }

        response = requests.post(url, headers=headers, json=payload, timeout=60)
        gemini_response = response.json()

        if 'candidates' in gemini_response:
            content = gemini_response['candidates'][0]['content']['parts'][0]['text']
            return jsonify({"insights": content})
        else:
            return jsonify({"error": "No insights found", "details": gemini_response}), 500

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": "Failed to fetch insights"}), 500

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)