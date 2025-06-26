from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from flask import Flask, request
import os
from dotenv import load_dotenv
from jenkins_utils import (
    get_all_jobs,
    trigger_job,
    get_last_build_console_output,
    extract_google_doc_link,
    wait_for_build_to_complete
)
import time
import base64
import requests
from requests.auth import HTTPBasicAuth

load_dotenv()
print("JENKINS_URL:", os.getenv("JENKINS_URL"))

app = App(
    token=os.getenv("SLACK_BOT_TOKEN"),
    signing_secret=os.getenv("SLACK_SIGNING_SECRET")
)

flask_app = Flask(__name__)
handler = SlackRequestHandler(app)

@app.command("/runjenkinsjob")
def handle_command(ack, body, client):
    ack()
    user_id = body["user_id"]
    channel_id = body["channel_id"]

    client.chat_postEphemeral(channel=channel_id, user=user_id, text="Loading Jenkins jobs...")

    jobs = get_all_jobs()
    options = [{"text": {"type": "plain_text", "text": job}, "value": job} for job in jobs]

    client.chat_postEphemeral(
        channel=channel_id,
        user=user_id,
        blocks=[
            {
                "type": "section",
                "block_id": "job_dropdown",
                "text": {"type": "mrkdwn", "text": "Select a Jenkins job to run:"},
                "accessory": {
                    "type": "static_select",
                    "action_id": "job_selected",
                    "placeholder": {"type": "plain_text", "text": "Choose a job"},
                    "options": options
                }
            }
        ]
    )

@app.action("job_selected")
def handle_job_selection(ack, body, client, respond):
    ack()
    selected_job = body["actions"][0]["selected_option"]["value"]
    user_id = body["user"]["id"]
    channel_id = body["channel"]["id"]

    if selected_job == "jenkins-pipeline":
        respond({
            "text": f"Job *{selected_job}* requires files. Please upload the following files here:\n• INPUT_XLSX (.xlsx)\n• SERVICE_ACCOUNT_JSON (.json)\nThen click the button below to trigger.",
            "blocks": [
                {"type": "section", "text": {"type": "mrkdwn", "text": f"*{selected_job}* needs file inputs. Please upload both files here."}},
                {"type": "actions", "elements": [
                    {"type": "button", "text": {"type": "plain_text", "text": "✅ I have uploaded files, Run Job"},
                     "style": "primary", "action_id": "confirm_file_upload", "value": selected_job}
                ]}
            ]
        })
    else:
        respond({
            "text": f"You selected *{selected_job}*. Do you want to trigger it?",
            "blocks": [
                {"type": "section", "text": {"type": "mrkdwn", "text": f"You selected *{selected_job}*. Run this job?"}},
                {"type": "actions", "elements": [
                    {"type": "button", "text": {"type": "plain_text", "text": "Yes, Run it"}, "style": "primary", "action_id": "confirm_run", "value": selected_job}
                ]}
            ]
        })

@app.action("confirm_run")
def handle_job_run(ack, body, client):
    ack()
    job_name = body["actions"][0]["value"]
    channel = body["channel"]["id"]
    
    client.chat_postMessage(channel=channel, text=f"Triggering *{job_name}*...")

    success = trigger_job(job_name)
    
    if not success:
        client.chat_postMessage(channel=channel, text=f":x: Failed to trigger job `{job_name}`.")
        return

    client.chat_postMessage(channel=channel, text="⏳ Waiting for job to complete...")

    build_number = wait_for_build_to_complete(job_name)

    if build_number is None:
        client.chat_postMessage(channel=channel, text=f":x: Job `{job_name}` timed out while waiting for completion.")
        return

    output = get_last_build_console_output(job_name)
    link = extract_google_doc_link(output)

    if link:
        client.chat_postMessage(channel=channel, text=f":white_check_mark: Job completed! Here's your Google Doc link:\n{link}")
    else:
        client.chat_postMessage(channel=channel, text=":warning: Job ran, but no Google Doc link was found.")

def download_file(file_info, token):
    url = file_info["url_private"]
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.get(url, headers=headers)
    return res.content

@app.action("confirm_file_upload")
def handle_file_job(ack, body, client):
    ack()
    user_id = body["user"]["id"]
    channel_id = body["channel"]["id"]
    job_name = body["actions"][0]["value"]

    client.chat_postMessage(channel=channel_id, text=f"Fetching uploaded files for *{job_name}*...")

    files = client.files_list(user=user_id)["files"]
    xlsx_file = next((f for f in files if f["filetype"] == "xlsx"), None)
    json_file = next((f for f in files if f["filetype"] == "json"), None)

    if not xlsx_file or not json_file:
        client.chat_postMessage(channel=channel_id, text="❌ Missing required files. Please upload both `.xlsx` and `.json` files.")
        return

    xlsx_bytes = download_file(xlsx_file, os.getenv("SLACK_BOT_TOKEN"))
    json_bytes = download_file(json_file, os.getenv("SLACK_BOT_TOKEN"))

    xlsx_b64 = base64.b64encode(xlsx_bytes).decode("utf-8")
    json_b64 = base64.b64encode(json_bytes).decode("utf-8")

    from jenkins_utils import get_crumb
    headers = get_crumb()
    headers["Content-Type"] = "application/x-www-form-urlencoded"

    payload = {
        "json": f"""{{"parameter": [
            {{"name":"INPUT_XLSX","file":"input.xlsx","base64":"{xlsx_b64}"}},
            {{"name":"SERVICE_ACCOUNT_JSON","file":"service-account.json","base64":"{json_b64}"}}
        ]}}"""
    }

    res = requests.post(
        f"{os.getenv('JENKINS_URL')}/job/{job_name}/build",
        headers=headers,
        auth=HTTPBasicAuth(os.getenv("JENKINS_USER"), os.getenv("JENKINS_API_TOKEN")),
        data=payload
    )

    if res.status_code == 201:
        client.chat_postMessage(channel=channel_id, text=f"✅ Job *{job_name}* triggered successfully with files.")
    else:
        client.chat_postMessage(channel=channel_id, text=f"❌ Failed to trigger job. Status code: {res.status_code}")

@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)

if __name__ == "__main__":
    flask_app.run(port=5000)
