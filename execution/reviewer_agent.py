"""
Reviewer Sub-Agent

This script acts as a reviewer for other execution scripts. 
It uses an available LLM (Gemini, Claude, or OpenAI) to analyze code 
and provide actionable feedback.

Usage:
    python execution/reviewer_agent.py --file <path_to_file>
"""

import argparse
import os
import sys
from pathlib import Path
import requests

# --- Environment Loading ---

def load_env():
    """Load environment variables from .env file manually."""
    workspace_root = Path(__file__).parent.parent
    env_file = workspace_root / ".env"
    
    if env_file.exists():
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    os.environ[key] = value

# --- LLM Clients ---

class LLMClient:
    def generate(self, prompt: str) -> str:
        raise NotImplementedError

class GeminiClient(LLMClient):
    def __init__(self, api_key: str):
        self.api_key = api_key
        # Default to 1.5 Pro for better reasoning in code reviews
        self.model = os.environ.get("GEMINI_MODEL", "gemini-1.5-pro")
        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

    def generate(self, prompt: str) -> str:
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }
        headers = {"Content-Type": "application/json"}
        try:
            response = requests.post(self.url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            return f"Error calling Gemini ({self.model}): {e}"

class AnthropicClient(LLMClient):
    def __init__(self, api_key: str):
        self.api_key = api_key
        # Default to Opus 4.5 (2026 model)
        self.model = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-5-20251101")
        self.url = "https://api.anthropic.com/v1/messages"

    def generate(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}]
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        try:
            response = requests.post(self.url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            return data["content"][0]["text"]
        except Exception as e:
            return f"Error calling Anthropic ({self.model}): {e}"

class OpenAIClient(LLMClient):
    def __init__(self, api_key: str):
        self.api_key = api_key
        # Detect OpenRouter key
        if self.api_key.startswith("sk-or-v1"):
            self.base_url = "https://openrouter.ai/api/v1/chat/completions"
            self.model = os.environ.get("OPENAI_MODEL", "openai/gpt-4o")
            self.headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/google-deepmind/agentic-coding", # Optional for OpenRouter
                "X-Title": "Agentic Coding Assistant" # Optional for OpenRouter
            }
        else:
            self.base_url = "https://api.openai.com/v1/chat/completions"
            self.model = os.environ.get("OPENAI_MODEL", "gpt-4o")
            self.headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

    def generate(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2
        }
        
        try:
            response = requests.post(self.base_url, headers=self.headers, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"Error calling provider ({self.base_url}): {e}"

class NvidiaNIMClient(LLMClient):
    def __init__(self, api_key: str):
        import openai
        self.model = os.environ.get("NVIDIA_REVIEW_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b")
        self.client = openai.OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=api_key
        )

    def generate(self, prompt: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                timeout=600
            )
            content = response.choices[0].message.content
            return content if content is not None else ""
        except Exception as e:
            return f"Error calling Nvidia NIM ({self.model}): {e}"

def get_llm_client():
    load_env()
    
    # Check Nvidia NIM
    nvidia_key = os.environ.get("NVIDIA_NIM") or os.environ.get("NVIDIA_API_KEY")
    if nvidia_key:
        return NvidiaNIMClient(nvidia_key), "Nvidia NIM"
        
    # Check Gemini
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        return GeminiClient(gemini_key), "Gemini"
        
    # Check Anthropic
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if anthropic_key:
        return AnthropicClient(anthropic_key), "Anthropic"
        
    # Check OpenAI
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        return OpenAIClient(openai_key), "OpenAI"
        
    return None, None

# --- Main Logic ---

SYSTEM_PROMPT = """
You are the "Reviewer Sub-Agent", a highly critical Senior Principal Software Engineer.
Your job is to review the following execution script with "fresh eyes".

Criteria:
1. Effectiveness: Is this done in the most effective manner humanly possible?
2. Correctness: Are there logical errors or bugs?
3. Robustness: Does it handle errors and edge cases?
4. Quality: Is the code clean, readable, and Pythonic?

Provide your output in Markdown format:
## Summary
(Brief summary of what the script does)

## Effectiveness Review
(Critique on efficiency and approach)

## Critical Issues
(List of bugs or major flaws, if any)

## Recommendations
(Unordered list of specific instructions to the top-level agent to improve the build. Be extremely prescriptive.)
"""

def review_file(file_path: str, error_message: str | None = None):
    path = Path(file_path)
    if not path.exists():
        print(f"Error: File not found: {file_path}")
        sys.exit(1)
        
    content = path.read_text(encoding="utf-8")
    
    client, provider_name = get_llm_client()
    if not client:
        print("Error: No API keys found in .env (GEMINI_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY).")
        print("Please add one of these keys to your .env file to use the Reviewer Sub-Agent.")
        sys.exit(1)
        
    print(f"Reviewing {path.name} using {provider_name} (Model: {client.model})...")
    
    if error_message:
        full_prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            f"--- CRITICAL FAILURE ---\n"
            f"The execution script failed during runtime with the following error/exception:\n"
            f"{error_message}\n\n"
            f"Please analyze the script code in relation to this error. Specifically:\n"
            f"1. Explain why this error happened.\n"
            f"2. Provide concrete recommendations or code fixes to prevent or handle this error.\n\n"
            f"--- SCRIPT CONTENT ---\n\n{content}"
        )
    else:
        full_prompt = f"{SYSTEM_PROMPT}\n\n--- SCRIPT CONTENT ---\n\n{content}"
    
    review = client.generate(full_prompt)
    
    print("\n" + "="*40 + "\nREVIEW REPORT\n" + "="*40 + "\n")
    print(review)

def run_reviewer_on_failure(script_path: str, error_message: str):
    """Run reviewer agent on script failure as a subprocess to keep environment clean."""
    import subprocess
    import sys
    from pathlib import Path
    
    reviewer_path = Path(__file__).resolve().parent / "reviewer_agent.py"
    try:
        subprocess.run([
            sys.executable,
            str(reviewer_path),
            "--file", script_path,
            "--error", error_message
        ], check=False)
    except Exception as e:
        print(f"Error executing reviewer agent: {e}", file=sys.stderr)

def review_on_failure(func):
    """Decorator to automatically run the reviewer agent if the decorated function raises an exception."""
    import functools
    import inspect
    import sys
    import traceback
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except SystemExit as exc:
            if exc.code != 0:
                try:
                    file_path = inspect.getsourcefile(func) or __file__
                    run_reviewer_on_failure(file_path, f"SystemExit with code {exc.code}")
                except Exception as review_exc:
                    print(f"Failed to run Reviewer Agent: {review_exc}", file=sys.stderr)
            raise
        except Exception:
            err_msg = traceback.format_exc()
            try:
                file_path = inspect.getsourcefile(func) or __file__
                run_reviewer_on_failure(file_path, err_msg)
            except Exception as review_exc:
                print(f"Failed to run Reviewer Agent: {review_exc}", file=sys.stderr)
            raise
    return wrapper

def main():
    parser = argparse.ArgumentParser(description="Review an execution script.")
    parser.add_argument("--file", required=True, help="Path to the file to review")
    parser.add_argument("--error", help="Optional error message or traceback from execution failure")
    args = parser.parse_args()
    
    review_file(args.file, error_message=args.error)

if __name__ == "__main__":
    main()
