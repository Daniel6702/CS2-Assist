#!/usr/bin/env python3

from flask import Flask, request

app = Flask(__name__)

last_round = None


@app.post("/")
def receive_gsi():
    global last_round

    data = request.get_json(silent=True) or {}

    current_round = data.get("round")
    previous_round = data.get("previously", {}).get("round")

    if current_round != last_round or previous_round is not None:
        print("\nROUND UPDATE")
        print("Current:   ", current_round)
        print("Previously:", previous_round, flush=True)

        last_round = (
            current_round.copy()
            if isinstance(current_round, dict)
            else current_round
        )

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
Example out:
Current: {'phase': 'live', 'bomb': 'planted'}
'''