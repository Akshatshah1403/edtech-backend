import os
import json
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables from .env (if exists)
load_dotenv()

# Initialize Firebase
if not firebase_admin._apps:
    if os.getenv("FIREBASE_CREDENTIALS_JSON"):
        # On Render or using env
        firebase_dict = json.loads(os.getenv("FIREBASE_CREDENTIALS_JSON"))
        cred = credentials.Certificate(firebase_dict)
    else:
        # Local file fallback
        cred = credentials.Certificate("firebase-key.json")
    firebase_admin.initialize_app(cred)

# Firestore client
db = firestore.client()

# Test write & read
try:
    doc_ref = db.collection("testCollection").document("testDocument")
    doc_ref.set({
        "message": "✅ Firebase is working!",
        "timestamp": datetime.utcnow().isoformat()
    })

    # Read it back
    doc = doc_ref.get()
    if doc.exists:
        print("✅ SUCCESS: Document written and read successfully.")
        print("📄 Data:", doc.to_dict())
    else:
        print("❌ FAIL: Document not found.")
except Exception as e:
    print("🔥 ERROR:", str(e))
