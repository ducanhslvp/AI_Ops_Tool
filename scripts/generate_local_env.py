import secrets
import sys
from pathlib import Path


def main() -> None:
    env_path = Path(sys.argv[1]).resolve()
    content = env_path.read_text(encoding="utf-8")
    content = content.replace("change-me-with-64-random-characters", secrets.token_urlsafe(48))
    content = content.replace("change-me-refresh-secret", secrets.token_urlsafe(48))
    content = content.replace(
        "SECRET_ENCRYPTION_KEY=", f"SECRET_ENCRYPTION_KEY={secrets.token_urlsafe(48)}"
    )
    env_path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
