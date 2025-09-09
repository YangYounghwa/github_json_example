import os
import requests
import json
from datetime import datetime, timedelta, timezone
from flask import Flask, jsonify, request, redirect, url_for, session, render_template
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# --- Configuration and Sanity Check ---
app.secret_key = os.getenv("FLASK_SECRET_KEY")
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")

if not all([app.secret_key, GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET]):
    raise ValueError("CRITICAL ERROR: One or more environment variables are missing. Please check your .env file.")

# --- GitHub API Constants ---
GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_URL = "https://api.github.com"

# =============================================================================
# AUTHENTICATION ROUTES
# =============================================================================

@app.route("/")
def index():
    """Homepage: Shows login link if not authenticated."""
    return render_template('index.html')

@app.route("/login")
def login():
    """Redirects user to GitHub for authorization."""
    if 'github_token' not in session:
        scope = "repo"
        return redirect(f"{GITHUB_AUTH_URL}?client_id={GITHUB_CLIENT_ID}&scope={scope}")
    return redirect(url_for('dashboard'))

@app.route("/logout")
def logout():
    """Clears the session and redirects to the homepage."""
    session.clear()
    return redirect(url_for('index'))

@app.route("/github/callback")
def github_callback():
    """Handles the callback from GitHub after authorization."""
    code = request.args.get("code")
    if not code:
        return "Error: No code provided.", 400

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

# =============================================================================
# CORE APPLICATION ROUTES
# =============================================================================

@app.route("/dashboard")
def dashboard():
    """Shows a list of the user's repositories to select from."""
    if 'github_token' not in session:
        return redirect(url_for('login'))

    headers = {"Authorization": f"Bearer {session['github_token']}"}
    repo_response = requests.get(f"{GITHUB_API_URL}/user/repos?sort=updated&per_page=30", headers=headers)
    repo_response.raise_for_status()
    repos = repo_response.json()
    return render_template('dashboard.html', repos=repos)

@app.route("/repo/<owner>/<name>/branch-diffs")
def show_branch_diffs(owner, name):
    if 'github_token' not in session:
        return redirect(url_for('login'))

    headers = {"Authorization": f"Bearer {session['github_token']}"}
    repo_url = f"{GITHUB_API_URL}/repos/{owner}/{name}"
    
    # This dictionary will hold the raw data if JSON format is requested
    raw_api_responses = {}

    try:
        repo_info_res = requests.get(repo_url, headers=headers)
        repo_info_res.raise_for_status()
        repo_info_data = repo_info_res.json()
        raw_api_responses['repository_info'] = repo_info_data
        default_branch = repo_info_data['default_branch']

        branches_res = requests.get(f"{repo_url}/branches", headers=headers)
        branches_res.raise_for_status()
        branches_data = branches_res.json()
        raw_api_responses['branches_list'] = branches_data
        
        raw_api_responses['comparisons'] = {}
        branch_diffs = {}

        for branch in branches_data:
            branch_name = branch['name']
            #if branch_name == default_branch:
            #    continue

            # Compare: AHEAD
            ahead_url = f"{repo_url}/compare/{default_branch}...{branch_name}"
            ahead_res = requests.get(ahead_url, headers=headers)
            ahead_res.raise_for_status()
            ahead_data = ahead_res.json()
            raw_api_responses['comparisons'][f"{default_branch}_vs_{branch_name}"] = ahead_data

            # Compare: BEHIND
            behind_url = f"{repo_url}/compare/{branch_name}...{default_branch}"
            behind_res = requests.get(behind_url, headers=headers)
            behind_res.raise_for_status()
            behind_data = behind_res.json()
            raw_api_responses['comparisons'][f"{branch_name}_vs_{default_branch}"] = behind_data
        
        # NEW LOGIC: Check for the format parameter
        if request.args.get('format') == 'json':
            # jsonify correctly sets the Content-Type header to application/json
            return jsonify(raw_api_responses)

        # --- If not returning JSON, process the data for the HTML template ---
        for branch_name, ahead_data in raw_api_responses['comparisons'].items():
            if not branch_name.startswith(default_branch): continue
            
            current_branch_name = branch_name.split('_vs_')[1]
            branch_diffs[current_branch_name] = {"ahead_commits": [], "behind_commits": []}
            
            for commit in ahead_data.get('commits', []):
                branch_diffs[current_branch_name]["ahead_commits"].append({
                    "sha": commit['sha'][:7], "full_sha": commit['sha'],
                    "message": commit['commit']['message'].split('\n')[0],
                    "author": commit['commit']['author']['name']
                })
            
            behind_data = raw_api_responses['comparisons'][f"{current_branch_name}_vs_{default_branch}"]
            for commit in behind_data.get('commits', []):
                 branch_diffs[current_branch_name]["behind_commits"].append({
                    "sha": commit['sha'][:7], "full_sha": commit['sha'],
                    "message": commit['commit']['message'].split('\n')[0],
                    "author": commit['commit']['author']['name']
                })

    except requests.exceptions.HTTPError as e:
        return jsonify({"error": str(e)}), 500 if request.args.get('format') == 'json' else (f"An API error occurred: {e}", 500)

    return render_template('branch_diffs.html',
                           repo_name=f"{owner}/{name}", owner=owner, name=name,
                           diffs=branch_diffs, default_branch=default_branch)

@app.route("/repo/<owner>/<name>/commit/<sha>")
def show_commit_detail(owner, name, sha):
    if 'github_token' not in session:
        return redirect(url_for('login'))

    headers = {"Authorization": f"Bearer {session['github_token']}"}
    commit_url = f"{GITHUB_API_URL}/repos/{owner}/{name}/commits/{sha}"

    try:
        response = requests.get(commit_url, headers=headers)
        response.raise_for_status()
        commit_data = response.json()

        # NEW LOGIC: Check for the format parameter
        if request.args.get('format') == 'json':
            return jsonify(commit_data)

        # --- If not returning JSON, process the data for the HTML template ---
        commit_details = {
            "sha": commit_data['sha'], "author": commit_data['commit']['author']['name'],
            "date": commit_data['commit']['author']['date'], "message": commit_data['commit']['message'],
            "files": []
        }
        for file in commit_data.get('files', []):
            commit_details['files'].append({
                "filename": file['filename'], "status": file['status'],
                "additions": file['additions'], "deletions": file['deletions'],
                "patch": file.get('patch', 'No patch available.')
            })

    except requests.exceptions.HTTPError as e:
         return jsonify({"error": str(e)}), 500 if request.args.get('format') == 'json' else (f"An API error occurred: {e}", 500)

    return render_template('commit_detail.html',
                           repo_name=f"{owner}/{name}", owner=owner, name=name,
                           commit=commit_details)
    
    
    
@app.route("/repo/<owner>/<name>/branch-summary")
def show_branch_summary(owner, name):
    if 'github_token' not in session:
        return redirect(url_for('login'))

    headers = {"Authorization": f"Bearer {session['github_token']}"}

    try:
        # STEP 1: Make a simple REST call to get the default branch name first.
        repo_url = f"{GITHUB_API_URL}/repos/{owner}/{name}"
        repo_info_res = requests.get(repo_url, headers=headers)
        repo_info_res.raise_for_status()
        default_branch = repo_info_res.json()['default_branch']

        # STEP 2: Use the corrected GraphQL query.
        graphql_query = """
        query GetBranchTimestamps($owner: String!, $repo: String!, $defaultBranch: String!) {
          repository(owner: $owner, name: $repo) {
            refs(refPrefix: "refs/heads/", first: 100, orderBy: {field: TAG_COMMIT_DATE, direction: DESC}) {
              nodes {
                name
                target {
                  ... on Commit {
                    committedDate
                  }
                }
                compare(headRef: $defaultBranch) {
                  commits(last: 1) {
                    nodes {
                      committedDate
                    }
                  }
                }
              }
            }
          }
        }
        """
        # STEP 3: Pass the default_branch name as a variable to the query.
        variables = {
            "owner": owner, 
            "repo": name,
            "defaultBranch": default_branch
        }
    
        response = requests.post(
            f"{GITHUB_API_URL}/graphql",
            headers=headers,
            json={"query": graphql_query, "variables": variables}
        )
        response.raise_for_status()
        raw_data = response.json()

        if "errors" in raw_data:
            # We now print the full error for better debugging
            return f"GraphQL Error: {raw_data['errors']}", 500

        # Process the raw data (this logic remains the same)
        branch_list = []
        refs = raw_data.get("data", {}).get("repository", {}).get("refs", {}).get("nodes", [])
        
        for ref in refs:
            latest_commit_date = ref.get("target", {}).get("committedDate")
            first_commit_nodes = ref.get("compare", {}).get("commits", {}).get("nodes", [])
            first_commit_date = None
            if first_commit_nodes:
                first_commit_date = first_commit_nodes[0].get("committedDate")

            branch_list.append({
                "name": ref['name'],
                "latest_change": latest_commit_date,
                "first_change": first_commit_date or latest_commit_date 
            })

    except requests.exceptions.HTTPError as e:
        return f"An API error occurred: {e}", 500

    return render_template('branch_summary.html', 
                           repo_name=f"{owner}/{name}", 
                           branches=branch_list)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)