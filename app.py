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
# In app.py, replace the whole function with this one.

@app.route("/repo/<owner>/<name>")
def show_repo_activity(owner, name):
    """Fetches activity using GraphQL, filters it, and displays the relevant JSON."""
    if 'github_token' not in session:
        return redirect(url_for('login'))

    headers = {"Authorization": f"Bearer {session['github_token']}"}
    
    # Define the time window for the activity search (e.g., last 30 days)
    # We use this for filtering *after* the API call
    since_datetime = datetime.utcnow() - timedelta(days=30)

    # 1. THE CORRECTED GRAPHQL QUERY
    # We removed the invalid 'since' arguments from comments and commits.
    graphql_query = """
    query GetRecentActivity($owner: String!, $repo: String!) {
      repository(owner: $owner, name: $repo) {
        nameWithOwner
        pullRequests(first: 30, orderBy: {field: UPDATED_AT, direction: DESC}) {
          nodes {
            updatedAt
            createdAt
            title
            number
            author { login }
            comments(last: 50) {
              nodes {
                author { login }
                bodyText
                createdAt
              }
            }
            commits(last: 50) {
              nodes {
                commit {
                  author { name }
                  messageHeadline
                  oid
                  committedDate
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
        "repo": name
    }

    response = requests.post(
        f"{GITHUB_API_URL}/graphql",
        headers=headers,
        json={"query": graphql_query, "variables": variables}
    )
    response.raise_for_status()
    raw_data = response.json()

    # If the API itself returned errors, display them.
    if "errors" in raw_data:
        pretty_json = json.dumps(raw_data, indent=2)
        return render_template('show_json.html', repo_name=f"{owner}/{name}", json_data=pretty_json)

    # 2. FILTER THE RESULTS IN PYTHON
    filtered_activity = []
    all_pull_requests = raw_data.get("data", {}).get("repository", {}).get("pullRequests", {}).get("nodes", [])

    for pr in all_pull_requests:
        # The `updatedAt` field is a string, so we need to parse it to a datetime object
        pr_updated_at = datetime.fromisoformat(pr['updatedAt'].replace('Z', '+00:00'))
        
        # Only process PRs that have been updated within our time window
        if pr_updated_at >= since_datetime:
            
            # Filter comments for this PR
            relevant_comments = []
            for comment in pr["comments"]["nodes"]:
                comment_created_at = datetime.fromisoformat(comment['createdAt'].replace('Z', '+00:00'))
                if comment_created_at >= since_datetime:
                    relevant_comments.append(comment)
            
            # Filter commits for this PR
            relevant_commits = []
            for commit_node in pr["commits"]["nodes"]:
                commit_date = datetime.fromisoformat(commit_node['commit']['committedDate'].replace('Z', '+00:00'))
                if commit_date >= since_datetime:
                    relevant_commits.append(commit_node)
            
            # Rebuild the PR object with only the filtered data
            pr["comments"]["nodes"] = relevant_comments
            pr["commits"]["nodes"] = relevant_commits
            filtered_activity.append(pr)

    # Prepare the final, filtered data for display
    final_data_to_display = {
        "info": f"Showing activity since {since_datetime.isoformat()}",
        "filteredPullRequests": filtered_activity
    }
    pretty_json = json.dumps(final_data_to_display, indent=2)

    return render_template('show_json.html', repo_name=f"{owner}/{name}", json_data=pretty_json)
@app.route("/logout")
def logout():
    """Clears the session and redirects to the homepage."""
    session.clear()
    return redirect(url_for('index'))





if __name__ == "__main__":
    # Use 0.0.0.0 to make it accessible on your local network
    app.run(host="0.0.0.0", port=5000, debug=True)