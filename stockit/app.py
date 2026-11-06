"""
StockIT - Sistema web de controle de estoque de TI.

Flask + SQLite. Multiplas unidades, perfis Admin/Padrao, tema escuro,
3 idiomas (pt-BR, en-US, es-ES) e especificacoes tecnicas de Notebook/Desktop.
"""
import os
import re
import secrets
import sqlite3
from datetime import datetime
from functools import wraps

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from translations import IDIOMAS_DISPONIVEIS, TEXTOS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _carregar_env(caminho=os.path.join(BASE_DIR, ".env")):
    """Le um arquivo .env simples (CHAVE=valor) sem dependencias externas."""
    if not os.path.exists(caminho):
        return
    with open(caminho, encoding="utf-8") as arquivo:
        for linha in arquivo:
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                chave, valor = linha.split("=", 1)
                os.environ.setdefault(chave.strip(), valor.strip())


_carregar_env()

app = Flask(__name__)
# Defina SECRET_KEY no ambiente em producao. Sem ela, uma chave aleatoria e gerada
# a cada inicializacao (as sessoes expiram ao reiniciar o servidor).
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

DB = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "estoque.db"))
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@123")
SENHA_TEMPORARIA = os.environ.get("TEMP_PASSWORD", "Temp@123")

PLANTAS = [
    ("MTZ", "Matriz"),
    ("FL1", "Filial 1"),
    ("FL2", "Filial 2"),
    ("FL3", "Filial 3"),
]

TIPOS_ITEM = [
    "Notebook", "Desktop", "Monitor", "Celular", "Mouse", "Teclado", "Headset",
    "Dock", "Cabos", "Impressora", "Toner", "Acessório", "Outro",
]

TIPOS_COM_ESPECIFICACAO = ("Notebook", "Desktop")
RAM_CANAIS = ("single", "dual")
TIPOS_ARMAZENAMENTO = ("ssd_sata", "ssd_nvme", "hdd", "hybrid")
STATUS_BATERIA = ("excellent", "good", "fair", "poor")
CORES_TONER = ("Black", "Cyan", "Magenta", "Yellow")


def agora():
    return datetime.now().strftime("%d/%m/%Y %H:%M")


def get_db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def validar_senha(s):
    if len(s) < 8:
        return False, "A senha deve ter no mínimo 8 caracteres."
    if not re.search(r"\d", s):
        return False, "A senha deve conter pelo menos um número."
    if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=/\\\[\];\']', s):
        return False, "A senha deve conter pelo menos um caractere especial."
    return True, ""


def texto(chave):
    idioma = session.get("idioma", "pt-BR")
    catalogo = TEXTOS.get(idioma, TEXTOS["pt-BR"])
    return catalogo.get(chave, TEXTOS["pt-BR"].get(chave, chave))


# ---------------------------------------------------------------------------
# Banco de dados
# ---------------------------------------------------------------------------
def _adicionar_colunas(tabela, colunas):
    """Adiciona colunas que ainda nao existem (migracao para bancos antigos)."""
    c = get_db()
    x = c.cursor()
    existentes = [linha[1] for linha in x.execute(f"PRAGMA table_info({tabela})").fetchall()]
    for nome, definicao in colunas.items():
        if nome not in existentes:
            x.execute(f"ALTER TABLE {tabela} ADD COLUMN {nome} {definicao}")
    c.commit()
    c.close()


def init_db():
    c = get_db()
    x = c.cursor()
    x.execute(
        """CREATE TABLE IF NOT EXISTS usuarios(
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               nome TEXT NOT NULL,
               usuario TEXT NOT NULL UNIQUE,
               senha_hash TEXT NOT NULL,
               planta TEXT NOT NULL,
               is_admin INTEGER DEFAULT 0,
               ativo INTEGER DEFAULT 1,
               criado_em TEXT NOT NULL)"""
    )
    x.execute(
        """CREATE TABLE IF NOT EXISTS produtos(
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               nome TEXT NOT NULL,
               tipo TEXT NOT NULL,
               patrimonio TEXT,
               serial TEXT,
               planta TEXT NOT NULL,
               quantidade INTEGER DEFAULT 0,
               estoque_minimo INTEGER DEFAULT 0,
               observacao TEXT,
               criado_em TEXT NOT NULL)"""
    )
    x.execute(
        """CREATE TABLE IF NOT EXISTS movimentacoes(
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               produto_id INTEGER NOT NULL,
               usuario_id INTEGER NOT NULL,
               tipo_movimento TEXT NOT NULL,
               quantidade INTEGER NOT NULL,
               destino TEXT,
               observacao TEXT,
               data_movimento TEXT NOT NULL)"""
    )
    x.execute(
        """CREATE TABLE IF NOT EXISTS especificacoes_equipamento(
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               produto_id INTEGER NOT NULL UNIQUE,
               processador TEXT,
               ram_gb INTEGER,
               ram_canal TEXT,
               armazenamento_tipo TEXT,
               armazenamento_gb INTEGER,
               bateria_saude INTEGER,
               bateria_status TEXT,
               atualizado_em TEXT NOT NULL,
               FOREIGN KEY(produto_id) REFERENCES produtos(id))"""
    )
    c.commit()
    c.close()

    _adicionar_colunas("produtos", {
        "ativo": "INTEGER DEFAULT 1",
        "cor_toner": "TEXT",
    })
    _adicionar_colunas("usuarios", {
        "tema": "TEXT DEFAULT 'light'",
        "idioma": "TEXT DEFAULT 'pt-BR'",
        "mostrar_metricas": "INTEGER DEFAULT 1",
        "mostrar_estoque_tipo": "INTEGER DEFAULT 1",
        "mostrar_movimentacoes": "INTEGER DEFAULT 1",
    })

    c = get_db()
    x = c.cursor()
    x.execute("SELECT id FROM usuarios WHERE usuario=?", ("admin",))
    if not x.fetchone():
        x.execute(
            "INSERT INTO usuarios(nome,usuario,senha_hash,planta,is_admin,ativo,criado_em) VALUES(?,?,?,?,?,?,?)",
            ("Administrador", "admin", generate_password_hash(ADMIN_PASSWORD), "TODAS", 1, 1, agora()),
        )
    c.commit()
    c.close()


# ---------------------------------------------------------------------------
# Especificacoes tecnicas (Notebook / Desktop)
# ---------------------------------------------------------------------------
def _inteiro_opcional(campo, minimo, maximo=None):
    valor = request.form.get(campo, "").strip()
    if not valor:
        return None
    numero = int(valor)
    if numero < minimo or (maximo is not None and numero > maximo):
        raise ValueError(campo)
    return numero


def ler_especificacoes_form(tipo):
    """Retorna (dados, erro). Para tipos sem configuracao retorna (None, None)."""
    if tipo not in TIPOS_COM_ESPECIFICACAO:
        return None, None
    try:
        ram_gb = _inteiro_opcional("ram_gb", 0, 1024)
        armazenamento_gb = _inteiro_opcional("armazenamento_gb", 0, 100000)
        bateria_saude = _inteiro_opcional("bateria_saude", 0, 100) if tipo == "Notebook" else None
    except ValueError:
        return None, texto("spec_invalid_number")

    ram_canal = request.form.get("ram_canal", "").strip()
    armazenamento_tipo = request.form.get("armazenamento_tipo", "").strip()
    bateria_status = request.form.get("bateria_status", "").strip()
    return {
        "processador": request.form.get("processador", "").strip(),
        "ram_gb": ram_gb,
        "ram_canal": ram_canal if ram_canal in RAM_CANAIS else "",
        "armazenamento_tipo": armazenamento_tipo if armazenamento_tipo in TIPOS_ARMAZENAMENTO else "",
        "armazenamento_gb": armazenamento_gb,
        "bateria_saude": bateria_saude,
        "bateria_status": bateria_status if tipo == "Notebook" and bateria_status in STATUS_BATERIA else "",
    }, None


def salvar_especificacoes(x, produto_id, tipo, dados):
    """Usa o cursor da transacao atual. Remove a configuracao se o tipo nao exigir."""
    if tipo not in TIPOS_COM_ESPECIFICACAO or dados is None:
        x.execute("DELETE FROM especificacoes_equipamento WHERE produto_id=?", (produto_id,))
        return
    x.execute(
        """INSERT INTO especificacoes_equipamento(
               produto_id, processador, ram_gb, ram_canal,
               armazenamento_tipo, armazenamento_gb,
               bateria_saude, bateria_status, atualizado_em)
           VALUES(?,?,?,?,?,?,?,?,?)
           ON CONFLICT(produto_id) DO UPDATE SET
               processador=excluded.processador,
               ram_gb=excluded.ram_gb,
               ram_canal=excluded.ram_canal,
               armazenamento_tipo=excluded.armazenamento_tipo,
               armazenamento_gb=excluded.armazenamento_gb,
               bateria_saude=excluded.bateria_saude,
               bateria_status=excluded.bateria_status,
               atualizado_em=excluded.atualizado_em""",
        (
            produto_id, dados["processador"], dados["ram_gb"], dados["ram_canal"],
            dados["armazenamento_tipo"], dados["armazenamento_gb"],
            dados["bateria_saude"], dados["bateria_status"], agora(),
        ),
    )


# ---------------------------------------------------------------------------
# Autenticacao, permissoes e contexto
# ---------------------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if not session.get("usuario_id"):
            flash("Faça login para continuar.", "warning")
            return redirect(url_for("login"))
        return f(*a, **k)
    return w


def admin_required(f):
    @wraps(f)
    def w(*a, **k):
        if not session.get("usuario_id"):
            flash("Faça login para continuar.", "warning")
            return redirect(url_for("login"))
        if not session.get("is_admin"):
            flash("Você não tem permissão para acessar esta área.", "danger")
            return redirect(url_for("dashboard"))
        return f(*a, **k)
    return w


def planta_atual():
    return session.get("planta_atual", "TODAS") if session.get("is_admin") else session.get("planta")


def plantas_usuario():
    return PLANTAS if session.get("is_admin") else [p for p in PLANTAS if p[0] == session.get("planta")]


def filtro_planta(alias=None):
    atual = planta_atual()
    campo = f"{alias}.planta" if alias else "planta"
    if session.get("is_admin") and atual == "TODAS":
        return "", []
    return f"WHERE {campo}=?", [atual]


@app.context_processor
def ctx():
    return {
        "PLANTAS": PLANTAS,
        "planta_atual": planta_atual(),
        "plantas_usuario": plantas_usuario(),
    }


@app.context_processor
def contexto_traducao():
    idioma = session.get("idioma", "pt-BR")
    if idioma not in IDIOMAS_DISPONIVEIS:
        idioma = "pt-BR"
    textos = TEXTOS.get(idioma, TEXTOS["pt-BR"])

    def tr(chave):
        return textos.get(chave, TEXTOS["pt-BR"].get(chave, chave))

    return {
        "tr": tr,
        "idioma_atual": idioma,
        "idiomas_disponiveis": [
            {"codigo": codigo, "nome": TEXTOS[codigo]["language_name"]} for codigo in IDIOMAS_DISPONIVEIS
        ],
    }


# ---------------------------------------------------------------------------
# Rotas: acesso
# ---------------------------------------------------------------------------
@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("usuario", "").strip().lower()
        s = request.form.get("senha", "")
        c = get_db()
        x = c.cursor()
        x.execute("SELECT * FROM usuarios WHERE usuario=? AND ativo=1", (u,))
        r = x.fetchone()
        c.close()
        if r and check_password_hash(r["senha_hash"], s):
            session.clear()
            session.update(
                usuario_id=r["id"],
                nome=r["nome"],
                usuario=r["usuario"],
                planta=r["planta"],
                is_admin=bool(r["is_admin"]),
                planta_atual="TODAS" if r["is_admin"] else r["planta"],
            )
            session["idioma"] = r["idioma"] if r["idioma"] in IDIOMAS_DISPONIVEIS else "pt-BR"
            session["tema"] = r["tema"] if r["tema"] in ("light", "dark", "system") else "light"
            return redirect(url_for("dashboard"))
        flash("Usuário ou senha inválidos.", "danger")
    return render_template("login.html")


@app.route("/novo-acesso", methods=["GET", "POST"])
def novo_acesso():
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        u = request.form.get("usuario", "").strip().lower()
        p = request.form.get("planta", "")
        s = request.form.get("senha", "")
        cs = request.form.get("confirmar_senha", "")
        if not nome or not u or not p or not s or not cs:
            flash("Preencha todos os campos obrigatórios.", "danger")
            return render_template("novo_acesso.html")
        if p not in [x[0] for x in PLANTAS]:
            flash("Selecione uma unidade válida.", "danger")
            return render_template("novo_acesso.html")
        if s != cs:
            flash("As senhas não conferem.", "danger")
            return render_template("novo_acesso.html")
        ok, msg = validar_senha(s)
        if not ok:
            flash(msg, "danger")
            return render_template("novo_acesso.html")
        try:
            c = get_db()
            c.execute(
                "INSERT INTO usuarios(nome,usuario,senha_hash,planta,is_admin,ativo,criado_em) VALUES(?,?,?,?,?,?,?)",
                (nome, u, generate_password_hash(s), p, 0, 1, agora()),
            )
            c.commit()
            c.close()
            flash("Acesso criado com sucesso. Faça login para continuar.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Este usuário já existe.", "danger")
    return render_template("novo_acesso.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Sessão encerrada com sucesso.", "success")
    return redirect(url_for("login"))


@app.route("/mudar-planta", methods=["POST"])
@login_required
def mudar_planta():
    if session.get("is_admin"):
        p = request.form.get("planta_atual", "TODAS")
        session["planta_atual"] = p if p in [x[0] for x in PLANTAS] + ["TODAS"] else "TODAS"
    return redirect(request.referrer or url_for("dashboard"))


# ---------------------------------------------------------------------------
# Rotas: dashboard e estoque
# ---------------------------------------------------------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    c = get_db()
    x = c.cursor()
    w, p = filtro_planta()
    j = "AND" if w else "WHERE"

    x.execute(f"SELECT COUNT(*) total FROM produtos {w} {j} ativo=1", p)
    total = x.fetchone()["total"]
    x.execute(f"SELECT COALESCE(SUM(quantidade),0) total FROM produtos {w} {j} ativo=1", p)
    qtd = x.fetchone()["total"]
    x.execute(f"SELECT COUNT(*) total FROM produtos {w} {j} ativo=1 AND quantidade<=estoque_minimo", p)
    baixo = x.fetchone()["total"]
    x.execute(f"SELECT COUNT(*) total FROM produtos {w} {j} ativo=1 AND quantidade<=0", p)
    sem = x.fetchone()["total"]

    x.execute(
        f"""SELECT tipo, COUNT(*) itens_cadastrados, COALESCE(SUM(quantidade), 0) quantidade_total
            FROM produtos {w} {j} ativo=1
            GROUP BY tipo ORDER BY tipo""",
        p,
    )
    estoque_por_tipo = x.fetchall()

    wm, pm = filtro_planta("p")
    jm = "AND" if wm else "WHERE"
    x.execute(
        f"""SELECT m.*, p.nome produto, p.planta, u.nome usuario_nome
            FROM movimentacoes m
            JOIN produtos p ON p.id=m.produto_id
            JOIN usuarios u ON u.id=m.usuario_id
            {wm} {jm} p.ativo=1
            ORDER BY m.id DESC LIMIT 8""",
        pm,
    )
    mov = x.fetchall()

    x.execute(
        "SELECT mostrar_metricas, mostrar_estoque_tipo, mostrar_movimentacoes FROM usuarios WHERE id=?",
        (session["usuario_id"],),
    )
    prefs = x.fetchone()
    c.close()

    dashboard_prefs = {
        "mostrar_metricas": bool(prefs["mostrar_metricas"]) if prefs else True,
        "mostrar_estoque_tipo": bool(prefs["mostrar_estoque_tipo"]) if prefs else True,
        "mostrar_movimentacoes": bool(prefs["mostrar_movimentacoes"]) if prefs else True,
    }
    return render_template(
        "dashboard.html",
        total_itens=total,
        total_estoque=qtd,
        baixo_estoque=baixo,
        sem_estoque=sem,
        movimentos=mov,
        estoque_por_tipo=estoque_por_tipo,
        dashboard_prefs=dashboard_prefs,
    )


@app.route("/produtos")
@login_required
def produtos():
    busca = request.args.get("busca", "").strip()
    tipo_filtro = request.args.get("tipo", "").strip()

    c = get_db()
    x = c.cursor()
    w, p = filtro_planta("produtos")
    j = "AND" if w else "WHERE"
    w = f"{w} {j} produtos.ativo=1"

    if busca:
        w += " AND (produtos.nome LIKE ? OR produtos.patrimonio LIKE ? OR produtos.serial LIKE ?)"
        p += [f"%{busca}%"] * 3
    if tipo_filtro:
        w += " AND produtos.tipo=?"
        p.append(tipo_filtro)

    x.execute(
        f"""SELECT produtos.*,
                   e.processador, e.ram_gb, e.ram_canal,
                   e.armazenamento_tipo, e.armazenamento_gb,
                   e.bateria_saude, e.bateria_status
            FROM produtos
            LEFT JOIN especificacoes_equipamento e ON e.produto_id = produtos.id
            {w}
            ORDER BY produtos.nome""",
        p,
    )
    itens = x.fetchall()
    c.close()
    return render_template("produtos.html", produtos=itens, busca=busca, tipo_filtro=tipo_filtro, tipos=TIPOS_ITEM)


def _ler_form_produto():
    tipo = request.form.get("tipo", "").strip()
    cor = request.form.get("cor_toner", "").strip()
    return {
        "nome": request.form.get("nome", "").strip(),
        "tipo": tipo,
        "cor_toner": cor if tipo == "Toner" and cor in CORES_TONER else "",
        "patrimonio": request.form.get("patrimonio", "").strip(),
        "serial": request.form.get("serial", "").strip(),
        "quantidade": max(0, int(request.form.get("quantidade", 0) or 0)),
        "estoque_minimo": max(0, int(request.form.get("estoque_minimo", 0) or 0)),
        "observacao": request.form.get("observacao", "").strip(),
    }


@app.route("/produtos/novo", methods=["GET", "POST"])
@login_required
def novo_produto():
    if request.method == "POST":
        d = _ler_form_produto()
        d["planta"] = request.form.get("planta", "").strip() if session.get("is_admin") else session.get("planta")

        if not d["nome"] or d["tipo"] not in TIPOS_ITEM or d["planta"] not in [x[0] for x in PLANTAS]:
            flash("Nome, tipo e unidade são obrigatórios.", "danger")
            return redirect(url_for("novo_produto"))

        especificacoes, erro = ler_especificacoes_form(d["tipo"])
        if erro:
            flash(erro, "danger")
            return redirect(url_for("novo_produto"))

        c = get_db()
        x = c.cursor()
        x.execute(
            """INSERT INTO produtos(nome, tipo, cor_toner, patrimonio, serial, planta,
                                    quantidade, estoque_minimo, observacao, criado_em)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (d["nome"], d["tipo"], d["cor_toner"], d["patrimonio"], d["serial"], d["planta"],
             d["quantidade"], d["estoque_minimo"], d["observacao"], agora()),
        )
        salvar_especificacoes(x, x.lastrowid, d["tipo"], especificacoes)
        c.commit()
        c.close()
        flash("Item cadastrado com sucesso.", "success")
        return redirect(url_for("produtos"))
    return render_template("produto_form.html", tipos=TIPOS_ITEM, especificacao=None)


@app.route("/produtos/<int:produto_id>/editar", methods=["GET", "POST"])
@admin_required
def editar_produto(produto_id):
    c = get_db()
    x = c.cursor()
    x.execute("SELECT * FROM produtos WHERE id=? AND ativo=1", (produto_id,))
    produto = x.fetchone()
    if not produto:
        c.close()
        flash("Item não encontrado ou já excluído.", "danger")
        return redirect(url_for("produtos"))

    if request.method == "POST":
        d = _ler_form_produto()
        d["planta"] = request.form.get("planta", "").strip()
        if not d["nome"] or d["tipo"] not in TIPOS_ITEM or d["planta"] not in [x[0] for x in PLANTAS]:
            c.close()
            flash("Nome, tipo e unidade são obrigatórios.", "danger")
            return redirect(url_for("editar_produto", produto_id=produto_id))

        especificacoes, erro = ler_especificacoes_form(d["tipo"])
        if erro:
            c.close()
            flash(erro, "danger")
            return redirect(url_for("editar_produto", produto_id=produto_id))

        x.execute(
            """UPDATE produtos
               SET nome=?, tipo=?, cor_toner=?, patrimonio=?, serial=?, planta=?,
                   quantidade=?, estoque_minimo=?, observacao=?
               WHERE id=? AND ativo=1""",
            (d["nome"], d["tipo"], d["cor_toner"], d["patrimonio"], d["serial"], d["planta"],
             d["quantidade"], d["estoque_minimo"], d["observacao"], produto_id),
        )
        salvar_especificacoes(x, produto_id, d["tipo"], especificacoes)
        c.commit()
        c.close()
        flash("Item atualizado com sucesso.", "success")
        return redirect(url_for("produtos"))

    x.execute("SELECT * FROM especificacoes_equipamento WHERE produto_id=?", (produto_id,))
    especificacao = x.fetchone()
    c.close()
    return render_template("produto_form.html", tipos=TIPOS_ITEM, produto=produto, especificacao=especificacao)


@app.route("/produtos/<int:produto_id>/excluir", methods=["POST"])
@admin_required
def excluir_produto(produto_id):
    c = get_db()
    x = c.cursor()
    # Exclusao logica: o historico de movimentacoes e preservado.
    x.execute("UPDATE produtos SET ativo=0 WHERE id=? AND ativo=1", (produto_id,))
    alterados = x.rowcount
    c.commit()
    c.close()
    if alterados:
        flash("Item excluído do estoque. O histórico foi preservado.", "success")
    else:
        flash("Item não encontrado ou já excluído.", "warning")
    return redirect(url_for("produtos"))


# ---------------------------------------------------------------------------
# Rotas: movimentacoes
# ---------------------------------------------------------------------------
@app.route("/produtos/<int:produto_id>/movimentar", methods=["GET", "POST"])
@login_required
def movimentar(produto_id):
    c = get_db()
    x = c.cursor()
    x.execute("SELECT * FROM produtos WHERE id=? AND ativo=1", (produto_id,))
    prod = x.fetchone()
    if not prod:
        c.close()
        flash("Produto não encontrado.", "danger")
        return redirect(url_for("produtos"))

    if request.method == "POST":
        tipo = request.form.get("tipo_movimento")
        q = int(request.form.get("quantidade", 0) or 0)
        dest = request.form.get("destino", "").strip()
        obs = request.form.get("observacao", "").strip()
        if tipo not in ("Entrada", "Retirada") or q <= 0:
            c.close()
            flash("Informe uma quantidade válida.", "danger")
            return redirect(url_for("movimentar", produto_id=produto_id))
        nova = prod["quantidade"] + q if tipo == "Entrada" else prod["quantidade"] - q
        if nova < 0:
            c.close()
            flash("Quantidade insuficiente em estoque.", "danger")
            return redirect(url_for("movimentar", produto_id=produto_id))

        x.execute("UPDATE produtos SET quantidade=? WHERE id=?", (nova, produto_id))
        x.execute(
            """INSERT INTO movimentacoes(produto_id,usuario_id,tipo_movimento,quantidade,destino,observacao,data_movimento)
               VALUES(?,?,?,?,?,?,?)""",
            (produto_id, session["usuario_id"], tipo, q, dest, obs, agora()),
        )
        c.commit()
        c.close()
        flash("Movimentação registrada com sucesso.", "success")
        return redirect(url_for("movimentacoes"))
    c.close()
    return render_template("movimentar.html", produto=prod)


@app.route("/movimentacoes")
@login_required
def movimentacoes():
    busca = request.args.get("busca", "").strip()
    tipo = request.args.get("tipo", "").strip()
    planta_filtro = request.args.get("planta", "").strip()
    where, params = [], []

    if session.get("is_admin"):
        if planta_atual() != "TODAS":
            where.append("p.planta=?")
            params.append(planta_atual())
        elif planta_filtro in [p[0] for p in PLANTAS]:
            where.append("p.planta=?")
            params.append(planta_filtro)
    else:
        where.append("p.planta=?")
        params.append(session.get("planta"))

    if tipo in ("Entrada", "Retirada"):
        where.append("m.tipo_movimento=?")
        params.append(tipo)
    if busca:
        where.append(
            "(p.nome LIKE ? OR p.patrimonio LIKE ? OR p.serial LIKE ? OR u.nome LIKE ? "
            "OR u.usuario LIKE ? OR m.destino LIKE ? OR m.observacao LIKE ?)"
        )
        params += [f"%{busca}%"] * 7

    ws = "WHERE " + " AND ".join(where) if where else ""
    c = get_db()
    x = c.cursor()
    x.execute(
        f"""SELECT m.*, p.nome produto, p.tipo produto_tipo, p.patrimonio, p.serial, p.planta,
                   u.nome usuario_nome, u.usuario usuario_login
            FROM movimentacoes m
            JOIN produtos p ON p.id=m.produto_id
            JOIN usuarios u ON u.id=m.usuario_id
            {ws}
            ORDER BY m.id DESC""",
        params,
    )
    mov = x.fetchall()
    c.close()
    return render_template("movimentacoes.html", movimentos=mov, busca=busca, tipo=tipo, planta_filtro=planta_filtro)


# ---------------------------------------------------------------------------
# Rotas: usuarios (admin)
# ---------------------------------------------------------------------------
@app.route("/usuarios")
@admin_required
def listar_usuarios():
    c = get_db()
    us = c.execute("SELECT id,nome,usuario,planta,is_admin,ativo,criado_em FROM usuarios ORDER BY nome").fetchall()
    c.close()
    return render_template("usuarios.html", usuarios=us)


@app.route("/usuarios/novo", methods=["GET", "POST"])
@admin_required
def criar_usuario():
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        u = request.form.get("usuario", "").strip().lower()
        s = request.form.get("senha", "")
        cs = request.form.get("confirmar_senha", "")
        p = request.form.get("planta", "")
        adm = 1 if request.form.get("is_admin") == "on" else 0
        if not nome or not u:
            flash("Preencha todos os campos obrigatórios.", "danger")
            return render_template("criar_usuario.html")
        if not adm and p not in [x[0] for x in PLANTAS]:
            flash("Selecione uma unidade válida.", "danger")
            return render_template("criar_usuario.html")
        if s != cs:
            flash("As senhas não conferem.", "danger")
            return render_template("criar_usuario.html")
        ok, msg = validar_senha(s)
        if not ok:
            flash(msg, "danger")
            return render_template("criar_usuario.html")
        try:
            c = get_db()
            c.execute(
                "INSERT INTO usuarios(nome,usuario,senha_hash,planta,is_admin,ativo,criado_em) VALUES(?,?,?,?,?,?,?)",
                (nome, u, generate_password_hash(s), "TODAS" if adm else p, adm, 1, agora()),
            )
            c.commit()
            c.close()
            flash("Usuário criado com sucesso.", "success")
            return redirect(url_for("listar_usuarios"))
        except sqlite3.IntegrityError:
            flash("Este usuário já existe.", "danger")
    return render_template("criar_usuario.html")


@app.route("/usuarios/<int:user_id>/alternar-admin", methods=["POST"])
@admin_required
def alternar_admin(user_id):
    if user_id == session.get("usuario_id"):
        flash("Você não pode remover sua própria permissão admin.", "warning")
        return redirect(url_for("listar_usuarios"))
    c = get_db()
    x = c.cursor()
    x.execute("SELECT is_admin FROM usuarios WHERE id=?", (user_id,))
    u = x.fetchone()
    if u:
        novo = 0 if u["is_admin"] else 1
        x.execute(
            "UPDATE usuarios SET is_admin=?, planta=? WHERE id=?",
            (novo, "TODAS" if novo else PLANTAS[0][0], user_id),
        )
        c.commit()
    c.close()
    return redirect(url_for("listar_usuarios"))


@app.route("/usuarios/<int:user_id>/alternar-status", methods=["POST"])
@admin_required
def alternar_status(user_id):
    if user_id == session.get("usuario_id"):
        flash("Você não pode desativar seu próprio usuário.", "warning")
        return redirect(url_for("listar_usuarios"))
    c = get_db()
    c.execute("UPDATE usuarios SET ativo=CASE WHEN ativo=1 THEN 0 ELSE 1 END WHERE id=?", (user_id,))
    c.commit()
    c.close()
    return redirect(url_for("listar_usuarios"))


@app.route("/usuarios/<int:user_id>/resetar-senha", methods=["POST"])
@admin_required
def resetar_senha(user_id):
    if user_id == session.get("usuario_id"):
        flash("Por segurança, você não pode resetar sua própria senha por esta opção.", "warning")
        return redirect(url_for("listar_usuarios"))
    c = get_db()
    c.execute("UPDATE usuarios SET senha_hash=? WHERE id=?", (generate_password_hash(SENHA_TEMPORARIA), user_id))
    c.commit()
    c.close()
    flash(f"Senha redefinida para: {SENHA_TEMPORARIA}", "success")
    return redirect(url_for("listar_usuarios"))


# ---------------------------------------------------------------------------
# Rotas: conta do usuario
# ---------------------------------------------------------------------------
@app.route("/alterar-senha", methods=["GET", "POST"])
@login_required
def alterar_senha():
    if request.method == "POST":
        senha_atual = request.form.get("senha_atual", "")
        nova_senha = request.form.get("nova_senha", "")
        confirmar_senha = request.form.get("confirmar_senha", "")

        c = get_db()
        x = c.cursor()
        x.execute("SELECT senha_hash FROM usuarios WHERE id=?", (session["usuario_id"],))
        usuario = x.fetchone()

        erro = None
        if not usuario:
            erro = "Usuário não encontrado."
        elif not check_password_hash(usuario["senha_hash"], senha_atual):
            erro = "Senha atual incorreta."
        elif nova_senha != confirmar_senha:
            erro = "As senhas não conferem."
        else:
            ok, msg = validar_senha(nova_senha)
            if not ok:
                erro = msg

        if erro:
            c.close()
            flash(erro, "danger")
            return redirect(url_for("alterar_senha"))

        x.execute("UPDATE usuarios SET senha_hash=? WHERE id=?",
                  (generate_password_hash(nova_senha), session["usuario_id"]))
        c.commit()
        c.close()
        flash("Senha alterada com sucesso.", "success")
        return redirect(url_for("dashboard"))
    return render_template("alterar_senha.html")


@app.route("/meu-perfil", methods=["GET", "POST"])
@login_required
def meu_perfil():
    c = get_db()
    x = c.cursor()

    if request.method == "POST":
        tema = request.form.get("tema", "light")
        if tema not in ("light", "dark", "system"):
            tema = "light"
        idioma = request.form.get("idioma", "pt-BR")
        if idioma not in IDIOMAS_DISPONIVEIS:
            idioma = "pt-BR"
        prefs = [1 if request.form.get(campo) == "on" else 0
                 for campo in ("mostrar_metricas", "mostrar_estoque_tipo", "mostrar_movimentacoes")]

        x.execute(
            """UPDATE usuarios
               SET tema=?, idioma=?, mostrar_metricas=?, mostrar_estoque_tipo=?, mostrar_movimentacoes=?
               WHERE id=?""",
            (tema, idioma, *prefs, session["usuario_id"]),
        )
        c.commit()
        c.close()
        session["tema"] = tema
        session["idioma"] = idioma
        flash(TEXTOS[idioma]["preferences_saved"], "success")
        return redirect(url_for("meu_perfil"))

    x.execute(
        """SELECT id, nome, usuario, planta, is_admin, ativo, criado_em, tema, idioma,
                  mostrar_metricas, mostrar_estoque_tipo, mostrar_movimentacoes
           FROM usuarios WHERE id=?""",
        (session["usuario_id"],),
    )
    usuario = x.fetchone()
    if not usuario:
        c.close()
        session.clear()
        flash("Sua conta não foi encontrada. Faça login novamente.", "danger")
        return redirect(url_for("login"))

    x.execute(
        """SELECT COUNT(*) total,
                  COALESCE(SUM(CASE WHEN tipo_movimento='Entrada' THEN 1 ELSE 0 END),0) entradas,
                  COALESCE(SUM(CASE WHEN tipo_movimento='Retirada' THEN 1 ELSE 0 END),0) retiradas
           FROM movimentacoes WHERE usuario_id=?""",
        (session["usuario_id"],),
    )
    estatisticas = x.fetchone()

    x.execute(
        """SELECT m.data_movimento, m.tipo_movimento, m.quantidade, m.destino, p.nome produto
           FROM movimentacoes m
           JOIN produtos p ON p.id=m.produto_id
           WHERE m.usuario_id=?
           ORDER BY m.id DESC LIMIT 8""",
        (session["usuario_id"],),
    )
    atividades = x.fetchall()
    c.close()

    preferencias = {
        "tema": usuario["tema"] or "light",
        "idioma": usuario["idioma"] or "pt-BR",
        "mostrar_metricas": bool(usuario["mostrar_metricas"]),
        "mostrar_estoque_tipo": bool(usuario["mostrar_estoque_tipo"]),
        "mostrar_movimentacoes": bool(usuario["mostrar_movimentacoes"]),
    }
    return render_template("meu_perfil.html", usuario=usuario, estatisticas=estatisticas,
                           atividades=atividades, preferencias=preferencias)


init_db()

if __name__ == "__main__":
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8080")),
        debug=os.environ.get("FLASK_DEBUG", "0") == "1",
    )
