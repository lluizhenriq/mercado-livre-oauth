from flask import Flask, request
import os
import requests
import time
import threading

app = Flask(__name__)

# ============================================================
# CONFIGURAÇÃO
# ============================================================

REDIRECT_URI = "https://mercado-livre-oauth.onrender.com/callback"

ML_AUTH_URL = "https://auth.mercadolivre.com.br/authorization"
ML_TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
ML_API_URL = "https://api.mercadolibre.com"

# Tokens mantidos somente na memória durante esta etapa.
# Depois vamos colocar armazenamento persistente seguro.
tokens = {
    "access_token": os.environ.get("ML_ACCESS_TOKEN"),
    "refresh_token": os.environ.get("ML_REFRESH_TOKEN"),
    "expires_at": 0
}

token_lock = threading.Lock()


# ============================================================
# FUNÇÕES DO MERCADO LIVRE
# ============================================================

def get_credentials():
    client_id = os.environ.get("ML_CLIENT_ID")
    client_secret = os.environ.get("ML_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise RuntimeError(
            "ML_CLIENT_ID ou ML_CLIENT_SECRET não configurado no Render."
        )

    return client_id, client_secret


def save_tokens(data):
    """
    Guarda os tokens na memória.
    O Mercado Livre envia um novo refresh_token a cada renovação.
    """

    tokens["access_token"] = data.get("access_token")
    tokens["refresh_token"] = data.get("refresh_token")

    expires_in = int(data.get("expires_in", 21600))

    # Renovar um pouco antes da expiração.
    tokens["expires_at"] = time.time() + expires_in - 300


def exchange_code_for_token(code):
    client_id, client_secret = get_credentials()

    response = requests.post(
        ML_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": REDIRECT_URI
        },
        headers={
            "accept": "application/json",
            "content-type": "application/x-www-form-urlencoded"
        },
        timeout=20
    )

    if not response.ok:
        raise RuntimeError(
            f"Erro ao trocar código por token: {response.text}"
        )

    data = response.json()

    if not data.get("access_token"):
        raise RuntimeError(
            f"Mercado Livre não retornou access_token: {data}"
        )

    save_tokens(data)

    return data


def refresh_access_token():
    """
    Usa o último refresh_token para obter novos tokens.
    O Mercado Livre informa que o refresh_token é de uso único,
    portanto o novo refresh_token precisa substituir o anterior.
    """

    with token_lock:

        refresh_token = tokens.get("refresh_token")

        if not refresh_token:
            raise RuntimeError(
                "Não existe refresh_token. É necessário autorizar novamente."
            )

        client_id, client_secret = get_credentials()

        response = requests.post(
            ML_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token
            },
            headers={
                "accept": "application/json",
                "content-type": "application/x-www-form-urlencoded"
            },
            timeout=20
        )

        if not response.ok:
            raise RuntimeError(
                f"Não foi possível renovar o token: {response.text}"
            )

        data = response.json()

        if not data.get("access_token"):
            raise RuntimeError(
                f"Resposta de renovação inválida: {data}"
            )

        save_tokens(data)

        return data


def get_ml_access_token():
    """
    Retorna um Access Token válido.
    """

    if not tokens.get("access_token"):
        raise RuntimeError(
            "Mercado Livre ainda não foi autorizado."
        )

    # Se estiver próximo da expiração, renova.
    if time.time() >= tokens.get("expires_at", 0):
        refresh_access_token()

    return tokens["access_token"]


def ml_get(endpoint, params=None):
    """
    Faz uma requisição autenticada à API do Mercado Livre.
    """

    access_token = get_ml_access_token()

    response = requests.get(
        f"{ML_API_URL}{endpoint}",
        params=params,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        },
        timeout=20
    )

    # Se o token estiver inválido, tenta renovar uma vez.
    if response.status_code == 401:
        refresh_access_token()

        access_token = tokens["access_token"]

        response = requests.get(
            f"{ML_API_URL}{endpoint}",
            params=params,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json"
            },
            timeout=20
        )

    if not response.ok:
        raise RuntimeError(
            f"Erro na API do Mercado Livre ({response.status_code}): "
            f"{response.text}"
        )

    return response.json()


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram_message(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID não configurado."
        )

    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text
        },
        timeout=20
    )

    if not response.ok:
        raise RuntimeError(
            f"Erro ao enviar Telegram: {response.text}"
        )

    return response.json()


# ============================================================
# PÁGINA PRINCIPAL
# ============================================================

@app.route("/")
def home():

    return """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <title>Mega Desconto</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 700px;
                margin: 50px auto;
                padding: 20px;
                background: #f5f5f5;
            }

            .box {
                background: white;
                padding: 30px;
                border-radius: 15px;
                box-shadow: 0 4px 20px rgba(0,0,0,.1);
            }

            a {
                display: block;
                margin: 15px 0;
                padding: 15px;
                background: #ffe600;
                color: #222;
                text-decoration: none;
                border-radius: 10px;
                font-weight: bold;
            }
        </style>
    </head>

    <body>

        <div class="box">

            <h1>🔥 Mega Desconto</h1>

            <p>Servidor online.</p>

            <a href="/autorizar">
                🔐 Conectar Mercado Livre
            </a>

            <a href="/ml-teste">
                🛒 Testar Mercado Livre
            </a>

            <a href="/telegram-teste">
                📲 Testar Telegram
            </a>

        </div>

    </body>
    </html>
    """


# ============================================================
# AUTORIZAÇÃO
# ============================================================

@app.route("/autorizar")
def autorizar():

    client_id = os.environ.get("ML_CLIENT_ID")

    if not client_id:
        return (
            "Erro: ML_CLIENT_ID não está configurado no Render.",
            500
        )

    authorization_url = (
        f"{ML_AUTH_URL}"
        f"?response_type=code"
        f"&client_id={client_id}"
        f"&redirect_uri={REDIRECT_URI}"
    )

    return f"""
    <html>
        <head>
            <meta http-equiv="refresh"
                  content="0;url={authorization_url}">
        </head>

        <body>
            <p>Redirecionando para o Mercado Livre...</p>
            <p>
                <a href="{authorization_url}">
                    Clique aqui se não redirecionar.
                </a>
            </p>
        </body>
    </html>
    """


# ============================================================
# CALLBACK DO MERCADO LIVRE
# ============================================================

@app.route("/callback")
def callback():

    error = request.args.get("error")

    if error:
        return f"""
        <h1>❌ Autorização não concluída</h1>
        <p>Erro: {error}</p>
        """, 400

    code = request.args.get("code")

    if not code:
        return """
        <h1>❌ Código não recebido</h1>
        <p>
            O Mercado Livre não enviou o código de autorização.
        </p>
        """, 400

    try:

        data = exchange_code_for_token(code)

        user_id = data.get("user_id", "desconhecido")
        expires_in = data.get("expires_in", "desconhecido")

        return f"""
        <h1>✅ Mercado Livre conectado!</h1>

        <p>A autorização foi concluída.</p>

        <p><b>ID do usuário:</b> {user_id}</p>

        <p>
            O Access Token foi recebido com sucesso.
        </p>

        <p>
            Validade informada pelo Mercado Livre:
            <b>{expires_in} segundos</b>
        </p>

        <hr>

        <p>
            Agora você pode testar a conexão:
        </p>

        <p>
            <a href="/ml-teste">
                🛒 Testar Mercado Livre
            </a>
        </p>
        """

    except Exception as e:

        return f"""
        <h1>❌ Erro na autorização</h1>

        <p>{str(e)}</p>
        """, 500


# ============================================================
# TESTE DO MERCADO LIVRE
# ============================================================

@app.route("/ml-teste")
def ml_teste():

    try:

        usuario = ml_get("/users/me")

        nickname = usuario.get("nickname", "não informado")
        user_id = usuario.get("id", "não informado")

        return f"""
        <h1>✅ Mercado Livre funcionando!</h1>

        <p><b>Usuário:</b> {nickname}</p>

        <p><b>ID:</b> {user_id}</p>

        <p>
            O bot conseguiu fazer uma requisição autenticada
            à API do Mercado Livre.
        </p>

        <hr>

        <p>
            <a href="/">
                Voltar
            </a>
        </p>
        """

    except Exception as e:

        return f"""
        <h1>❌ Erro</h1>

        <p>{str(e)}</p>

        <p>
            Talvez seja necessário autorizar novamente:
        </p>

        <p>
            <a href="/autorizar">
                🔐 Autorizar Mercado Livre
            </a>
        </p>
        """, 500


# ============================================================
# TESTE DO TELEGRAM
# ============================================================

@app.route("/telegram-teste")
def telegram_teste():

    try:

        send_telegram_message(
            "🔥 MEGA DESCONTO 🔥\n\n"
            "O bot conseguiu enviar esta mensagem automaticamente! 🚀"
        )

        return """
        <h1>✅ Telegram funcionando!</h1>

        <p>
            A mensagem foi enviada para o grupo.
        </p>

        <p>
            <a href="/">
                Voltar
            </a>
        </p>
        """

    except Exception as e:

        return f"""
        <h1>❌ Erro no Telegram</h1>

        <p>{str(e)}</p>
        """, 500


# ============================================================
# SERVIDOR
# ============================================================

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port
    )
