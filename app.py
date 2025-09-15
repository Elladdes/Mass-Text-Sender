import os
import time
import csv
import requests
from flask import Flask, request, render_template, redirect, url_for, flash

# --- Config ---
API_KEY = "your_api_key_here"   # Replace with real Dialpad API key
DIALPAD_NUMBER = "+15551234567" # Your Dialpad number
URL = "https://api.dialpad.com/v2/sms"
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"csv"}

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.secret_key = "supersecret"  # Needed for flashing messages


# --- Helpers ---
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def send_sms(to, message):
    payload = {"to": to, "from": DIALPAD_NUMBER, "text": message}
    response = requests.post(URL, headers=HEADERS, json=payload)
    return response.status_code, response.json()


# --- Routes ---
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        message = request.form["message"]

        # Check file upload
        if "file" not in request.files:
            flash("No file part")
            return redirect(request.url)
        file = request.files["file"]

        if file.filename == "":
            flash("No selected file")
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
            file.save(filepath)

            results = []
            with open(filepath, newline="") as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    name = row.get("name", "").strip()
                    phone = row.get("phone", "").strip()

                    # Replace placeholders
                    personalized_msg = message.replace("{name}", name)

                    status, data = send_sms(phone, personalized_msg)
                    results.append((phone, status, data))
                    time.sleep(1)  # prevent hitting rate limits

            return render_template("index.html", results=results)

    return render_template("index.html")
    

if __name__ == "__main__":
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    app.run(debug=True)
