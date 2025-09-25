# Import standard Python libraries
import os       # Provides functions for interacting with the file system (like saving uploaded files)
import time     # Allows adding delays (we use this to pause between SMS sends to avoid rate limits)
import csv      # Used for reading contact data from uploaded CSV files
import requests # A library to send HTTP requests (we use this to call the Dialpad API)
import re
from collections import defaultdict
import phonenumbers
import logging
from functools import wraps
import threading
import queue
import redis
from rq import Queue

# Connect to Redis (default: localhost:6379)
redis_conn = redis.Redis()
task_queue = Queue(connection=redis_conn)


# Import parts of Flask (the web framework)
from flask import Flask, request, render_template, redirect, url_for, flash, Response
from dotenv import load_dotenv
load_dotenv()  # Loads the .env file

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

from flask import Flask, request, session, redirect, url_for, render_template_string
import os

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

# --- Authentication Setup ---
# Credentials
VALID_USERNAME = os.getenv("APP_USERNAME", "admin")
VALID_PASSWORD = os.getenv("APP_PASSWORD", "mypassword")

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

@app.route("/login", methods=["GET", "POST"])
def login():
    # --- Regular form login (POST) ---
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if username == VALID_USERNAME and password == VALID_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("index"))
        else:
            flash("Invalid credentials", "danger")

    # --- Render login page ---
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out", "info")
    return redirect(url_for("login"))


# Your Dialpad API key (replace this with a real one from your Dialpad account)
API_KEY = os.getenv('DIALPAD_API_KEY')

# The Dialpad phone number you will send SMS messages from


# The Dialpad API endpoint for sending SMS messages
URL = "https://dialpad.com/api/v2/sms"

# Headers to send with every API request
# "Authorization" is how we tell Dialpad who we are (using the API key)
# "Content-Type" tells Dialpad we are sending JSON-formatted data
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

# Folder where uploaded CSV files will be temporarily stored
UPLOAD_FOLDER = "uploads"

# Allowed file types for upload (in this case, only CSV)
ALLOWED_EXTENSIONS = {"csv"}

# Create a Flask web application
# __name__ tells Flask where to look for templates and static files


# Configure the app to know where uploaded files go
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Secret key is required for some Flask features like flashing messages


# --- Helper functions ---

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def send_sms(sender, to, message):

    payload = {"to_numbers": to, "from_number": sender, "text": message}
    response = requests.post(URL, headers=HEADERS, json=payload)
    return response.status_code, response.json()

def send_bulk_sms(filepath, message, sender_number):
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    results = []
    with open(filepath, newline="") as csvfile:
        reader = csv.DictReader(csvfile)

        for row in reader:
            # --- Your current CSV parsing and SMS logic ---
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

    logging.info(f"Finished processing job for {filepath} with {len(results)} messages")
    return results


# --- Main route (the page people see when they visit the app) ---

@app.route("/", methods=["GET", "POST"])
def index():
    user = request.args.get("user")
    password = request.args.get("pass")

    if user and password:
        if user == VALID_USERNAME and password == VALID_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("index"))
        else:
            flash("Invalid credentials in URL", "danger")
            return redirect(url_for("login"))

    if not session.get("logged_in"):
        return redirect(url_for("login"))

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

            # Instead of enqueuing:
            # task_queue.enqueue(send_bulk_sms, filepath, message, sender_number)

            # Run inline:
            results = send_bulk_sms(filepath, message, sender_number)
            flash(f"Finished sending {len(results)} messages", "info")

            return redirect(url_for("index"))

    return render_template("index.html")

    
@app.route("/test")
def test():
    return "It works!"

# --- Run the app ---
if __name__ == "__main__":
    # Make sure the uploads/ folder exists before starting the app
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    # Run the Flask app in debug mode
    # Debug mode means the app restarts automatically if you change the code
    app.run()
