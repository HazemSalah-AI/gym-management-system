"""Manual API smoke test with hidden password input and an in-memory cookie jar."""
import argparse
import getpass
import secrets
import warnings
from urllib.parse import urlparse

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    parsed = urlparse(args.base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        parser.error("Use a plain HTTP(S) server URL without credentials")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        parser.error("Use HTTPS for a remote server")
    try:
        username = input("Username: ")
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            password = getpass.getpass("Password: ")
        # Local development traffic must not go through an ambient remote proxy.
        use_proxy_environment = parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        with httpx.Client(base_url=args.base_url, timeout=15, trust_env=use_proxy_environment) as client:
            def expect(response: httpx.Response, status: int, label: str):
                if response.status_code != status:
                    raise RuntimeError(f"{label}: expected {status}, got {response.status_code}")
                print(f"PASS: {label}")

            response = client.get("/auth/csrf")
            expect(response, 200, "CSRF token")
            csrf = response.json()["csrf_token"]
            response = client.post("/auth/login", json={"username": username, "password": password},
                                   headers={"X-CSRF-Token": csrf})
            expect(response, 200, "Login")
            response = client.get("/auth/me")
            expect(response, 200, "Current user")
            if "password_hash" in response.text:
                raise RuntimeError("Sensitive field appeared in response")
            csrf = client.get("/auth/csrf").json()["csrf_token"]
            expect(client.post("/auth/logout", headers={"X-CSRF-Token": csrf}), 204, "Logout")
            expect(client.get("/auth/me"), 401, "No session")
            csrf = client.get("/auth/csrf").json()["csrf_token"]
            response = client.post("/auth/login", json={"username": username, "password": secrets.token_urlsafe(48)},
                                   headers={"X-CSRF-Token": csrf})
            expect(response, 401, "Wrong password")
            if response.json() != {"detail": "Invalid username or password"}:
                raise RuntimeError("Unexpected invalid-credentials response")
        return 0
    except (EOFError, KeyboardInterrupt, getpass.GetPassWarning):
        print("Cancelled: run from a terminal supporting hidden password input.")
    except (httpx.HTTPError, RuntimeError, KeyError, ValueError) as exc:
        if isinstance(exc, RuntimeError):
            print(str(exc))
        else:
            print("Verification failed: check server availability and configuration.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
