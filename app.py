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
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change_this")

# --- Authentication Setup ---
VALID_USERNAME = os.getenv("APP_USERNAME")
VALID_PASSWORD = os.getenv("APP_PASSWORD")

def login_required(f):
    """Decorator to protect routes that require login."""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if username == VALID_USERNAME and password == VALID_PASSWORD:
            session["logged_in"] = True
            flash("Login successful!", "success")
            return redirect(url_for("index"))
        else:
            flash("Invalid credentials", "danger")
    return render_template_string("""
        <h2>Login</h2>
        <form method="post">
            <input type="text" name="username" placeholder="Username" required><br><br>
            <input type="password" name="password" placeholder="Password" required><br><br>
            <button type="submit">Login</button>
        </form>
    """)


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


# Your Dialpad API key (replace this with a real one from your Dialpad account)
API_KEY = os.getenv('DIALPAD_API_KEY')

# The Dialpad phone number you will send SMS messages from


# The Dialpad API endpoint for sending SMS messages
URL = "https://api.dialpad.com/v2/sms"

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
# (Flashing is how Flask shows temporary alerts like "Upload successful" or "No file selected")
app.secret_key = os.getenv('FLASK_SECRET_KEY')


# --- Helper functions ---

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def send_sms(sender, to, message):

    payload = {"to": to, "from": sender, "text": message}
    response = requests.post(URL, headers=HEADERS, json=payload)
    return response.status_code, response.json()


# --- Main route (the page people see when they visit the app) ---

@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
        # Get the message the user typed into the form
        message = request.form["message"]
        sender_number = request.form["sender_number"]
        if not sender_number:
            flash("Sender number is required.")
            return redirect(request.url)
        # Check that a file was actually uploaded
        if "file" not in request.files:
            flash("No file part")  # Show an alert message on the page
            return redirect(request.url)  # Reload the form

        file = request.files["file"]

        # If the user submitted without choosing a file
        if file.filename == "":
            flash("No selected file")
            return redirect(request.url)

        # If the file exists and has a valid extension (CSV)
        if file and allowed_file(file.filename):
            # Save the uploaded file into the uploads/ folder
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
            file.save(filepath)

            results = []  # Store results for each SMS (phone, status, response)

            # Open the uploaded CSV file
            with open(filepath, newline="") as csvfile:
                reader = csv.DictReader(csvfile)  
                # DictReader reads each row as a dictionary with keys = column names

                for row in reader:
                    #get event name, acr and the event attendee name
                    event = row.get("Event: Event Name", "").strip()
                    event = re.sub(r"-\d+", "", event) #American Automotive Summit-2025 -> American Automotive Summit
                    event_acr = row.get("Event Acronym", "").strip() #used to get the url for catalog url
                    name = row.get("Event Attendee: Event Attendee Name", "").strip()

                    #get all phone numebers
                    phone = row.get("Phone", "").strip()
                    mobile = row.get("Mobile", "").strip()
                    zoom_phone = row.get("Zoom Phone", "").strip()
                    zoom_mobile_phone = row.get("Zoom Mobile Phone", "").strip()

                    #get username and password from form
                    username = row.get("Username", "").strip()
                    password = row.get("Password", "").strip()

                    all_numbers = [phone, mobile, zoom_phone, zoom_mobile_phone]

                    #remove duplicate/empty numbers
                    unique_numbers = list(set(num for num in all_numbers if num))

                    #match event acronym to event url

                    event_url = acr_to_url.get(event_acr)
                    if not event_url:
                        event_url = "amdsummit"
                    catalog_url = f"catalog.{event_url}.com/user/login"

                    # Replace placeholder {name}, {username}, {password}, ... in the message with the csv row
                    
                    placeholders = defaultdict(str, {
                        "name": name, "username": username,
                        "password": password, "catalog": catalog_url,
                        "event": event
                    })
                    personalized_msg = message.format_map(placeholders)

                    #send sms to all numbers through for loop
                    for phone in unique_numbers:
                        #normalize all phone numbers
                        try:
                            parsed = phonenumbers.parse(phone, "US")
                            phone = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
                        except phonenumbers.NumberParseException as e:
                            logging.warning(f"Invalid phone number '{phone}' for {name}: {e}")
                            continue


                        # Send the SMS using our helper function
                        status, data = send_sms(sender_number, phone, personalized_msg)

                        # Add the result to our list (to show on the results page)
                        results.append((phone, status, data))

                        # Pause for half a second to avoid hitting API rate limits
                        time.sleep(0.50)

            # After sending all SMS messages, show the results in the template
            return render_template("index.html", results=results)

    # If GET request, or if something went wrong, just render the form again
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
