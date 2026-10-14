import json
import os
import urllib.error
import urllib.request
from pathlib import Path

# Config: read from backend/.env, never printed
ENV_PATH = Path(__file__).parent.parent / ".env"  # backend/.env
TIMEOUT_SECONDS = 30


def load_env_file(path: Path) -> None:
    """Copy KEY=VALUE lines from .env into os.environ."""
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


# Helper: one POST call, returns (status, short message)
def post_json(url: str, api_key: str, body: dict) -> tuple[int, dict]:
    """Send a JSON POST and return the status code and parsed reply."""
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        # Provider rejected the call (bad key, no balance, wrong model)
        return error.code, {"error": error.read().decode()[:200]}


# Checks: one function per provider
def test_anthropic() -> str:
    """Ask Claude for a 5 token reply."""
    request = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps({
            "model": os.environ["ANTHROPIC_MODEL"],
            "max_tokens": 5,
            "messages": [{"role": "user", "content": "Reply with: ok"}],
        }).encode(),
        headers={
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            reply = json.loads(response.read())
    except urllib.error.HTTPError as error:
        return f"FAIL {error.code} {error.read().decode()[:200]}"
    return "OK reply=" + reply["content"][0]["text"]


# DeepSeek paused. Uncomment this and its entry in main() to switch back.
# def test_deepseek() -> str:
#     """Ask DeepSeek for a 5 token reply."""
#     status, reply = post_json(
#         os.environ["DEEPSEEK_BASE_URL"] + "/chat/completions",
#         os.environ["DEEPSEEK_API_KEY"],
#         {
#             "model": os.environ["DEEPSEEK_MODEL"],
#             "messages": [{"role": "user", "content": "Reply with: ok"}],
#             "max_tokens": 5,
#         },
#     )
#     if status != 200:
#         return f"FAIL {status} {reply}"
#     return "OK reply=" + reply["choices"][0]["message"]["content"]


def test_voyage() -> str:
    """Embed one word and report the vector size."""
    status, reply = post_json(
        os.environ["VOYAGE_BASE_URL"] + "/embeddings",
        os.environ["VOYAGE_API_KEY"],
        {"model": os.environ["VOYAGE_MODEL"], "input": ["hello"]},
    )
    if status != 200:
        return f"FAIL {status} {reply}"
    return f"OK vector size={len(reply['data'][0]['embedding'])}"


# Entry point: one try/except so network errors print cleanly
def main() -> None:
    load_env_file(ENV_PATH)
    for name, check in [("Anthropic", test_anthropic), ("Voyage", test_voyage)]:  # ("DeepSeek", test_deepseek) paused
        try:
            print(f"{name}: {check()}")
        except Exception as error:
            print(f"{name}: ERROR {type(error).__name__}: {error}")


if __name__ == "__main__":
    main()
