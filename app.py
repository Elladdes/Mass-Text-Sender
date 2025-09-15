import os
import time
import csv
import requests
import re
from collections import defaultdict
import phonenumbers
import logging
from flask import Flask, request, render_template, redirect, url_for, flash, session, render_template_string
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change_this")

USERNAME = os.getenv("APP_USERNAME", "admin")
PASSWORD = os.getenv("APP_PASSWORD", "secret")

acr_to_url = {
    "AAS": "usautosummit",
    "AMD": "amdsummit",
    "AAD": "aadsummit",
    "AMS": "manusummit",
    "BIO": "biomanamerica",
    "ASC": "supplychainus",
    "PMOS": "posummit",
    "APS": "uspacksummit",
    "CIO": "cioamerica",
    "FMS": "foodmansummit",
    "CMS": "chemmansummit"
}

logging.basicConfig(level=logging.INFO, filename="sms_errors.log",
                    format="%(asctime)s - %(levelname)s - %(message)s")

# --- Login routes ---
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form["username"] == USERNAME and request.form["password"] == PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("index"))
        return "Invalid credentials", 401
    return render_template_string("""
        <form method="post">
          <input type="text" name="username" placeholder="Username"><br>
          <input type="password" name="password" placeholder="Password"><br>
          <button type="submit">Login</button>
        </form>
    """)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.before_request
def require_login():
    if request.endpoint not in ("login", "static") and not session.get("logged_in"):
        return redirect(url_for("login"))

# --- Config ---
API_KEY = os.getenv("DIALPAD_API_KEY")
URL = "https://api.dialpad.com/v2/sms"
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"csv"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# --- Helper functions ---
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def send_sms(sender, to, message):
    payload = {"to": to, "from": sender, "text": message}
    response = requests.post(URL, headers=HEADERS, json=payload)
    return response.status_code, response.json()

# --- Main route ---
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        message = request.form["message"]
        sender_number = request.form["sender_number"]
        if not sender_number:
            flash("Sender number is required.")
            return redirect(request.url)

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
                    event = row.get("Event: Event Name", "").strip()
                    event = re.sub(r"-\d+", "", event)
                    event_acr = row.get("Event Acronym", "").strip()
                    name = row.get("Event Attendee: Event Attendee Name", "").strip()

                    phone = row.get("Phone", "").strip()
                    mobile = row.get("Mobile", "").strip()
                    zoom_phone = row.get("Zoom Phone", "").strip()
                    zoom_mobile_phone = row.get("Zoom Mobile Phone", "").strip()

                    username = row.get("Username", "").strip()
                    password = row.get("Password", "").strip()

                    all_numbers = [phone, mobile, zoom_phone, zoom_mobile_phone]
                    unique_numbers = list(set(num for num in all_numbers if num))

                    event_url = acr_to_url.get(event_acr, "amdsummit")
                    catalog_url = f"catalog.{event_url}.com/user/login"

                    placeholders = defaultdict(str, {
                        "name": name, "username": username,
                        "password": password, "catalog": catalog_url,
                        "event": event
                    })
                    personalized_msg = message.format_map(placeholders)

                    for phone in unique_numbers:
                        try:
                            parsed = phonenumbers.parse(phone, "US")
                            phone = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
                        except phonenumbers.NumberParseException as e:
                            logging.warning(f"Invalid phone number '{phone}' for {name}: {e}")
                            continue

                        status, data = send_sms(sender_number, phone, personalized_msg)
                        results.append((phone, status, data))
                        time.sleep(0.50)

            return render_template("index.html", results=results)

    return render_template("index.html")

# --- Run app ---
if __name__ == "__main__":
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    app.run(debug=True)
