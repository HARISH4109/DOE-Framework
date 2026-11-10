import os
import sys
from pathlib import Path

# Allow oauthlib to accept modified/relaxed scopes from Google consent
os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/documents'
]

def main():
    credentials_path = Path("credentials.json")
    if not credentials_path.exists():
        print("Error: credentials.json not found", flush=True)
        sys.exit(1)
        
    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
    auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
    
    tmp_dir = Path(".tmp")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    (tmp_dir / "auth_url.txt").write_text(auth_url, encoding="utf-8")
    
    print("\n--- GOOGLE AUTHORIZATION REQUIRED ---", flush=True)
    print("Please visit the following URL in your browser to authorize the application:", flush=True)
    print(auth_url, flush=True)
    print("⚠️ IMPORTANT: Check the boxes for 'Google Docs' and 'Google Drive' (or 'Select all') on the consent screen!", flush=True)
    print("--------------------------------------\n", flush=True)
    
    # Run the local server to catch the redirect and open browser
    creds = flow.run_local_server(port=0, open_browser=True)
    
    with open("token.json", "w") as f:
        f.write(creds.to_json())
    print("\n✅ Authentication successful! token.json saved.", flush=True)

if __name__ == "__main__":
    main()
