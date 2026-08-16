from flask import Flask, request
import os
import requests
import time
import threading
from urllib.parse import urlencode

app = Flask(__name__)

# ============================================================
# CONFIGURAÇÃO
# ============================================================

REDIRECT_URI = "https://mercado-livre-oauth.onrender.com/callback"

ML_AUTH_URL = "https://auth.mercadolivre.com.br/authorization"
ML_TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
ML_API_URL = "https://api.mercadolibre.com"

# Configuração das ofertas
DESCONTO_MINIMO = 20
PRECO_MINIMO = 20
PRECO_MAXIMO = 5000

tokens = {
    "access_token": os.environ.get("ML_ACCESS_TOKEN"),
    "refresh_token": os.environ.get("ML_REFRESH_TOKEN"),
    "expires_at": 0
}

token_lock = threading.Lock()


# ============================================================
# CREDENCIAIS
# ============================================================

def get_credentials():
    client_id = os.environ.get("ML_CLIENT_ID")
    client_secret = os.environ.get("ML_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise RuntimeError(
            "ML_CLIENT_ID ou ML_CLIENT_SECRET não configurado."
        )

    return client_id, client_secret


# ============================================================
# TOKENS
# ============================================================

def save_tokens(data):
    tokens["access_token"] = data.get("access_token")
    tokens["refresh_token"] = data.get("refresh_token")

    expires_in = int(data.get("expires_in", 21600))

    # Renova 5 minutos antes de expirar
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
            f"Erro ao obter token: {response.text}"
        )

    data = response.json()

    if not data.get("access_token"):
        raise RuntimeError(
            f"Access Token não recebido: {data}"
        )

    save_tokens(data)

    return data


def refresh_access_token():
    with token_lock:

        refresh_token = tokens.get("refresh_token")

        if not refresh_token:
            raise RuntimeError(
                "Refresh Token não disponível. Autorize novamente."
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
                f"Erro ao renovar token: {response.text}"
            )

        data = response.json()

        if not data.get("access_token"):
            raise RuntimeError(
                f"Novo Access Token não recebido: {data}"
            )

        save_tokens(data)

        return data


def get_access_token():
    if not tokens.get("access_token"):
        raise RuntimeError(
            "Mercado Livre não está autorizado. "
            "Abra /autorizar primeiro."
        )

    if time.time() >= tokens.get("expires_at", 0):
        refresh_access_token()

    return tokens["access_token"]


# ============================================================
# API MERCADO LIVRE
# ============================================================

def ml_get(endpoint, params=None):

    access_token = get_access_token()

    response = requests.get(
        f"{ML_API_URL}{endpoint}",
        params=params,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        },
        timeout=20
    )

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
            f"Erro API Mercado Livre {response.status_code}: "
            f"{response.text}"
        )

    return response.json()


# ============================================================
# BUSCAR PRODUTOS
# ============================================================

def buscar_produtos():

    print("====================================")
print("PRODUTOS ENCONTRADOS:", len(produtos))
print("====================================")

for p in produtos[:10]:
    print(
        p.get("id"),
        "|",
        p.get("title"),
        "|",
        p.get("price"),
        "|",
        p.get("original_price")
    )

    consultas = [
        "ofertas",
        "eletronicos",
        "casa",
        "celular",
        "informatica"
    ]

    encontrados = []

    for consulta in consultas:

        try:

            resposta = requests.get(
                f"{ML_API_URL}/sites/MLB/search",
                params={
                    "q": consulta,
                    "limit": 20
                },
                timeout=20
            )

            if not resposta.ok:
                continue

            dados = resposta.json()

            for produto in dados.get("results", []):

                if produto.get("id"):

                    encontrados.append(produto)

        except Exception:
            continue

    # Remove produtos repetidos
    unicos = {}

    for produto in encontrados:
        unicos[produto["id"]] = produto

    return list(unicos.values())


# ============================================================
# PEGAR PREÇO REAL / PROMOÇÃO
# ============================================================

def obter_preco_promocional(item_id):

    dados = ml_get(
        f"/items/{item_id}/prices"
    )

    precos = dados.get("prices", [])

    melhor = None

    for preco in precos:

        tipo = preco.get("type")

        amount = preco.get("amount")
        regular_amount = preco.get("regular_amount")

        if not amount or not regular_amount:
            continue

        if regular_amount <= amount:
            continue

        # Verifica se a promoção está ativa
        conditions = preco.get("conditions", {})

        inicio = conditions.get("start_time")
        fim = conditions.get("end_time")

        # O Mercado Livre pode retornar condições sem datas.
        # Nesse caso ainda podemos analisar o preço.
        agora = time.time()

        # Para esta primeira versão,
        # usamos o preço promocional disponível.

        desconto = (
            (regular_amount - amount)
            / regular_amount
        ) * 100

        if desconto < DESCONTO_MINIMO:
            continue

        if amount < PRECO_MINIMO:
            continue

        if amount > PRECO_MAXIMO:
            continue

        candidato = {
            "preco": float(amount),
            "preco_original": float(regular_amount),
            "desconto": round(desconto, 1),
            "tipo": tipo,
            "inicio": inicio,
            "fim": fim
        }

        if melhor is None:
            melhor = candidato

        elif candidato["desconto"] > melhor["desconto"]:
            melhor = candidato

    return melhor


# ============================================================
# TELEGRAM
# ============================================================

def enviar_telegram(produto):

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID não configurado."
        )

    titulo = produto["titulo"]
    preco = produto["preco"]
    preco_original = produto["preco_original"]
    desconto = produto["desconto"]
    imagem = produto.get("imagem")
    link = produto["link"]

    texto = (
        "🔥 MEGA DESCONTO\n\n"
        f"🛒 {titulo}\n\n"
        "💰 OFERTA ENCONTRADA!\n\n"
        f"DE: R$ {preco_original:,.2f}\n"
        f"POR: R$ {preco:,.2f}\n"
        f"📉 {desconto:.0f}% OFF\n\n"
        "🛍️ Confira a oferta:\n"
        f"{link}"
    )

    # Ajusta formato brasileiro
    texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")

    if imagem:

        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendPhoto",
            json={
                "chat_id": chat_id,
                "photo": imagem,
                "caption": texto
            },
            timeout=30
        )

    else:

        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": texto
            },
            timeout=30
        )

    if not response.ok:
        raise RuntimeError(
            f"Telegram retornou erro: {response.text}"
        )

    return response.json()


# ============================================================
# PÁGINA PRINCIPAL
# ============================================================

@app.route("/")
def home():

    return """
    <h1>🔥 Mega Desconto</h1>

    <p>Servidor online!</p>

    <hr>

    <p>
        <a href="/autorizar">
            🔐 Autorizar Mercado Livre
        </a>
    </p>

    <p>
        <a href="/ml-teste">
            🛒 Testar Mercado Livre
        </a>
    </p>

    <p>
        <a href="/oferta-teste">
            🔥 Buscar uma oferta de teste
        </a>
    </p>

    <p>
        <a href="/telegram-teste">
            📲 Testar Telegram
        </a>
    </p>
    """


# ============================================================
# AUTORIZAÇÃO
# ============================================================

@app.route("/autorizar")
def autorizar():

    client_id = os.environ.get("ML_CLIENT_ID")

    if not client_id:
        return "ML_CLIENT_ID não configurado.", 500

    parametros = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI
    }

    url = (
        ML_AUTH_URL
        + "?"
        + urlencode(parametros)
    )

    return f"""
    <script>
        window.location.href = "{url}";
    </script>

    <p>
        Redirecionando para o Mercado Livre...
    </p>

    <p>
        <a href="{url}">
            Clique aqui
        </a>
    </p>
    """


# ============================================================
# CALLBACK
# ============================================================

@app.route("/callback")
def callback():

    erro = request.args.get("error")

    if erro:
        return f"""
        <h1>❌ Erro</h1>
        <p>{erro}</p>
        """, 400

    code = request.args.get("code")

    if not code:
        return """
        <h1>❌ Código não recebido</h1>
        """, 400

    try:

        data = exchange_code_for_token(code)

        return """
        <h1>✅ Mercado Livre conectado!</h1>

        <p>
            Autorização concluída com sucesso.
        </p>

        <p>
            <a href="/ml-teste">
                🛒 Testar Mercado Livre
            </a>
        </p>

        <p>
            <a href="/oferta-teste">
                🔥 Buscar oferta de teste
            </a>
        </p>
        """

    except Exception as e:

        return f"""
        <h1>❌ Erro na autorização</h1>

        <p>{e}</p>
        """, 500


# ============================================================
# TESTE MERCADO LIVRE
# ============================================================

@app.route("/ml-teste")
def ml_teste():

    try:

        usuario = ml_get("/users/me")

        return f"""
        <h1>✅ Mercado Livre funcionando!</h1>

        <p>
            Usuário: {usuario.get("nickname", "não informado")}
        </p>

        <p>
            ID: {usuario.get("id", "não informado")}
        </p>

        <p>
            <a href="/oferta-teste">
                🔥 Buscar oferta
            </a>
        </p>
        """

    except Exception as e:

        return f"""
        <h1>❌ Erro</h1>

        <p>{e}</p>

        <p>
            <a href="/autorizar">
                🔐 Autorizar novamente
            </a>
        </p>
        """, 500


# ============================================================
# PRIMEIRA OFERTA DE TESTE
# ============================================================

@app.route("/oferta-teste")
def oferta_teste():

    try:

        produtos = buscar_produtos()

        if not produtos:
            return """
            <h1>❌ Nenhum produto encontrado.</h1>
            """

        analisados = 0

        for produto in produtos:

            item_id = produto.get("id")

            try:

                promocao = obter_preco_promocional(item_id)

                analisados += 1

                if not promocao:
                    continue

                titulo = produto.get(
                    "title",
                    "Produto sem título"
                )

                imagem = (
                    produto.get("thumbnail")
                    or produto.get("secure_thumbnail")
                )

                link = produto.get(
                    "permalink",
                    ""
                )

                dados = {
                    "id": item_id,
                    "titulo": titulo,
                    "preco": promocao["preco"],
                    "preco_original": promocao["preco_original"],
                    "desconto": promocao["desconto"],
                    "imagem": imagem,
                    "link": link
                }

                enviar_telegram(dados)

                return f"""
                <h1>🔥 Oferta enviada!</h1>

                <p>
                    <b>{titulo}</b>
                </p>

                <p>
                    De: R$ {promocao["preco_original"]:.2f}
                </p>

                <p>
                    Por: R$ {promocao["preco"]:.2f}
                </p>

                <p>
                    Desconto:
                    {promocao["desconto"]:.1f}%
                </p>

                <p>
                    O produto foi enviado para o Telegram.
                </p>
                """

            except Exception:
                continue

        return f"""
        <h1>😕 Nenhuma oferta encontrada</h1>

        <p>
            Foram analisados {analisados} produtos.
        </p>

        <p>
            O filtro atual exige pelo menos
            {DESCONTO_MINIMO}% de desconto.
        </p>

        <p>
            <a href="/oferta-teste">
                🔄 Tentar novamente
            </a>
        </p>
        """

    except Exception as e:

        return f"""
        <h1>❌ Erro ao buscar ofertas</h1>

        <p>{e}</p>
        """, 500


# ============================================================
# TESTE TELEGRAM
# ============================================================

@app.route("/telegram-teste")
def telegram_teste():

    try:

        enviar_telegram({
            "titulo": "Teste Mega Desconto",
            "preco": 79.90,
            "preco_original": 99.90,
            "desconto": 20,
            "imagem": None,
            "link": "https://www.mercadolivre.com.br/"
        })

        return """
        <h1>✅ Telegram funcionando!</h1>

        <p>
            Mensagem enviada para o grupo.
        </p>
        """

    except Exception as e:

        return f"""
        <h1>❌ Erro no Telegram</h1>

        <p>{e}</p>
        """, 500


# ============================================================
# SERVIDOR
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get("PORT", 10000)
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
