from flask import Flask, request
import os
import requests

app = Flask(__name__)

REDIRECT_URI = "https://mercado-livre-oauth.onrender.com/callback"


@app.route("/")
def home():
    return """
    <h1>🔥 Mega Desconto</h1>
    <p>Servidor online!</p>
    <p><a href="/autorizar">🔐 Conectar Mercado Livre</a></p>
    <p><a href="/teste">📲 Testar Telegram</a></p>
    """


@app.route("/autorizar")
def autorizar():
    client_id = os.environ.get("ML_CLIENT_ID")

    if not client_id:
        return "ML_CLIENT_ID não configurado no Render.", 500

    url = (
        "https://auth.mercadolivre.com.br/authorization"
        f"?response_type=code"
        f"&client_id={client_id}"
        f"&redirect_uri={REDIRECT_URI}"
    )

    return f'<script>window.location.href="{url}"</script>'


@app.route("/callback")
def callback():
    code = request.args.get("code")

    if not code:
        error = request.args.get("error", "desconhecido")
        return f"Autorização não concluída. Erro: {error}", 400

    client_id = os.environ.get("ML_CLIENT_ID")
    client_secret = os.environ.get("ML_CLIENT_SECRET")

    if not client_id or not client_secret:
        return "Credenciais do Mercado Livre não configuradas no Render.", 500

    resposta = requests.post(
        "https://api.mercadolibre.com/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": REDIRECT_URI,
        },
        headers={
            "accept": "application/json",
            "content-type": "application/x-www-form-urlencoded",
        },
        timeout=20,
    )

    if not resposta.ok:
        return f"Erro ao obter token: {resposta.text}", 500

    dados = resposta.json()

    # Por segurança, não mostramos os tokens na página.
    return """
    <h1>✅ Mercado Livre conectado!</h1>
    <p>A autorização foi concluída.</p>
    <p>Agora precisamos salvar os tokens com segurança no Render.</p>
    """


@app.route("/teste")
def teste():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        return "Variáveis do Telegram não configuradas.", 500

    resposta = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": "🔥 TESTE MEGA DESCONTO 🔥\n\nBot funcionando!",
        },
        timeout=15,
    )

    if resposta.ok:
        return "Mensagem enviada para o Telegram!"

    return f"Erro do Telegram: {resposta.text}", 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
