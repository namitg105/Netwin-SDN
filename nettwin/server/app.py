"""Tiny Flask server that gives the clients something real to talk to.

Run on the srv host:  python3 -m nettwin.server.app
"""
import socket

from flask import Flask, jsonify

from nettwin import netmodel


def create_app():
    app = Flask(__name__)

    @app.route("/")
    def index():
        return jsonify(message="NetTwin server is alive", host=socket.gethostname())

    @app.route("/health")
    def health():
        return jsonify(status="ok")

    return app


if __name__ == "__main__":
    # 0.0.0.0: listen on every address of the host, so 10.0.0.100 works.
    create_app().run(host="0.0.0.0", port=netmodel.SERVER_PORT, threaded=True)
