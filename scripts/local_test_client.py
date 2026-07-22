import argparse
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def request(base_url: str, path: str, *, method: str = "GET", token: str | None = None,
            payload: dict | None = None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urlopen(Request(f"{base_url}{path}", data=data, headers=headers, method=method),
                     timeout=30) as response:
            body = response.read().decode()
            return json.loads(body) if body else None
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {path}: {detail}") from exc


def login(base_url: str, email: str, password: str) -> str:
    result = request(base_url, "/auth/login", method="POST", payload={
        "email": email, "password": password, "remember": False,
    })
    return result["access_token"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage backend development test profiles")
    parser.add_argument("profile")
    parser.add_argument("--hostname", default="erp-linux-01")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--email", default="operator@aiops.example.com")
    parser.add_argument("--password", default="Operator@123456")
    args = parser.parse_args()
    token = login(args.base_url, args.email, args.password)
    servers = request(args.base_url, "/inventory/servers?page=1&page_size=200", token=token)
    server = next((item for item in servers if item["hostname"] == args.hostname), None)
    if server is None:
        raise RuntimeError(f"Development target not found: {args.hostname}")
    result = request(args.base_url, f"/development/servers/{server['id']}/profile",
                     method="PUT", token=token, payload={"profile": args.profile})
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
