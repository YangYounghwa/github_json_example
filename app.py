import os
import requests
import json
from datetime import datetime, timedelta
from flask import Flask, request, redirect, url_for, session, render_template

from dotenv import load_dotenv



load_dotenv()

app= Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")



GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
# GITHUB_REDIRECT_URI = os.getenv("GITHUB_REDIRECT_URI")
GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_URL = "https://api.github.com"


@app.route("/")
def index():
    """Homepage : Shows login link if not authenticated."""
    if 'github_token' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route("/login")
def login():
    """Redirects user to GitHub login page."""
    scope = "repo"
    return redirect(f"{GITHUB_AUTH_URL}?client_id={GITHUB_CLIENT_ID}&scope={scope}")



@app.route("/github/callback")
def github_callback():
    """Handles the callback from GitHub after authorization."""
    code = request.args.get("code")
    if not code:
        return "Error: No code provided.", 400

    # Exchange the temporary code for an access token
    token_response = requests.post(
        GITHUB_TOKEN_URL,
        headers={"Accept": "application/json"},
        json={
            "client_id": GITHUB_CLIENT_ID,
            "client_secret": GITHUB_CLIENT_SECRET,
            "code": code,
        },
    )
    token_response.raise_for_status()
    session['github_token'] = token_response.json()['access_token']

    return redirect(url_for('dashboard'))
