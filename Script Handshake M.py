#DESATUALIZADO DEVIDO A INCAPACIDADE DE FAZER TESTES FUNCIONAIS, PELO HERCULES FUNCIONA
import socket
import os
import time
import threading
from threading import Lock
import tkinter as tk
from datetime import datetime

# CONFIGURAÇÕES GERAIS
HOST = "0.0.0.0"
PORT = 8899

BASE_DIR = r""

PASTA_ENVIAR = os.path.join(BASE_DIR, "ENVIAR")
PASTA_RECEBER = os.path.join(BASE_DIR, "RECEBER")
PASTA_LOG = os.path.join(BASE_DIR, "LOG")
XON  = b'\x11' #Caractere que faz o CNC trabalhar direto na rede
XOFF = b'\x13'

#Escolha de Handshake transferencia de programa ou direto da rede
#Transferencia de programa
HANDSHAKE_NORMAL = {
    b"A": "CNC01",
    b"B": "CNC02",
    b"C": "CNC03",
    b"D": "CNC04",
    b"E": "CNC05",
    b"F": "CNC06",
}
#Direto da rede
HANDSHAKE_DNC = {
    b"G": "CNC01",
    b"H": "CNC02",
    b"I": "CNC03",
    b"J": "CNC04",
    b"K": "CNC05",
    b"L": "CNC06",
}

#Criação de pastas
for maquina in set(HANDSHAKE_NORMAL.values()):
    os.makedirs(os.path.join(PASTA_ENVIAR, maquina), exist_ok=True) #Cria todas pastas de envio para cada maquina
os.makedirs(PASTA_RECEBER, exist_ok=True) #Pasta unica de recebimento PC
os.makedirs(PASTA_LOG, exist_ok=True) #Pasta de log por máquina

def log(msg, maquina="GERAL"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    caminho = os.path.join(PASTA_LOG, f"{maquina}.log")
    with open(caminho, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")
    print(f"[{maquina}] {msg}")
def log_geral_evento(maquina, ip, evento):
    log(f"[{maquina} | {ip}]{evento}", "GERAL")
#Selecionador
def pegar_arquivo(pasta):
    arquivos = [f for f in os.listdir(pasta)
                if os.path.isfile(os.path.join(pasta, f))]
    if not arquivos:
        return None
    return os.path.join(pasta, arquivos[0])

#Envio normal
def enviar_normal(conn, caminho, maquina):
    log("Envio NORMAL iniciado", maquina)

    with open(caminho, "rb") as f:
        dados=f.read()
    time.sleep(0.2)
    log("Iniciando envio do arquivo",maquina)
    for i in range(0, len(dados), 256):
        conn.send(dados[i:i+256])
        time.sleep(0.02)
    log("Transferencia finalizada", maquina)
    log_geral_evento(maquina, conn.getpeername()[0], "ENVIADO (NORMAL)")
#Direto da rede
def enviar_dnc(conn, caminho, maquina):
    log("Envio DNC iniciado", maquina)

    with open(caminho, "rb") as f:
        for linha in f:
            conn.sendall(linha)

            # controle XON / XOFF
            try:
                conn.settimeout(0.01)
                ctrl = conn.recv(1)
                if ctrl == XOFF:
                    log("XOFF recebido - pausa", maquina)
                    while True:
                        ctrl = conn.recv(1)
                        if ctrl == XON:
                            log("XON recebido - retomando", maquina)
                            break
            except socket.timeout:
                pass

    log("Programa finalizado", maquina)
    log_geral_evento(maquina, conn.getpeername()[0], "ENVIADO (DNC)")
    
def atender_conexao(conn, addr):
    conn.settimeout(1.0)
    ip = addr[0]
    print("Socket Conectado:", ip)
    log(f"Conectado: {addr}")
    estado = "IDLE"
    buffer = b""
    maquina = "DESCONHECIDA"
    log_geral_evento(maquina, ip, "CONEXÃO INICIADA")
    try:
        while True:
            Recebendo = False
            try:
                data = conn.recv(4096)
            except socket.timeout:
                if maquina in maquinas:
                    maquina_Online(maquina)
                continue
            if maquina in maquinas:
                maquina_Online(maquina)
            if not data:
                break
            for byte in data:
                b = bytes([byte])
                # ===================== IDLE =====================
                if estado == "IDLE":
                    # --- HANDSHAKE NORMAL ---
                    if b in HANDSHAKE_NORMAL:
                        maquina = HANDSHAKE_NORMAL[b]
                        maquina_conectada(maquina, ip)
                        pasta = os.path.join(PASTA_ENVIAR, maquina)
                        log("Handshake NORMAL recebido", maquina)
                        caminho = pegar_arquivo(pasta)
                        if caminho:
                            estado = "ENVIANDO"
                            maquina_atividade(maquina, "Enviando")
                            enviar_normal(conn, caminho, maquina)
                            maquina_atividade(maquina, "Repouso")
                            os.remove(caminho)
                            log("Arquivo removido após envio", maquina)
                            maquina_atividade(maquina, "Repouso")
                            maquina_Online(maquina)
                        estado = "IDLE"
                        continue
                    # --- HANDSHAKE DNC ---
                    if b in HANDSHAKE_DNC:
                        maquina = HANDSHAKE_DNC[b]
                        with lock:
                            maquinas[maquina]["status"] = "Handshake_DNC"
                            maquinas[maquina]["atividade"] = "Repouso"
                            maquinas[maquina]["ip"] = ip
                            maquinas[maquina]["last_seen"] = time.time()
                        pasta = os.path.join(PASTA_ENVIAR, maquina)
                        log("Handshake DNC recebido", maquina)
                        caminho = pegar_arquivo(pasta)
                        if caminho:
                            estado = "DNC"
                            maquina_atividade(maquina, "Usinando")
                            enviar_dnc(conn, caminho, maquina)
                            maquina_atividade(maquina, "Repouso")
                        estado = "IDLE"
                        continue
                    # --- INICIO RECEPÇÃO CNC -> PC ---
                    if b == b"%":
                        buffer = b"%"
                        estado = "RECEBENDO"
                        continue
                # ===================== RECEBENDO =====================
                elif estado == "RECEBENDO":
                    maquina_Online(maquina)
                    if not Recebendo:
                        maquina_atividade(maquina, "Recebendo")
                        root.update_idletasks()
                        Recebendo = True
                    buffer += b
                    if b == b"%":
                        nome = datetime.now().strftime(
                            f"{maquina}_%Y%m%d_%H%M%S.nc"
                        )
                        caminho = os.path.join(PASTA_RECEBER, nome)
                        with open(caminho, "wb") as f:
                            f.write(buffer)
                        log(f"Arquivo recebido: {nome}", maquina)
                        log_geral_evento(maquina, ip, f"RECEBIDO ({nome})")
                        buffer = b""
                        estado = "IDLE"
                        Recebendo = False
                        maquina_atividade(maquina, "Repouso")
                    continue
                # ===================== ENVIANDO / DNC =====================
                elif estado in ("ENVIANDO", "DNC"):
                    # Ignora qualquer dado recebido durante envio
                    continue

    except Exception as e:
        log(f"Erro: {e}", maquina)

    finally:
        if maquina in maquinas:
            maquina_Offline(maquina)
        conn.close()
        log("Conexão encerrada", maquina)
        log_geral_evento(maquina, ip, "CONEXÃO ENCERRADA")

#Loop do programa
def dnc_loop():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((HOST, PORT))
    sock.listen(20)
    log("Servidor DNC iniciado")
    while True:
        conn, addr = sock.accept()
        threading.Thread(target=atender_conexao, args=(conn, addr), daemon=True).start()
#--------------------------------------------------------------------------------------------- FRONT END -------------------------------------------------------------------------------------------------------

# máquinas fixas
NOMES_MAQUINAS = [
    "CNC01",
    "CNC02",
    "CNC03",
    "CNC04",
    "CNC05",
    "CNC06",
]

maquinas = {}
lock = Lock()

# inicializa todas como Offline
for nome in NOMES_MAQUINAS:
    maquinas[nome] = {
        "status": "Offline",
        "atividade":"Repouso",
        "ip":"-",
        "last_seen": 0
    }

TIMEOUT = 5  # segundos

def maquina_conectada(nome, ip):
    with lock:
        maquinas[nome]["status"] = "Handshake"
        maquinas[nome]["atividade"] = "Repouso"
        maquinas[nome]["ip"] = ip
        maquinas[nome]["last_seen"] = time.time()

def maquina_Online(nome):
    with lock:
        if maquinas[nome]["status"] !="Handshake_DNC":
            maquinas[nome]["status"] = "Online"
        maquinas[nome]["last_seen"] = time.time()

def maquina_atividade(nome, atividade):
    with lock:
        maquinas[nome]["atividade"] = atividade
        maquinas[nome]["last_seen"] = time.time()


def maquina_Offline(nome):
    with lock:
        maquinas[nome]["status"] = "Offline"
        maquinas[nome]["atividade"] = "Repouso"
        maquinas[nome]["ip"] = "-"

def monitor_timeout():
    while True:
        time.sleep(1)
        agora = time.time()
        with lock:
            for m in maquinas.values():
                if (
                    m["status"] !="Offline"
                    and m["atividade"] not in ("Usinando","Enviando")
                    and agora - m["last_seen"]>TIMEOUT
                ):
                    m["status"] = "Offline"
                    m["atividade"] = "Repouso"
                    m["ip"] = "-"

# ===================== GUI =====================

root = tk.Tk()
root.title("Monitor CNC - Rede")

frame = tk.Frame(root)
frame.pack(padx=10, pady=10)

cards = {}

def set_atividade(nome,atividade):
    maquina_atividade(nome,atividade)
    root.update_idletasks()

def criar_cards():
    for i, nome in enumerate(NOMES_MAQUINAS):
        f = tk.Frame(frame, width=200, height=70, relief="ridge", borderwidth=2)
        frame.configure(bg="#203864")
        root.configure(bg="#A3A6A5")
        f.grid(row=i//3, column=i%3, padx=10, pady=10)
        f.config(bg="#ededed")
        f.grid_propagate(False)

        canvas = tk.Canvas(f, width=20, height=20)
        canvas.place(relx=0.1, rely=0.5)

        lbl_nome = tk.Label(f, text=nome,bg=f["bg"], font=("bahnschrift", 12, "bold"))
        lbl_nome.place(relx=0.5, rely=0.8 ,anchor="center")

        lbl_ip = tk.Label(f, text="IP: -",bg=f["bg"],font=("bahnschrift",10),fg='#a3a6a5')
        lbl_ip.place(relx=0.05, rely=0.35)

        lbl_status = tk.Label(f, text="Status: Offline",bg=f["bg"],font=("bahnschrift",10))
        lbl_status.place(rely=0.01,relx=0.15)

        cards[nome] = (canvas, lbl_ip, lbl_status)

def atualizar_gui():
    with lock:
        for nome, dados in maquinas.items():
            canvas, lbl_ip, lbl_status = cards[nome]
            canvas.delete("all")

            if dados["status"] == "Offline":
                cor = "red"
            elif dados["status"] == "Handshake":
                cor = "orange"
            elif dados["status"] == "Handshake_DNC":
                cor = "blue"
            else:
                cor = "green"

            canvas.create_oval(2, 2, 18, 18, fill=cor)
            canvas.place(relx=0.1,rely=0.2,anchor="center")
            lbl_ip.config(text=f"IP: {dados['ip']}")
            lbl_status.config(text=f"{dados['status']} | {dados['atividade']}",fg=cor)

    root.after(500, atualizar_gui)

criar_cards()
threading.Thread(target=monitor_timeout, daemon=True).start()
root.after(200, atualizar_gui)

threading.Thread(target=dnc_loop, daemon=True).start()
root.mainloop()
