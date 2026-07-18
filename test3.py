#!/usr/bin/env python3

from flask import Flask, request

app = Flask(__name__)


@app.route("/", methods=["POST"])
def gsi():
    data = request.get_json(silent=True)

    if not data:
        return "OK"

    round_info = data.get("round")

    if round_info is None:
        return "OK"

    print("\n========== ROUND INFO ==========")

    for key, value in round_info.items():
        print(f"{key:20}: {value}")

    print("================================")

    return "OK"


if __name__ == "__main__":
    print("Listening on http://127.0.0.1:3000")
    app.run(host="127.0.0.1", port=3000, debug=False)

'''
OUTPUT:
========== ROUND INFO ==========
phase               : freezetime
================================
127.0.0.1 - - [18/Jul/2026 22:40:52] "POST / HTTP/1.1" 200 -

========== ROUND INFO ==========
phase               : live
================================
127.0.0.1 - - [18/Jul/2026 22:40:54] "POST / HTTP/1.1" 200 -
'''