import requests
from requests.auth import HTTPBasicAuth
import os
from dotenv import load_dotenv
import time



load_dotenv()  # <-- This is CRUCIAL

JENKINS_URL = os.getenv("JENKINS_URL")
JENKINS_USER = os.getenv("JENKINS_USER")
JENKINS_API_TOKEN = os.getenv("JENKINS_API_TOKEN")

def get_crumb():
    url = f"{JENKINS_URL}/crumbIssuer/api/json"
    res = requests.get(url, auth=HTTPBasicAuth(JENKINS_USER, JENKINS_API_TOKEN))
    res.raise_for_status()
    data = res.json()
    return {data['crumbRequestField']: data['crumb']}

def get_all_jobs():
    headers = get_crumb()
    url = f"{JENKINS_URL}/api/json"
    res = requests.get(url, auth=HTTPBasicAuth(JENKINS_USER, JENKINS_API_TOKEN), headers=headers)
    res.raise_for_status()
    jobs = res.json().get("jobs", [])
    return [job['name'] for job in jobs]

def trigger_job(job_name):
    headers = get_crumb()
    url = f"{JENKINS_URL}/job/{job_name}/build"
    res = requests.post(url, auth=HTTPBasicAuth(JENKINS_USER, JENKINS_API_TOKEN), headers=headers)
    return res.status_code == 201

def get_last_build_console_output(job_name):
    url = f"{JENKINS_URL}/job/{job_name}/lastBuild/consoleText"
    res = requests.get(url, auth=HTTPBasicAuth(JENKINS_USER, JENKINS_API_TOKEN))
    return res.text

def extract_google_doc_link(console_output):
    import re
    match = re.search(r"https://docs\.google\.com/[^\s]+", console_output)
    return match.group(0) if match else None


def wait_for_build_to_complete(job_name, timeout=180, interval=5):
    """
    Polls Jenkins to wait until the latest build of `job_name` completes.
    Returns the build number once done, or None if timed out.
    """
    build_url = f"{JENKINS_URL}/job/{job_name}/lastBuild/api/json"

    for _ in range(int(timeout / interval)):
        res = requests.get(build_url, auth=HTTPBasicAuth(JENKINS_USER, JENKINS_API_TOKEN))
        if res.status_code != 200:
            time.sleep(interval)
            continue
        data = res.json()
        if not data.get("building", True):
            return data.get("number")
        time.sleep(interval)

    return None  # Timed out
