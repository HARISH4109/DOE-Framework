import os
import sys
from pathlib import Path
import requests
from dotenv import load_dotenv

# Load environment variables from workspace root
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(WORKSPACE_ROOT / ".env")

api_key = os.getenv("NVIDIA_NIM") or os.getenv("NVIDIA_API_KEY")
url = os.getenv("NVIDIA_API_URL", "https://integrate.api.nvidia.com/v1/models")

if not api_key:
    print("Error: NVIDIA_NIM or NVIDIA_API_KEY not found in environment.")
    sys.exit(1)

headers = {
    "Authorization": f"Bearer {api_key}"
}

try:
    r = requests.get(url, headers=headers, timeout=30)
    print(f"Status Code: {r.status_code}")
    if r.status_code == 200:
        models = r.json().get('data', [])
        print("\nAvailable NVIDIA NIM Models:")
        for m in models:
            mid = m.get('id', 'unknown')
            print(f"- {mid}")
    else:
        print(f"Error ({r.status_code}): {r.text}")
except Exception as e:
    print(f"Connection error: {e}")
