import json
import os
import webbrowser
from urllib.parse import urlencode

import requests


CLIENT_ID = os.getenv("ZOHO_CLIENT_ID", "1000.Y06ENWZQ8EM6L5S6WBZNH6HGK75D4Y")
CLIENT_SECRET = os.getenv("ZOHO_CLIENT_SECRET", "b234404bf7090f3b94adcf779f4adcaa9453b881b8")
REDIRECT_URI = "http://localhost:8080"

ACCOUNTS_URL = "https://accounts.zoho.in"
TOKEN_FILE = "zoho_tokens.json"

SCOPE = "ZohoInventory.items.READ"


def create_authorization_url():
    """
    This URL is required only once to get the refresh token.
    """
    params = {
        "scope": SCOPE,
        "client_id": CLIENT_ID,
        "response_type": "code",
        "access_type": "offline",
        "redirect_uri": REDIRECT_URI,
        "prompt": "consent",
    }

    return f"{ACCOUNTS_URL}/oauth/v2/auth?{urlencode(params)}"


def exchange_authorization_code(code):
    """
    Exchange the one-time authorization code for access and refresh tokens.
    """
    response = requests.post(
        f"{ACCOUNTS_URL}/oauth/v2/token",
        data={
            "code": code.strip(),
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )

    data = response.json()

    if response.status_code != 200 or "access_token" not in data:
        raise RuntimeError(
            f"Token exchange failed: {json.dumps(data, indent=2)}"
        )

    if "refresh_token" not in data:
        raise RuntimeError(
            "Zoho did not return a refresh token. Revoke the existing app "
            "permission and authorize again using access_type=offline and "
            "prompt=consent."
        )

    save_tokens(data)

    return data


def save_tokens(tokens):
    with open(TOKEN_FILE, "w", encoding="utf-8") as file:
        json.dump(tokens, file, indent=2)

    print(f"Tokens saved in {TOKEN_FILE}")


def main():
    if CLIENT_ID == "PASTE_NEW_CLIENT_ID":
        print("Please set your Zoho Client ID and Client Secret first.")
        return

    authorization_url = create_authorization_url()

    print("=" * 70)
    print("ZOHO INITIAL AUTHORIZATION")
    print("=" * 70)
    print()
    print("Open this URL and sign in:")
    print()
    print(authorization_url)
    print()
    print("This sign-in is required only once.")
    print()

    try:
        webbrowser.open(authorization_url)
    except Exception:
        pass

    redirected_url = input(
        "After Zoho redirects you, paste the complete redirected URL here:\n"
    ).strip()

    if "code=" not in redirected_url:
        print("The URL does not contain an authorization code.")
        return

    code = redirected_url.split("code=", 1)[1].split("&", 1)[0]

    try:
        tokens = exchange_authorization_code(code)

        print()
        print("=" * 70)
        print("SUCCESS")
        print("=" * 70)
        print("Access token received.")
        print("Refresh token received.")
        print()
        print("You will not need to sign in again unless:")
        print("- the refresh token is revoked")
        print("- the Zoho app is deleted")
        print("- the user removes app permission")

    except Exception as error:
        print()
        print(f"Error: {error}")


if __name__ == "__main__":
    main()