import os

# Load .env file using stdlib
_env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
if os.path.exists(_env_path):
    with open(_env_path, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                _k, _v = _k.strip(), _v.strip().strip("'\"")
                if _k not in os.environ:
                    os.environ[_k] = _v

# Browser Configuration
CHROME_USER_DATA = os.getenv("CHROME_USER_DATA", "/Users/siddhant/Library/Application Support/Google/Chrome")
CHROME_EXECUTABLE_PATH = os.getenv("CHROME_EXECUTABLE_PATH", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

# LLM & API Configuration
GOOGLE_AI_API_KEY = os.getenv("GOOGLE_AI_API_KEY", "")

# Resume Configuration
RESUME_FILE_PATH = os.getenv("RESUME_FILE_PATH", "/Users/siddhant/Desktop/Resume/SiddhantSinghResume2026.pdf")

