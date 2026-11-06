
import os
import random
import sys
from datetime import datetime, timedelta

RESET = "--reset" in sys.argv
if RESET:
    from pathlib import Path
    db = os.environ.get("DATABASE_PATH", str(Path(__file__).with_name("estoque.db")))
    if os.path.exists(db):
        os.remove(db)
        print(f"Banco removido: {db}")

from werkzeug.security import generate_password_hash  # noqa: E402

import app as sistema  # noqa: E402  (importar o app ja executa o init_db)

random.seed(42)
SENHA_DEMO = "Demo@123"
agora = datetime.now()


def data(dias_atras):
    return (agora - timedelta(days=dias_atras, hours=random.randint(0, 8))).strftime("%d/%m/%Y %H:%M")


USUARIOS = [
    ("Ana Souza", "ana.souza", "MTZ"),
    ("Bruno Lima", "bruno.lima", "FL1"),
    ("Carla Mendes", "carla.mendes", "FL2"),
    ("Diego Rocha", "diego.rocha", "FL3"),
]

PRODUTOS = [
    # nome, tipo, unidade, quantidade, minimo, cor_toner, especificacao
    ("Notebook Dell Latitude 5440", "Notebook", "MTZ", 6, 3, "", ("Intel Core i5-1345U", 16, "dual", "ssd_nvme", 512, 92, "excellent")),
    ("Notebook Dell Latitude 5440", "Notebook", "FL1", 2, 3, "", ("Intel Core i5-1345U", 16, "dual", "ssd_nvme", 512, 71, "good")),
    ("Notebook Lenovo ThinkPad E14", "Notebook", "FL2", 4, 2, "", ("AMD Ryzen 5 7530U", 8, "single", "ssd_nvme", 256, 55, "fair")),
    ("Notebook HP ProBook 440", "Notebook", "FL3", 1, 2, "", ("Intel Core i7-1255U", 16, "dual", "ssd_sata", 512, 34, "poor")),
    ("Desktop Dell OptiPlex 7010", "Desktop", "MTZ", 8, 4, "", ("Intel Core i5-13500", 16, "dual", "ssd_nvme", 512, None, "")),
    ("Desktop HP EliteDesk 800", "Desktop", "FL1", 3, 2, "", ("Intel Core i7-12700", 32, "dual", "ssd_nvme", 1024, None, "")),
    ("Monitor Dell P2422H 24\"", "Monitor", "MTZ", 15, 5, "", None),
    ("Monitor LG 27\" 4K", "Monitor", "FL2", 0, 2, "", None),
    ("Dock Station Dell WD19S", "Dock", "MTZ", 7, 3, "", None),
    ("Mouse Logitech M90", "Mouse", "FL1", 25, 10, "", None),
    ("Teclado Logitech K120", "Teclado", "FL3", 9, 10, "", None),
    ("Headset Jabra Evolve2 30", "Headset", "MTZ", 12, 5, "", None),
    ("Cabo HDMI 2m", "Cabos", "FL2", 30, 10, "", None),
    ("Smartphone Samsung Galaxy A35", "Celular", "MTZ", 4, 2, "", None),
    ("Toner HP 58A", "Toner", "MTZ", 6, 2, "Black", None),
    ("Toner Ricoh IM C300", "Toner", "FL1", 2, 2, "Cyan", None),
    ("Toner Ricoh IM C300", "Toner", "FL1", 3, 2, "Magenta", None),
    ("Toner Ricoh IM C300", "Toner", "FL1", 0, 2, "Yellow", None),
]

DESTINOS = ["Financeiro", "RH", "Engenharia", "Comercial", "Logística", "Compras", "Fornecedor"]

c = sistema.get_db()
x = c.cursor()

if x.execute("SELECT COUNT(*) FROM produtos").fetchone()[0] > 0 and not RESET:
    print("O banco ja possui itens. Use --reset para recriar com os dados de demonstracao.")
    c.close()
    sys.exit(0)

ids_usuarios = [x.execute("SELECT id FROM usuarios WHERE usuario='admin'").fetchone()[0]]
for nome, login, unidade in USUARIOS:
    x.execute(
        "INSERT OR IGNORE INTO usuarios(nome,usuario,senha_hash,planta,is_admin,ativo,criado_em) VALUES(?,?,?,?,0,1,?)",
        (nome, login, generate_password_hash(SENHA_DEMO), unidade, data(60)),
    )
    ids_usuarios.append(x.execute("SELECT id FROM usuarios WHERE usuario=?", (login,)).fetchone()[0])

for n, (nome, tipo, unidade, qtd, minimo, cor, spec) in enumerate(PRODUTOS, start=1):
    unico = tipo in ("Notebook", "Desktop", "Monitor", "Celular", "Dock")
    x.execute(
        """INSERT INTO produtos(nome,tipo,cor_toner,patrimonio,serial,planta,quantidade,estoque_minimo,observacao,criado_em)
           VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (nome, tipo, cor, f"PAT-{1000 + n}" if unico else "", f"SN{random.randint(100000, 999999)}" if unico else "",
         unidade, qtd, minimo, "Item de demonstração", data(45)),
    )
    produto_id = x.lastrowid
    if spec:
        proc, ram, canal, disco_tipo, disco_gb, bat, bat_status = spec
        x.execute(
            """INSERT INTO especificacoes_equipamento(produto_id,processador,ram_gb,ram_canal,armazenamento_tipo,
                   armazenamento_gb,bateria_saude,bateria_status,atualizado_em) VALUES(?,?,?,?,?,?,?,?,?)""",
            (produto_id, proc, ram, canal, disco_tipo, disco_gb, bat, bat_status, data(30)),
        )
    for _ in range(random.randint(1, 3)):
        tipo_mov = random.choice(["Entrada", "Retirada"])
        x.execute(
            """INSERT INTO movimentacoes(produto_id,usuario_id,tipo_movimento,quantidade,destino,observacao,data_movimento)
               VALUES(?,?,?,?,?,?,?)""",
            (produto_id, random.choice(ids_usuarios), tipo_mov, random.randint(1, 3),
             random.choice(DESTINOS) if tipo_mov == "Retirada" else "Fornecedor", "", data(random.randint(0, 30))),
        )

c.commit()
c.close()
print("Dados de demonstracao criados.")
print(f"  Admin:   admin / {sistema.ADMIN_PASSWORD}")
print(f"  Padrao:  ana.souza / {SENHA_DEMO}  (e os demais usuarios de exemplo)")
