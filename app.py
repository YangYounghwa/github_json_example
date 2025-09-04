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

if not all([app.secret_key, GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET]):
    raise ValueError("CRITICAL ERROR: One or more environment variables (FLASK_SECRET_KEY, GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET) are missing. Please check your .env file.")

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


# -----------------------------------------------
# 2. SELECT REPOSITORY
# -----------------------------------------------

@app.route("/dashboard")
def dashboard():
    """Shows a list of the user's repositories to select from."""
    if 'github_token' not in session:
        return redirect(url_for('login'))

    headers = {"Authorization": f"Bearer {session['github_token']}"}
    # Using the REST API here is simple and efficient for getting a repo list
    repo_response = requests.get(f"{GITHUB_API_URL}/user/repos?sort=updated&per_page=20", headers=headers)
    repo_response.raise_for_status()
    repos = repo_response.json()

    return render_template('dashboard.html', repos=repos)



# -----------------------------------------------
# 3. GET RELEVANT ACTIVITY & 4. SHOW JSON
# -----------------------------------------------

@app.route("/repo/<owner>/<name>")
def show_repo_activity(owner, name):
    """Fetches activity using GraphQL and displays the raw JSON."""
    if 'github_token' not in session:
        return redirect(url_for('login'))

    headers = {"Authorization": f"Bearer {session['github_token']}"}
    
    # Define the time window for the activity search (e.g., last 30 days)
    since_date = (datetime.utcnow() - timedelta(days=30)).isoformat()

    # The GraphQL query from our plan
    graphql_query = """
    query GetDailyActivity($owner: String!, $repo: String!, $since: DateTime!) {
      repository(owner: $owner, name: $repo) {
        nameWithOwner
        pullRequests(first: 20, orderBy: {field: UPDATED_AT, direction: DESC}) {
          nodes {
            updatedAt
            title
            number
            author { login }
            comments(first: 20, since: $since) {
              nodes {
                author { login }
                bodyText
                createdAt
              }
            }
            commits(first: 20, since: $since) {
              nodes {
                commit {
                  author { name }
                  messageHeadline
                  oid
                }
              }
            }
          }
        }
      }
    }
    """

    variables = {
        "owner": owner,
        "repo": name,
        "since": since_date
    }

    # Make the GraphQL API POST request
    response = requests.post(
        f"{GITHUB_API_URL}/graphql",
        headers=headers,
        json={"query": graphql_query, "variables": variables}
    )
    response.raise_for_status()
    activity_json = response.json()
    
    # Pretty-print the JSON to be displayed in the template
    pretty_json = json.dumps(activity_json, indent=2)

    return render_template('show_json.html', repo_name=f"{owner}/{name}", json_data=pretty_json, raw_data=activity_json)







if __name__ == "__main__":
    # Use 0.0.0.0 to make it accessible on your local network
    app.run(host="0.0.0.0", port=5000, debug=True)