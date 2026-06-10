#!/usr/bin/env python3
"""
Auto-processador do inbox — motor GEMINI (barato).
Disparado por evento pelo Sussurro (via auto_processar.sh) logo após salvar.

Fluxo:
  1. Lê a nota do inbox.
  2. Pede à Gemini um PLANO kepano (ai_provider.planejar_inbox_kepano).
  3. EXECUTA o plano: cria as notas atômicas no lugar certo, com [[links]].
  4. Marca a nota do inbox como processado e loga.

Se a Gemini se declarar insegura (escalar_claude) ou der erro → sai com código 3
para o auto_processar.sh acionar o Claude (camada de exceção).

Uso: processar_inbox.py /caminho/para/nota_inbox.md
"""
import os
import sys
import re
import glob
import json
from datetime import datetime

HOME        = os.path.expanduser("~")
VAULT_ROOT  = os.path.join(HOME, "FernandaOS")
PESSOAL     = os.path.join(VAULT_ROOT, "fernanda-obsidian-main")
LOG_PATH    = os.path.join(PESSOAL, "Inbox", "_auto-processador.log")
SUSSURRO_DIR = os.path.dirname(os.path.abspath(__file__))

# Carrega o .env central (a GEMINI_API_KEY mora aqui), antes de importar ai_provider.
try:
    from dotenv import load_dotenv
    # secrets.env é a fonte operativa (o ~/.profile carrega ele). override=True faz
    # um edit no arquivo valer na hora, mesmo que o processo tenha herdado key velha.
    for _p in (os.path.join(HOME, ".config", "fernanda", ".env"),
               os.path.join(HOME, ".config", "fernanda", "secrets.env")):
        if os.path.exists(_p):
            load_dotenv(_p, override=True)
except Exception:
    pass

sys.path.insert(0, SUSSURRO_DIR)
import ai_provider  # noqa: E402

ESCALAR = 3  # exit code → auto_processar.sh chama o Claude


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts}  {msg}"
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line)


def slug(nome):
    """Nome de arquivo seguro (sem caracteres proibidos)."""
    nome = re.sub(r'[\\/:*?"<>|]', "", str(nome)).strip()
    return nome[:120] or "sem-titulo"


def titulos_existentes():
    out = []
    for base in ("Notes", "References", "Manuscritos"):
        for f in glob.glob(os.path.join(PESSOAL, base, "**", "*.md"), recursive=True):
            nome = os.path.basename(f)[:-3]
            if not nome.startswith("_"):
                out.append(nome)
    return sorted(set(out))


def paginas_livro():
    """Mapeia 'Título da página-mãe → pasta' para cada livro em Manuscritos/."""
    out = []
    for d in glob.glob(os.path.join(PESSOAL, "Manuscritos", "*")):
        if not os.path.isdir(d):
            continue
        rel = os.path.relpath(d, PESSOAL)
        mae = None
        for f in glob.glob(os.path.join(d, "*.md")):
            nome = os.path.basename(f)
            txt = ""
            try:
                with open(f, encoding="utf-8") as fh:
                    txt = fh.read(600)
            except Exception:
                pass
            if "tipo: livro" in txt or nome.lower().startswith("livro"):
                mae = nome[:-3]
                break
        if mae:
            out.append(f'"{mae}" → pasta "{rel}"')
    return out


def escrever_nota(nota):
    """Cria um arquivo .md a partir de uma entrada do plano. Não sobrescreve."""
    pasta = nota.get("pasta", "Notes").strip().strip("/")
    titulo = slug(nota.get("titulo", "sem-titulo"))
    md = nota.get("markdown", "")
    if not md.strip():
        return None
    destino = os.path.join(PESSOAL, pasta)
    os.makedirs(destino, exist_ok=True)
    path = os.path.join(destino, f"{titulo}.md")
    n = 2
    while os.path.exists(path):
        path = os.path.join(destino, f"{titulo} ({n}).md")
        n += 1
    with open(path, "w", encoding="utf-8") as f:
        f.write(md if md.endswith("\n") else md + "\n")
    return os.path.relpath(path, PESSOAL)


def marcar_inbox(note_path, status, receipt):
    """Marca a nota do inbox como processado/revisar e anexa o recibo."""
    try:
        with open(note_path, encoding="utf-8") as f:
            txt = f.read()
        txt = re.sub(r'(?m)^status:\s*inbox\s*$', f"status: {status}", txt, count=1)
        if receipt:
            txt = txt.rstrip() + f"\n\n---\n- [x] {receipt}\n"
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(txt)
    except Exception as e:
        log(f"  (aviso: não consegui marcar o inbox: {e})")


def main():
    if len(sys.argv) < 2 or not os.path.isfile(sys.argv[1]):
        log("✗ sem arquivo válido")
        return 1
    note_path = sys.argv[1]
    nome = os.path.basename(note_path)

    with open(note_path, encoding="utf-8") as f:
        nota_md = f.read()

    prov = ai_provider.provedor_ativo()
    if prov is None:
        log(f"✗ {nome}: nenhuma IA configurada → escalando")
        return ESCALAR

    log(f"→ {nome}: planejando com {prov}…")
    plano = ai_provider.planejar_inbox_kepano(
        nota_md,
        titulos_existentes=titulos_existentes(),
        paginas_livro=paginas_livro(),
    )

    if not isinstance(plano, dict) or "erro" in plano:
        motivo = plano.get("erro") if isinstance(plano, dict) else "resposta inválida"
        log(f"✗ {nome}: Gemini falhou ({motivo}) → escalando p/ Claude")
        return ESCALAR

    if plano.get("escalar_claude"):
        log(f"↑ {nome}: Gemini insegura ({plano.get('motivo','')}) → escalando p/ Claude")
        return ESCALAR

    notas = plano.get("notas") or []
    criadas = []
    for nt in notas:
        try:
            rel = escrever_nota(nt)
            if rel:
                criadas.append(rel)
        except Exception as e:
            log(f"  (aviso: falha ao criar '{nt.get('titulo','?')}': {e})")

    status = plano.get("inbox_status", "processado")
    resumo = plano.get("log", "") or (f"{len(criadas)} nota(s) criada(s)")
    if criadas:
        marcar_inbox(note_path, status, resumo)
        log(f"✓ {nome}: {len(criadas)} nota(s) → {', '.join(criadas)}")
    elif status == "revisar":
        marcar_inbox(note_path, "revisar", resumo)
        log(f"~ {nome}: deixado p/ #revisar — {resumo}")
    else:
        # Sem notas e sem revisar = provavelmente ops (TODO interativo).
        marcar_inbox(note_path, "processado", resumo)
        log(f"✓ {nome}: {resumo}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log(f"✗ erro inesperado: {e} → escalando")
        sys.exit(ESCALAR)
