# Import standard Python libraries
import os       # Provides functions for interacting with the file system (like saving uploaded files)
import time     # Allows adding delays (we use this to pause between SMS sends to avoid rate limits)
import csv      # Used for reading contact data from uploaded CSV files
import requests # A library to send HTTP requests (we use this to call the Dialpad API)
import re

# Import parts of Flask (the web framework)
from flask import Flask, request, render_template, redirect, url_for, flash

from dotenv import load_dotenv
load_dotenv()  # Loads the .env file

# --- Configuration section ---

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
app = Flask(__name__)

# Configure the app to know where uploaded files go
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Secret key is required for some Flask features like flashing messages
# (Flashing is how Flask shows temporary alerts like "Upload successful" or "No file selected")
app.secret_key = os.getenv('FLASK_SECRET_KEY')


# --- Helper functions ---

def allowed_file(filename):
    """
    Checks if the uploaded file has an allowed extension (e.g. .csv).
    Returns True if valid, False otherwise.
    """
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def send_sms(sender, to, message):
    """
    Sends a single SMS message using the Dialpad API.
    
    Parameters:
        to (str): The phone number of the recipient
        message (str): The text message content
    
    Returns:
        status_code (int): HTTP status code (e.g. 200 for success, 400 for error)
        response.json() (dict): The response from Dialpad in JSON format
    """
    payload = {"to": to, "from": sender, "text": message}
    response = requests.post(URL, headers=HEADERS, json=payload)
    return response.status_code, response.json()


# --- Main route (the page people see when they visit the app) ---

@app.route("/", methods=["GET", "POST"])
def index():
    """
    This function handles both displaying the form (GET request)
    and processing form submissions (POST request).
    
    GET → Show the upload form
    POST → Handle uploaded CSV + message, send SMS messages
    """
    if request.method == "POST":
        # Get the message the user typed into the form
        message = request.form["message"]
        sender_number = request.form["sender_number"]
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

                    event_url = acr_to_url.get(event_acr)
                    catalog_url = f"catalog.{event_url}.com/user/login"

                    # Replace placeholder {name}, {username}, {password}, ... in the message with the csv row
                    personalized_msg = message.format(name=name, username=username, password=password, catalog=catalog_url, event=event)

                    # Send the SMS using our helper function
                    for phone in unique_numbers:
                        status, data = send_sms(sender_number, phone, personalized_msg)

                        # Add the result to our list (to show on the results page)
                        results.append((phone, status, data))

                        # Pause for 1 second to avoid hitting API rate limits
                        time.sleep(1)

            # After sending all SMS messages, show the results in the template
            return render_template("index.html", results=results)

    # If GET request, or if something went wrong, just render the form again
    return render_template("index.html")
    

# --- Run the app ---
if __name__ == "__main__":
    # Make sure the uploads/ folder exists before starting the app
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    # Run the Flask app in debug mode
    # Debug mode means the app restarts automatically if you change the code
    app.run(debug=True)
