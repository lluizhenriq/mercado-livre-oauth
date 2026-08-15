from flask import Flask, request

app = Flask(__name__)

@app.route("/")
def home():
    return "Mega Desconto - servidor online!"

@app.route("/callback")
def callback():
    code = request.args.get("code")

    if not code:
        return "Callback funcionando, mas nenhum código foi recebido."

    return f"Código recebido: {code}"

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
