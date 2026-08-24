import os
import glob
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

def main():
    root = Path(__file__).resolve().parent.parent
    
    # 1. Search for any client_secret*.json file
    secret_files = list(root.glob("client_secret*.json")) + list(root.glob("*.json"))
    valid_secret_file = None
    for f in secret_files:
        if "client_secret" in f.name.lower() or "oauth" in f.name.lower():
            valid_secret_file = f
            break
            
    flow = None
    if valid_secret_file and valid_secret_file.exists():
        print(f"Found credential file: {valid_secret_file.name}")
        flow = InstalledAppFlow.from_client_secrets_file(str(valid_secret_file), SCOPES)
    else:
        print("\n" + "="*50)
        print("YouTube Authentication Setup")
        print("="*50)
        print("No 'client_secret.json' file found.")
        print("You can either:")
        print("1. Download 'client_secret.json' from Google Cloud Console and place it in this folder.")
        print("2. Or enter your OAuth Client ID and Client Secret directly below:\n")
        
        client_id = input("Enter YouTube OAuth Client ID (or press Enter to exit): ").strip()
        if not client_id:
            print("Authentication cancelled.")
            return
            
        client_secret = input("Enter YouTube OAuth Client Secret: ").strip()
        if not client_secret:
            print("Authentication cancelled.")
            return
            
        client_config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"]
            }
        }
        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)

    print("\nStarting authentication flow... Opening browser window...")
    credentials = flow.run_local_server(port=0)

    print("\n" + "="*50)
    print("✅ AUTHENTICATION SUCCESSFUL!")
    print("="*50)
    
    # Auto-save to .env
    env_path = root / ".env"
    env_lines = []
    if env_path.exists():
        env_lines = env_path.read_text(encoding="utf-8").splitlines()
        
    env_dict = {}
    for line in env_lines:
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            env_dict[k.strip()] = v.strip()
            
    env_dict["YOUTUBE_CLIENT_ID"] = credentials.client_id
    env_dict["YOUTUBE_CLIENT_SECRET"] = credentials.client_secret
    env_dict["YOUTUBE_REFRESH_TOKEN"] = credentials.refresh_token
    
    new_env_content = "\n".join([f"{k}={v}" for k, v in env_dict.items()]) + "\n"
    env_path.write_text(new_env_content, encoding="utf-8")
    print(f"💾 Saved YouTube credentials automatically to: {env_path}")

    print("\nCopy these values to your GitHub Repository Secrets (Settings ➔ Secrets ➔ Actions):")
    print(f"YOUTUBE_CLIENT_ID: {credentials.client_id}")
    print(f"YOUTUBE_CLIENT_SECRET: {credentials.client_secret}")
    print(f"YOUTUBE_REFRESH_TOKEN: {credentials.refresh_token}")
    print("="*50 + "\n")

if __name__ == '__main__':
    main()
