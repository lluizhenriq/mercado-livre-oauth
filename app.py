from flask import Flask, request
import os

app = Flask(__name__)


@app.route("/")
def home():
    return "Mega Desconto - bot online!"


@app.route("/callback")
def callback():
    code = request.args.get("code")

    if not code:
        return "Callback funcionando!"

    return "Autorização recebida com sucesso!"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
