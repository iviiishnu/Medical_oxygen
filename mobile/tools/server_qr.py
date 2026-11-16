"""Generate Server & Expo Go QR Codes for Instant Phone Pairing.

Run:
    python mobile/tools/server_qr.py [--server-port 8000] [--expo-port 8082]
"""
from __future__ import annotations

import argparse
import socket
import urllib.parse
from pathlib import Path


def get_local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def main():
    parser = argparse.ArgumentParser(description="Server & Expo Go QR Code Generator")
    parser.add_argument("--server-port", type=int, default=8000, help="Vision server port (default: 8000)")
    parser.add_argument("--expo-port", type=int, default=8082, help="Expo Metro bundler port (default: 8082)")
    args = parser.parse_args()

    local_ip = get_local_ip()
    server_url = f"http://{local_ip}:{args.server_port}"
    expo_url = f"exp://{local_ip}:{args.expo_port}"

    qr_expo = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(expo_url)}"
    qr_server = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={urllib.parse.quote(server_url)}"

    html_content = f"""<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>O2 Monitor - Phone Pairing Hub</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {{
            font-family: system-ui, -apple-system, sans-serif;
            background: #1e222b;
            color: #ffffff;
            display: flex;
            flex-direction: column;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            padding: 24px;
        }}
        .header {{
            text-align: center;
            margin-bottom: 24px;
        }}
        .header h1 {{
            font-size: 24px;
            margin: 0;
            color: #8ab4f8;
        }}
        .header p {{
            font-size: 13px;
            color: #9aa0a6;
            margin-top: 6px;
        }}
        .grid {{
            display: flex;
            gap: 24px;
            flex-wrap: wrap;
            justify-content: center;
            max-width: 900px;
            width: 100%;
        }}
        .card {{
            background: #ffffff;
            color: #202124;
            border-radius: 16px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.3);
            padding: 24px;
            flex: 1;
            min-width: 320px;
            max-width: 400px;
            text-align: center;
        }}
        .card h2 {{
            font-size: 18px;
            margin-top: 0;
            color: #1a73e8;
        }}
        .url {{
            background: #f1f3f4;
            padding: 8px 12px;
            border-radius: 6px;
            font-family: monospace;
            font-size: 13px;
            font-weight: bold;
            color: #202124;
            margin: 12px 0;
            word-break: break-all;
        }}
        img.qr {{
            width: 240px;
            height: 240px;
            border-radius: 8px;
            border: 1px solid #dadce0;
            margin: 10px 0;
        }}
        .step {{
            font-size: 12px;
            color: #5f6368;
            line-height: 1.5;
            text-align: left;
            background: #f8f9fa;
            padding: 10px;
            border-radius: 8px;
            margin-top: 12px;
        }}
        .step strong {{
            color: #202124;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📱 O2 Monitor Phone Pairing Hub</h1>
        <p>Scan with your phone to launch the app and connect to the local server</p>
    </div>

    <div class="grid">
        <!-- Card 1: Launch App via Expo Go -->
        <div class="card">
            <h2>1. Launch App in Expo Go</h2>
            <div class="url">{expo_url}</div>
            <img class="qr" src="{qr_expo}" alt="Expo Go QR Code" />
            <div class="step">
                <strong>Instructions:</strong><br>
                1. Open the <strong>Expo Go</strong> app on your Android phone or iPhone.<br>
                2. Tap <strong>"Scan QR Code"</strong> (or use iPhone Camera).<br>
                3. The app loads instantly over your Wi-Fi!
            </div>
        </div>

        <!-- Card 2: Connect Server API -->
        <div class="card">
            <h2>2. Connect Server API</h2>
            <div class="url">{server_url}</div>
            <img class="qr" src="{qr_server}" alt="Vision Server QR Code" />
            <div class="step">
                <strong>Instructions:</strong><br>
                Inside the running app, tap <strong>"📷 Connect via QR Scanner"</strong> to link the app to this Vision server.
            </div>
        </div>
    </div>
</body>
</html>
"""

    out_file = Path(__file__).resolve().parent / "server_qr.html"
    out_file.write_text(html_content, encoding="utf-8")

    print("\n" + "=" * 60)
    print("  O2 MONITOR - PAIRING HUB READY")
    print("=" * 60)
    print(f"Expo Go App URL:   {expo_url}")
    print(f"Vision Server URL: {server_url}")
    print(f"Pairing Hub HTML:  {out_file.as_uri()}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
