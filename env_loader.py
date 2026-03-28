# config/env_loader.py

import os
from pathlib import Path
from dotenv import load_dotenv

_env_loaded = False

def load_env():
    """
    Loads environment variables from the root .env file.
    Call this once at app startup or before accessing os.getenv().
    """
    global _env_loaded
    if _env_loaded:
        return  # already loaded, skip

    # Find project root (where .env is located)
    current_dir = Path(__file__).resolve()
    while current_dir != current_dir.parent:
        env_path = current_dir / ".env"
        if env_path.exists():
            load_dotenv(dotenv_path=env_path, override=True)
            _env_loaded = True
            print(f"✅ Loaded environment from: {env_path}")
            return
        current_dir = current_dir.parent

    print("⚠️ No .env file found in parent directories.")
