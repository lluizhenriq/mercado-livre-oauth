from flask import Flask
import os
import requests

app = Flask(__name__)


@app.route("/")
def home():
    return "Mega Desconto - bot online!"


@app.route("/teste")
def teste():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        return "Erro: variáveis do Telegram não configuradas.", 500

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    resposta = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": "🔥 TESTE MEGA DESCONTO 🔥\n\nO bot está funcionando corretamente! 🚀"
        },
        timeout=15
    )

    if resposta.ok:
        return "Mensagem enviada para o Telegram!"

    return f"Erro do Telegram: {resposta.text}", 500


@app.route("/callback")
def callback():
    return "Callback do Mercado Livre funcionando!"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
