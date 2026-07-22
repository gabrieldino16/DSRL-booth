"""Autorización de SmugMug (se corre UNA sola vez).

Conecta tu cuenta de SmugMug con la fotocabina mediante OAuth 1.0a y te deja
listos los datos para pegar en `secrets.json`.

ANTES de correrlo necesitás una API Key + Secret de SmugMug:
  1. Entrá a https://api.smugmug.com/api/developer/apply y pedí una "API Key".
  2. Copiá el "API Key" y el "API Secret" que te dan.

Uso (desde la raíz del proyecto):
  .venv\\Scripts\\python.exe scripts\\smugmug_auth.py

El script te va a:
  - pedir tu API Key y Secret,
  - abrir el navegador para que autorices la app en tu cuenta,
  - pedirte el código de 6 dígitos que muestra SmugMug,
  - imprimir tus access_token / access_secret,
  - listar tus álbumes con su album_uri para que elijas dónde subir.
Después pegás esos valores en secrets.json.
"""
from __future__ import annotations

import sys
import webbrowser

try:
    from requests_oauthlib import OAuth1Session
except ImportError:
    print("Falta requests-oauthlib. Instalá: pip install requests-oauthlib")
    sys.exit(1)

BASE = "https://secure.smugmug.com/services/oauth/1.0a"
REQUEST_TOKEN_URL = f"{BASE}/getRequestToken"
AUTHORIZE_URL = f"{BASE}/authorize"
ACCESS_TOKEN_URL = f"{BASE}/getAccessToken"
API_ROOT = "https://api.smugmug.com"


def main() -> None:
    print("=== Autorización de SmugMug ===\n")
    api_key = input("API Key: ").strip()
    api_secret = input("API Secret: ").strip()
    if not api_key or not api_secret:
        print("Necesito API Key y Secret. Salgo.")
        return

    # 1) Token de solicitud.
    session = OAuth1Session(api_key, client_secret=api_secret,
                            callback_uri="oob")
    session.fetch_request_token(REQUEST_TOKEN_URL)

    # 2) URL de autorización (pedimos permiso de lectura+escritura).
    auth_url = session.authorization_url(AUTHORIZE_URL)
    auth_url += "&Access=Full&Permissions=Add"
    print("\nAbrí esta URL y autorizá la app (intento abrirla solo):")
    print(auth_url + "\n")
    try:
        webbrowser.open(auth_url)
    except Exception:  # noqa: BLE001
        pass

    verifier = input("Pegá el código de 6 dígitos que muestra SmugMug: ").strip()

    # 3) Token de acceso definitivo.
    session = OAuth1Session(
        api_key, client_secret=api_secret,
        resource_owner_key=session.token["oauth_token"],
        resource_owner_secret=session.token["oauth_token_secret"],
        verifier=verifier)
    tokens = session.fetch_access_token(ACCESS_TOKEN_URL)
    access_token = tokens["oauth_token"]
    access_secret = tokens["oauth_token_secret"]

    print("\n=== ¡Listo! Pegá esto en secrets.json (sección \"smugmug\") ===")
    print(f'  "api_key": "{api_key}",')
    print(f'  "api_secret": "{api_secret}",')
    print(f'  "access_token": "{access_token}",')
    print(f'  "access_secret": "{access_secret}",')

    # 4) Listar álbumes para elegir album_uri.
    print("\nBuscando tus álbumes...")
    auth = OAuth1Session(api_key, client_secret=api_secret,
                         resource_owner_key=access_token,
                         resource_owner_secret=access_secret)
    headers = {"Accept": "application/json"}
    me = auth.get(f"{API_ROOT}/api/v2!authuser", headers=headers).json()
    nickname = me["Response"]["User"]["NickName"]
    albums_uri = me["Response"]["User"]["Uris"]["UserAlbums"]["Uri"]
    albums = auth.get(API_ROOT + albums_uri + "?count=100",
                      headers=headers).json()

    print(f"\nÁlbumes de {nickname} (elegí uno y usá su album_uri):\n")
    for al in albums["Response"].get("Album", []):
        print(f'  {al["Name"]:35s} -> "album_uri": "{al["Uri"]}"')
    print("\nSi no ves el álbum que querés, creá uno en SmugMug y volvé a correr esto.")


if __name__ == "__main__":
    main()
