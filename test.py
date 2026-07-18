#!/usr/bin/env python3

from flask import Flask, request

app = Flask(__name__)

last_kills = None


@app.route("/", methods=["POST"])
def gsi():
    global last_kills

    data = request.json or {}

    stats = data.get("player", {}).get("match_stats", {})
    kills = stats.get("kills")

    if kills is None:
        return "", 200

    if last_kills is None:
        last_kills = kills
    elif kills > last_kills:
        print(f"KILL! Total kills: {kills}")
        last_kills = kills

    return "", 200


if __name__ == "__main__":
    print("Listening for CS2 GSI on http://127.0.0.1:3000")
    app.run(host="127.0.0.1", port=3000)