from flask import Flask, request
import os
import requests
import time
import threading
from urllib.parse import urlencode
from html import escape

app = Flask(__name__)

# ============================================================
# CONFIGURAÇÕES
# ============================================================

REDIRECT_URI = "https://mercado-livre-oauth.onrender.com/callback"

ML_AUTH_URL = "https://auth.mercadolivre.com.br/authorization"
ML_TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
ML_API_URL = "https://api.mercadolibre.com"

SITE_ID = "MLB"

DESCONTO_MINIMO = 20
PRECO_MINIMO = 20
PRECO_MAXIMO = 5000

PRODUTOS_POR_BUSCA = 10


# ============================================================
# TOKENS
# ============================================================

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

    if not client_id:
        raise RuntimeError(
            "ML_CLIENT_ID não está configurado no Render."
        )

    if not client_secret:
        raise RuntimeError(
            "ML_CLIENT_SECRET não está configurado no Render."
        )

    return client_id, client_secret


# ============================================================
# SALVAR TOKENS
# ============================================================

def save_tokens(data):

    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")

    if not access_token:
        raise RuntimeError(
            "Mercado Livre não retornou Access Token."
        )

    tokens["access_token"] = access_token

    if refresh_token:
        tokens["refresh_token"] = refresh_token

    expires_in = int(
        data.get("expires_in", 21600)
    )

    tokens["expires_at"] = (
        time.time() + expires_in - 300
    )


# ============================================================
# TROCAR CODE POR TOKEN
# ============================================================

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
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded"
        },
        timeout=30
    )

    if not response.ok:

        raise RuntimeError(
            "Erro ao trocar código por token:\n"
            + response.text
        )

    data = response.json()

    save_tokens(data)

    return data


# ============================================================
# RENOVAR ACCESS TOKEN
# ============================================================

def refresh_access_token():

    with token_lock:

        refresh_token = tokens.get(
            "refresh_token"
        )

        if not refresh_token:

            raise RuntimeError(
                "Refresh Token não encontrado. "
                "É necessário autorizar novamente."
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
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded"
            },
            timeout=30
        )

        if not response.ok:

            raise RuntimeError(
                "Erro ao renovar Access Token:\n"
                + response.text
            )

        data = response.json()

        save_tokens(data)

        return data


# ============================================================
# PEGAR ACCESS TOKEN
# ============================================================

def get_access_token():

    access_token = tokens.get(
        "access_token"
    )

    if not access_token:

        raise RuntimeError(
            "Mercado Livre não está autorizado. "
            "Acesse /autorizar."
        )

    if time.time() >= tokens.get(
        "expires_at",
        0
    ):

        refresh_access_token()

    return tokens["access_token"]


# ============================================================
# REQUISIÇÃO À API DO MERCADO LIVRE
# ============================================================

def ml_get(endpoint, params=None):

    access_token = get_access_token()

    response = requests.get(
        ML_API_URL + endpoint,
        params=params,
        headers={
            "Authorization": "Bearer " + access_token,
            "Accept": "application/json"
        },
        timeout=30
    )

    if response.status_code == 401:

        refresh_access_token()

        access_token = tokens["access_token"]

        response = requests.get(
            ML_API_URL + endpoint,
            params=params,
            headers={
                "Authorization": "Bearer " + access_token,
                "Accept": "application/json"
            },
            timeout=30
        )

    if not response.ok:

        raise RuntimeError(
            "Erro na API do Mercado Livre "
            + str(response.status_code)
            + ":\n"
            + response.text
        )

    return response.json()


# ============================================================
# BUSCAR PRODUTOS
# ============================================================

def buscar_produtos():

    consultas = [
        "celular",
        "notebook",
        "fone de ouvido",
        "smart tv",
        "mouse",
        "teclado",
        "monitor",
        "air fryer",
        "eletronicos"
    ]

    produtos = {}

    for consulta in consultas:

        try:

            print(
                f"[ML] Buscando catálogo: '{consulta}'"
            )

            data = ml_get(
                "/products/search",
                params={
                    "status": "active",
                    "site_id": SITE_ID,
                    "q": consulta,
                    "limit": PRODUTOS_POR_BUSCA,
                    "offset": 0
                }
            )

            resultados = data.get(
                "results",
                []
            )

            print(
                f"[ML] '{consulta}' -> "
                f"{len(resultados)} produtos"
            )

            for produto in resultados:

                product_id = produto.get("id")

                if not product_id:
                    continue

                try:

                    detalhe = ml_get(
                        "/products/" + product_id
                    )

                except Exception as e:

                    print(
                        f"[ML] Erro no produto "
                        f"{product_id}: {e}"
                    )

                    continue

                buy_box = detalhe.get(
                    "buy_box_winner"
                )

                if not buy_box:
                    print(
                        f"[ML] Produto {product_id} "
                        f"sem buy_box_winner"
                    )
                    continue

                item_id = buy_box.get(
                    "item_id"
                )

                if not item_id:
                    continue

                try:

                    item = ml_get(
                        "/items/" + item_id
                    )

                except Exception as e:

                    print(
                        f"[ML] Erro no item "
                        f"{item_id}: {e}"
                    )

                    continue

                item["catalog_product_id"] = product_id

                produtos[item_id] = item

        except Exception as e:

            print(
                f"[ML] EXCEÇÃO na busca "
                f"'{consulta}': {repr(e)}"
            )

    print(
        "[ML] TOTAL DE PRODUTOS ENCONTRADOS: "
        + str(len(produtos))
    )

    return list(produtos.values())


# ============================================================
# ENCONTRAR PROMOÇÃO
# ============================================================

def encontrar_promocao(item_id):

    try:

        item = ml_get(
            "/items/" + item_id
        )

    except Exception as e:

        print(
            f"[ML] Erro ao consultar item "
            f"{item_id}: {e}"
        )

        return None

    valor = item.get("price")

    valor_original = item.get(
        "original_price"
    )

    if valor is None:

        return None

    if valor_original is None:

        return None

    try:

        valor = float(valor)
        valor_original = float(valor_original)

    except (TypeError, ValueError):

        return None

    if valor_original <= valor:

        return None

    if valor < PRECO_MINIMO:

        return None

    if valor > PRECO_MAXIMO:

        return None

    desconto = (
        (valor_original - valor)
        / valor_original
    ) * 100

    if desconto < DESCONTO_MINIMO:

        return None

    return {
        "preco": valor,
        "preco_original": valor_original,
        "desconto": desconto
    }


# ============================================================
# ENVIAR TELEGRAM
# ============================================================

def enviar_telegram(produto):

    bot_token = os.environ.get(
        "TELEGRAM_BOT_TOKEN"
    )

    chat_id = os.environ.get(
        "TELEGRAM_CHAT_ID"
    )

    if not bot_token:

        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN não configurado."
        )

    if not chat_id:

        raise RuntimeError(
            "TELEGRAM_CHAT_ID não configurado."
        )

    titulo = produto.get(
        "titulo",
        "Produto"
    )

    preco = float(
        produto["preco"]
    )

    preco_original = float(
        produto["preco_original"]
    )

    desconto = float(
        produto["desconto"]
    )

    link = produto.get(
        "link",
        ""
    )

    imagem = produto.get(
        "imagem"
    )

    preco_formatado = (
        f"R$ {preco:,.2f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )

    original_formatado = (
        f"R$ {preco_original:,.2f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )

    texto = (
        "🔥 MEGA DESCONTO 🔥\n\n"
        f"🛒 {titulo}\n\n"
        "💰 OFERTA ENCONTRADA!\n\n"
        f"❌ De: {original_formatado}\n"
        f"✅ Por: {preco_formatado}\n"
        f"📉 {desconto:.0f}% OFF\n\n"
        "🛍️ Ver oferta:\n"
        f"{link}"
    )

    texto = texto[:1000]

    if imagem:

        response = requests.post(
            "https://api.telegram.org/bot"
            + bot_token
            + "/sendPhoto",
            json={
                "chat_id": chat_id,
                "photo": imagem,
                "caption": texto
            },
            timeout=30
        )

    else:

        response = requests.post(
            "https://api.telegram.org/bot"
            + bot_token
            + "/sendMessage",
            json={
                "chat_id": chat_id,
                "text": texto
            },
            timeout=30
        )

    if not response.ok:

        raise RuntimeError(
            "Erro no Telegram:\n"
            + response.text
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
                font-family: Arial;
                background: #f4f4f4;
                text-align: center;
                padding: 40px;
            }

            .box {
                background: white;
                max-width: 600px;
                margin: auto;
                padding: 30px;
                border-radius: 15px;
                box-shadow: 0 5px 20px
                    rgba(0,0,0,0.1);
            }

            a {
                display: block;
                padding: 15px;
                margin: 15px;
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

            <p>
                Bot de promoções do Mercado Livre
            </p>

            <hr>

            <a href="/autorizar">
                🔐 Conectar Mercado Livre
            </a>

            <a href="/ml-teste">
                🛒 Testar Mercado Livre
            </a>

            <a href="/buscar-teste">
                🔎 Testar busca de produtos
            </a>

            <a href="/oferta-teste">
                🔥 Buscar oferta de teste
            </a>

            <a href="/telegram-teste">
                📲 Testar Telegram
            </a>

        </div>

    </body>

    </html>
    """


# ============================================================
# AUTORIZAR MERCADO LIVRE
# ============================================================

@app.route("/autorizar")
def autorizar():

    client_id = os.environ.get(
        "ML_CLIENT_ID"
    )

    if not client_id:

        return (
            "ML_CLIENT_ID não configurado.",
            500
        )

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
    <html>

    <head>

        <meta http-equiv="refresh"
              content="0;url={url}">

    </head>

    <body>

        <p>
            Redirecionando para o Mercado Livre...
        </p>

        <p>

            <a href="{url}">
                Clique aqui
            </a>

        </p>

    </body>

    </html>
    """


# ============================================================
# CALLBACK
# ============================================================

@app.route("/callback")
def callback():

    erro = request.args.get(
        "error"
    )

    if erro:

        return f"""
        <h1>❌ Erro na autorização</h1>

        <p>
            {escape(erro)}
        </p>
        """, 400

    code = request.args.get(
        "code"
    )

    if not code:

        return """
        <h1>❌ Código não recebido</h1>
        """, 400

    try:

        exchange_code_for_token(
            code
        )

        return """
        <h1>✅ Mercado Livre conectado!</h1>

        <p>
            A autorização foi concluída.
        </p>

        <p>
            <a href="/ml-teste">
                🛒 Testar conexão
            </a>
        </p>

        <p>
            <a href="/buscar-teste">
                🔎 Testar busca
            </a>
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

        <pre>{escape(str(e))}</pre>

        <p>
            <a href="/autorizar">
                🔐 Autorizar novamente
            </a>
        </p>
        """, 500


# ============================================================
# TESTAR CONEXÃO
# ============================================================

@app.route("/ml-teste")
def ml_teste():

    try:

        usuario = ml_get(
            "/users/me"
        )

        nickname = usuario.get(
            "nickname",
            "não informado"
        )

        user_id = usuario.get(
            "id",
            "não informado"
        )

        return f"""
        <h1>✅ Mercado Livre funcionando!</h1>

        <p>
            <b>Usuário:</b>
            {escape(str(nickname))}
        </p>

        <p>
            <b>ID:</b>
            {escape(str(user_id))}
        </p>

        <hr>

        <a href="/buscar-teste">
            🔎 Testar busca
        </a>
        """

    except Exception as e:

        return f"""
        <h1>❌ Erro no Mercado Livre</h1>

        <pre>{escape(str(e))}</pre>

        <a href="/autorizar">
            🔐 Autorizar novamente
        </a>
        """, 500


# ============================================================
# TESTAR BUSCA
# ============================================================

@app.route("/buscar-teste")
def buscar_teste():

    try:

        produtos = buscar_produtos()

        if not produtos:

            return """
            <h1>❌ Nenhum produto encontrado</h1>

            <p>
                O buscador não encontrou produtos
                de catálogo com anúncios disponíveis.
            </p>

            <p>
                Confira os logs do Render.
            </p>

            <a href="/">
                Voltar
            </a>
            """

        html = f"""
        <h1>🔎 Produtos encontrados</h1>

        <p>
            Quantidade encontrada:
            <b>{len(produtos)}</b>
        </p>

        <hr>
        """

        for produto in produtos[:20]:

            titulo = produto.get(
                "title",
                "Sem título"
            )

            preco = produto.get(
                "price",
                "N/A"
            )

            item_id = produto.get(
                "id",
                "N/A"
            )

            html += f"""
            <p>
                <b>{escape(str(titulo))}</b><br>
                ID: {escape(str(item_id))}<br>
                Preço: {escape(str(preco))}
            </p>

            <hr>
            """

        html += """
        <a href="/oferta-teste">
            🔥 Procurar oferta
        </a>
        """

        return html

    except Exception as e:

        return f"""
        <h1>❌ Erro na busca</h1>

        <pre>{escape(str(e))}</pre>

        <a href="/">
            Voltar
        </a>
        """, 500


# ============================================================
# BUSCAR UMA OFERTA
# ============================================================

@app.route("/oferta-teste")
def oferta_teste():

    try:

        produtos = buscar_produtos()

        if not produtos:

            return """
            <h1>❌ Nenhum produto encontrado</h1>

            <p>
                A busca não retornou produtos.
            </p>
            """

        analisados = 0

        for produto in produtos:

            item_id = produto.get(
                "id"
            )

            if not item_id:
                continue

            try:

                promocao = encontrar_promocao(
                    item_id
                )

                analisados += 1

            except Exception as e:

                print(
                    f"[ML] Erro analisando "
                    f"{item_id}: {e}"
                )

                continue

            if not promocao:
                continue

            titulo = produto.get(
                "title",
                "Produto"
            )

            imagem = (
                produto.get(
                    "secure_thumbnail"
                )
                or
                produto.get(
                    "thumbnail"
                )
            )

            link = produto.get(
                "permalink",
                ""
            )

            oferta = {
                "titulo": titulo,
                "preco": promocao["preco"],
                "preco_original": promocao["preco_original"],
                "desconto": promocao["desconto"],
                "imagem": imagem,
                "link": link
            }

            enviar_telegram(
                oferta
            )

            return f"""
            <h1>🔥 OFERTA ENVIADA!</h1>

            <h2>
                {escape(str(titulo))}
            </h2>

            <p>
                De:
                R$ {promocao["preco_original"]:.2f}
            </p>

            <p>
                Por:
                R$ {promocao["preco"]:.2f}
            </p>

            <p>
                Desconto:
                {promocao["desconto"]:.1f}%
            </p>

            <p>
                📲 A oferta foi enviada para o Telegram.
            </p>
            """

        return f"""
        <h1>😕 Nenhuma promoção encontrada</h1>

        <p>
            Produtos analisados:
            <b>{analisados}</b>
        </p>

        <p>
            Desconto mínimo:
            <b>{DESCONTO_MINIMO}%</b>
        </p>

        <p>
            Nenhum produto encontrado possui
            desconto compatível com os filtros atuais.
        </p>

        <p>
            <a href="/oferta-teste">
                🔄 Tentar novamente
            </a>
        </p>
        """

    except Exception as e:

        return f"""
        <h1>❌ Erro ao procurar oferta</h1>

        <pre>{escape(str(e))}</pre>
        """, 500


# ============================================================
# TESTE TELEGRAM
# ============================================================

@app.route("/telegram-teste")
def telegram_teste():

    try:

        enviar_telegram({

            "titulo":
                "Teste do Mega Desconto",

            "preco":
                79.90,

            "preco_original":
                99.90,

            "desconto":
                20,

            "imagem":
                None,

            "link":
                "https://www.mercadolivre.com.br/"
        })

        return """
        <h1>✅ Telegram funcionando!</h1>

        <p>
            A mensagem foi enviada para o Telegram.
        </p>
        """

    except Exception as e:

        return f"""
        <h1>❌ Erro no Telegram</h1>

        <pre>{escape(str(e))}</pre>
        """, 500


# ============================================================
# SERVIDOR
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
