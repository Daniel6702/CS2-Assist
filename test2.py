#!/usr/bin/env python3

import logging
from flask import Flask, request

logging.getLogger("werkzeug").setLevel(logging.ERROR)

app = Flask(__name__)

last_value = None


@app.post("/")
def receive_gsi():
    global last_value

    data = request.get_json(silent=True) or {}

    has_kit = data.get("player", {}).get("state", {}).get("defusekit")

    if has_kit != last_value:
        print(f"Defuse kit: {has_kit}", flush=True)
        last_value = has_kit

    return "", 200


if __name__ == "__main__":
    print("Listening on http://127.0.0.1:3000")

    app.run(
        host="127.0.0.1",
        port=3000,
        threaded=False,
        use_reloader=False,
    )

'''
OUT:
Defuse kit: True
Defuse kit: None
'''