"""
YouTube Authentication Helper Script.

This script runs a local server to authenticate with YouTube and generate a refresh token.
You will need to have a `client_secret.json` file in the root of the project.
You can obtain this file from the Google Cloud Console.
"""

import os
from google_auth_oauthlib.flow import InstalledAppFlow

# The SCOPES needed for uploading and managing videos.
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

def main():
    if not os.path.exists('client_secret.json'):
        print("ERROR: client_secret.json not found in the current directory.")
        print("Please create a Google Cloud Project, enable the YouTube Data API v3,")
        print("create OAuth 2.0 Client IDs (Desktop app), and download the JSON file")
        print("as 'client_secret.json'.")
        return

    print("Starting authentication flow...")
    
    flow = InstalledAppFlow.from_client_secrets_file(
        'client_secret.json', SCOPES
    )
    
    # This will open a browser window for you to log in and authorize the app.
    credentials = flow.run_local_server(port=0)

    print("\n" + "="*50)
    print("AUTHENTICATION SUCCESSFUL!")
    print("="*50)
    print("\nPlease copy the following values and add them to your GitHub Repository Secrets:\n")
    
    print(f"YOUTUBE_CLIENT_ID: {credentials.client_id}")
    print(f"YOUTUBE_CLIENT_SECRET: {credentials.client_secret}")
    print(f"YOUTUBE_REFRESH_TOKEN: {credentials.refresh_token}")
    print("\n" + "="*50)

if __name__ == '__main__':
    main()
