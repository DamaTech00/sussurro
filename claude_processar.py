#!/usr/bin/env python3
"""
Processa uma captura do Sussurro no cofre usando o Claude Code headless
(assinatura da Fê — custo marginal zero), no lugar do Gemini, que morreu.

Arquitetura:
  Sussurro salva a nota no Inbox  →  auto_processar.sh  →  ESTE script
    1. faz um SNAPSHOT dos .md do cofre (undo garantido, já que as árvores git
       têm alterações não commitadas e `git checkout` não seria confiável)
    2. chama `claude -p` com ferramentas RESTRITAS (ler/escrever no cofre; sem rm,
       sem sudo, sem rede) e o contrato em "Inbox/_PROCESSAR (instruções pro Claude).md"
    3. registra o recibo no log, marca a nota como processada e arquiva em _processados/

Uso:
  claude_processar.py <nota.md> [--dry-run] [--sem-snapshot]

Sai com 0 = processado · 1 = erro · 2 = dry-run concluído
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import tarfile
import time
from datetime import datetime

HOME        = os.path.expanduser("~")
VAULT_ROOT  = os.path.join(HOME, "Documentos", "FernandaOS")
MYSPACE     = os.path.join(VAULT_ROOT, "MySpace")
INBOX       = os.path.join(MYSPACE, "Inbox")
PROCESSADOS = os.path.join(INBOX, "_processados")
REGRAS      = os.path.join(INBOX, "_PROCESSAR (instruções pro Claude).md")
LOG         = os.path.join(INBOX, "_auto-processador.log")
BASE        = os.path.join(HOME, "sussurro")
LOGS_DIR    = os.path.join(BASE, "claude_logs")
SNAP_DIR    = os.path.join(LOGS_DIR, "snapshots")
USO_JSON    = os.path.join(LOGS_DIR, "uso.json")
CLAUDE      = os.path.join(HOME, ".local", "bin", "claude")

# Só isto o Claude pode usar. Fora daqui, negado automaticamente (headless).
TOOLS_OK  = ("Read,Write,Edit,Glob,Grep,"
             "Bash(mv:*),Bash(mkdir:*),Bash(ls:*),Bash(cat:*),Bash(wc:*),Bash(date:*)")
TOOLS_DRY = "Read,Glob,Grep,Bash(ls:*)"
TOOLS_NOT = ("Bash(rm:*),Bash(sudo:*),Bash(curl:*),Bash(wget:*),Bash(git:*),"
             "Bash(python:*),Bash(pip:*),WebFetch,WebSearch,Task,NotebookEdit")

MAX_LOGS = 40          # mantém os últimos N logs de execução
MAX_SNAPS = 30         # mantém os últimos N snapshots do cofre


def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str, silencioso: bool = False):
    linha = f"{ts()}  {msg}"
    try:
        os.makedirs(INBOX, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except Exception:
        pass
    if not silencioso:
        print(linha)


def podar(pasta: str, prefixo: str, maximo: int):
    """Mantém só os N arquivos mais recentes que casam com o prefixo."""
    try:
        arquivos = [p for p in glob.glob(os.path.join(pasta, prefixo + "*"))
                    if os.path.isfile(p)]
        arquivos.sort(key=os.path.getmtime, reverse=True)
        for antigo in arquivos[maximo:]:
            os.remove(antigo)
    except Exception:
        pass


def snapshot() -> str:
    """Backup dos .md do cofre antes de deixar o Claude escrever."""
    os.makedirs(SNAP_DIR, exist_ok=True)
    destino = os.path.join(SNAP_DIR, f"cofre_{datetime.now():%Y%m%d_%H%M%S}.tar.gz")
    try:
        with tarfile.open(destino, "w:gz") as tar:
            for raiz, dirs, arquivos in os.walk(VAULT_ROOT):
                dirs[:] = [d for d in dirs
                           if d not in (".git", "node_modules") and not d.startswith("_backup")]
                for a in arquivos:
                    if a.endswith(".md"):
                        caminho = os.path.join(raiz, a)
                        tar.add(caminho, arcname=os.path.relpath(caminho, VAULT_ROOT))
        podar(SNAP_DIR, "cofre_", MAX_SNAPS)
        return destino
    except Exception as e:
        return f"ERRO: {e}"


def montar_prompt(nota: str, dry: bool) -> str:
    if dry:
        return (
            "Você é o agente que organiza o inbox do Sussurro da Fernanda.\n"
            f"LEIA PRIMEIRO o contrato: {REGRAS}\n"
            f"Depois leia a captura: {nota}\n\n"
            "MODO SIMULAÇÃO: não escreva, não crie e não mova NADA no cofre.\n"
            "Responda apenas com:\n"
            "1. o tipo e o destino que você daria à captura (e por quê);\n"
            "2. a lista exata de arquivos que criaria ou editaria;\n"
            "3. o que você extrairia como tarefa/pendência;\n"
            "4. o que ficaria marcado #revisar por ambiguidade.\n"
            "Seja curto e específico. Sem preâmbulo."
        )
    return (
        "Você é o agente que organiza o inbox do Sussurro da Fernanda (capturas de voz).\n"
        f"LEIA PRIMEIRO e siga o contrato: {REGRAS}\n"
        f"Processe SOMENTE esta captura: {nota}\n\n"
        "Regras duras:\n"
        "- NUNCA apague arquivo nem conteúdo. Nada de `rm`.\n"
        "- NÃO mova nem apague a nota do inbox: um script cuida do arquivamento. "
        "Só acrescente a ela uma linha de recibo (o que você fez).\n"
        "- Não invente: o que estiver ambíguo fica marcado #revisar e listado no fim.\n"
        "- Ops que dependem de Calendar/Gmail (não disponíveis aqui) → 'TODO (interativo)'.\n"
        "- Caso clínico: anonimizar (sigilo médico/LGPD).\n"
        "- Conhecimento vai pro MySpace (Notes/); maquinário/ops pro MaestroVault.\n"
        "- Ao terminar, acrescente UMA linha em "
        f"{LOG} no formato: '<data> | <nota> | intencao=<x> | <resumo do que fez> | arquivado em _processados/'\n"
        "No fim, responda em no máximo 6 linhas: o que criou/editou e o que ficou em dúvida."
    )


def registrar_uso(dados: dict):
    """Acumula o 'custo de lista' relatado, só para a Fê acompanhar o consumo."""
    try:
        hist = []
        if os.path.exists(USO_JSON):
            with open(USO_JSON, encoding="utf-8") as f:
                hist = json.load(f)
        custo = dados.get("total_cost_usd") or 0
        uso = dados.get("usage") or {}
        hist.append({
            "quando": ts(),
            "custo_lista_usd": round(custo, 4),
            "tokens_saida": uso.get("output_tokens", 0),
            "tokens_cache_lidos": uso.get("cache_read_input_tokens", 0),
            "tokens_cache_criados": uso.get("cache_creation_input_tokens", 0),
            "turnos": dados.get("num_turns", 0),
            "negados": len(dados.get("permission_denials") or []),
        })
        hist = hist[-200:]
        with open(USO_JSON, "w", encoding="utf-8") as f:
            json.dump(hist, f, ensure_ascii=False, indent=1)
        total = sum(h["custo_lista_usd"] for h in hist)
        return custo, total, len(hist)
    except Exception:
        return 0, 0, 0


def marcar_processada(nota: str, status: str = "processado"):
    """Troca status: ... pelo status final no frontmatter."""
    try:
        with open(nota, encoding="utf-8") as f:
            txt = f.read()
        if txt.startswith("---"):
            fim = txt.find("\n---", 3)
            if fim > 0:
                cabeca, corpo = txt[:fim], txt[fim:]
                novos = []
                for linha in cabeca.splitlines():
                    if linha.strip().startswith("status:"):
                        novos.append(f"status: {status}")
                    else:
                        novos.append(linha)
                if not any(l.strip().startswith("status:") for l in novos):
                    novos.append(f"status: {status}")
                with open(nota, "w", encoding="utf-8") as f:
                    f.write("\n".join(novos) + corpo)
                return True
    except Exception:
        pass
    return False


def arquivar(nota: str) -> str:
    os.makedirs(PROCESSADOS, exist_ok=True)
    destino = os.path.join(PROCESSADOS, os.path.basename(nota))
    try:
        if os.path.abspath(nota) != os.path.abspath(destino):
            os.replace(nota, destino)
        return destino
    except Exception as e:
        log(f"✗ não consegui arquivar {os.path.basename(nota)}: {e}")
        return nota


def montar_prompt_briefing(conteudo: str, dry: bool) -> str:
    """Briefing = instrução nossa (não é captura de voz): mantém a VERDADE do cofre."""
    trava = ("MODO SIMULAÇÃO: não escreva, não crie e não mova NADA. "
             "Responda só com o plano (arquivos e mudanças) e as dúvidas.\n"
             if dry else
             "Execute as mudanças nos arquivos do cofre.\n")
    return (
        quem_esta_falando() + "\n"
        "Você é o agente que mantém a VERDADE do cofre da Fernanda (MySpace = cérebro, "
        "MaestroVault = maquinário/ops).\n"
        f"LEIA PRIMEIRO o roteador: {os.path.join(VAULT_ROOT, 'MaestroVault', '_ROUTER.md')}\n"
        f"{trava}\n"
        "Regras duras:\n"
        "- NUNCA apague arquivo nem conteúdo. Nada de `rm`.\n"
        "- ATUALIZE as notas canônicas existentes em vez de criar concorrentes. "
        "Se criar nota nova, ela é atômica e linka as existentes.\n"
        "- NÃO invente fato: o briefing é a fonte; o que não estiver nele e não estiver "
        "comprovado no cofre fica como está (ou vira #revisar).\n"
        "- Preserve dados sensíveis e a anonimização de caso clínico.\n"
        "- Datas: hoje é " + datetime.now().strftime("%d/%m/%Y") + ". A nota de verdade "
        "carrega a data da última atualização no título — atualize essa data.\n"
        "- Ao terminar, responda em até 8 linhas: arquivos editados, o que mudou, "
        "o que ficou em #revisar.\n\n"
        "════════ BRIEFING ════════\n" + conteudo
    )


# ── Modo TAREFA (sysadmin/casa): diagnóstico e correção reversível na máquina ──
TASK_TOOLS = ("Read,Write,Edit,Glob,Grep,"
              "Bash(journalctl:*),Bash(dmesg:*),Bash(ip:*),Bash(iw:*),Bash(nmcli:*),"
              "Bash(cat:*),Bash(ls:*),Bash(grep:*),Bash(tail:*),Bash(head:*),Bash(wc:*),"
              "Bash(date:*),Bash(systemctl status:*),Bash(systemctl list-units:*),"
              "Bash(ping:*),Bash(ss:*),Bash(lspci:*),Bash(lsusb:*),Bash(ethtool:*),"
              "Bash(uptime:*),Bash(sensors:*),Bash(sudo:*),"
              # arquivos, medição e disco (tarefas de armazenamento/ripagem)
              "Bash(df:*),Bash(du:*),Bash(find:*),Bash(stat:*),Bash(sort:*),Bash(uniq:*),"
              "Bash(mkdir:*),Bash(mv:*),Bash(cp:*),Bash(chmod:*),Bash(tee:*),"
              "Bash(awk:*),Bash(sed:*),Bash(sleep:*),Bash(pgrep:*),Bash(journalctl -k:*),"
              # ripagem de DVD
              "Bash(ffmpeg:*),Bash(ffprobe:*),Bash(nohup:*),Bash(lsblk:*),Bash(udevadm:*),"
              "Bash(udisksctl:*),Bash(dd if=/dev/sr0:*),"
              # rodar scripts nossos e avisar a Fê
              "Bash(bash /home/ferda/sussurro:*),Bash(hermes send:*),"
              "Bash(/home/ferda/.hermes/hermes-agent/venv/bin/hermes send:*)")
TASK_NOT = ("Bash(rm:*),Bash(dd:*),Bash(mkfs:*),Bash(fdisk:*),Bash(apt:*),Bash(dpkg:*),"
            "Bash(curl:*),Bash(wget:*),Bash(git:*),Bash(python:*),Bash(pip:*),"
            "WebFetch,WebSearch,Task,NotebookEdit")
RELATORIOS = os.path.join(HOME, "sussurro", "tarefas", "relatorios")
# Registro compartilhado: qualquer IA que mexa nesta máquina deve ler e escrever aqui.
REGISTRO = os.path.join(HOME, "Documentos", "REGISTRO-IA.md")


def quem_esta_falando() -> str:
    """Contexto de coordenação: evita que duas IAs pisem uma na outra (incidente de 01/nov)."""
    return (
        "## QUEM ESTÁ FALANDO COM VOCÊ\n"
        "Quem te aciona é o **Hermes**, a agente-orquestradora da Fernanda (a \"gerente\": roda num modelo\n"
        "barato, escreve o briefing e delega o trabalho pesado). A **Fernanda é a chefe**. Você é o executor.\n"
        "⚠️ Na máquina dela também há um **Claude Desktop** aberto — é **outro Claude, sem memória\n"
        "compartilhada com você**. Em 01/11/2026 isso causou prejuízo: a sessão do Desktop re-rippou um DVD\n"
        "por cima de um arquivo completo que o Hermes tinha acabado de entregar.\n"
        f"Antes de sobrescrever, mover ou apagar qualquer arquivo que possa ter sido tocado por outra IA,\n"
        f"leia o registro compartilhado: {REGISTRO}\n"
        "E **registre no fim do trabalho o que você fez**, acrescentando uma linha nesse arquivo.\n"
    )


def registrar(mensagem: str):
    """Deixa a linha do trabalho no registro compartilhado (para a outra IA e para a Fê)."""
    try:
        with open(REGISTRO, "a", encoding="utf-8") as f:
            f.write(f"| {datetime.now():%d/%m %H:%M} | estagiário (headless, via Hermes) | {mensagem} |\n")
    except Exception:
        pass


def montar_prompt_tarefa(conteudo: str, relatorio: str, dry: bool) -> str:
    """Tarefa técnica na máquina dela (rede, USB, disco, serviço...)."""
    trava = ("MODO SIMULAÇÃO: NÃO mude nada na máquina. Só investigue (comandos de leitura) "
             "e responda com o diagnóstico + a correção proposta.\n"
             if dry else
             "Aplique SOMENTE correções reversíveis e que não possam derrubar a rede.\n")
    return (
        quem_esta_falando() + "\n"
        "Você é o executor técnico da máquina da Fernanda (OptiPlex 7070, Ubuntu, usuário ferda). "
        "Ela te acessa À DISTÂNCIA pelo Telegram — se você derrubar a rede, você fica sem contato "
        "com ela.\n"
        f"{trava}\n"
        "Método obrigatório:\n"
        "1. INVESTIGUE com evidência (logs, estado atual, medição). Não suponha.\n"
        "2. Escreva seu diagnóstico e as evidências em: " + relatorio + "\n"
        "3. Só depois proponha/aplique correção.\n\n"
        "Regras duras:\n"
        "- NADA destrutivo. Não apague arquivo, não instale pacote, não mexa em partição/disco.\n"
        "- Correção que possa derrubar a rede, o Wi-Fi ou o container: NÃO aplique — descreva como "
        "proposta e deixe para ela decidir.\n"
        "- Toda mudança de config precisa ser reversível e você deve escrever no relatório "
        "exatamente como desfazer (comando de rollback).\n"
        "- Registre no relatório TODO comando que rodou e o resultado.\n"
        "- Se a causa não estiver comprovada, diga o que falta medir e deixe um monitor rodando "
        "pra coletar evidência (ex.: script que registra quedas com data/hora).\n"
        "- Não mexa no cofre (MySpace/MaestroVault) nesta tarefa.\n"
        "- Ao terminar, responda em até 10 linhas: diagnóstico · evidência · o que aplicou · "
        "o que está em dúvida · como desfazer.\n\n"
        "════════ TAREFA ════════\n" + conteudo
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("nota")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sem-snapshot", action="store_true")
    ap.add_argument("--briefing", action="store_true",
                    help="trata o arquivo como BRIEFING (não é captura: não arquiva nem "
                         "mexe em status de inbox)")
    ap.add_argument("--tarefa", action="store_true",
                    help="trata o arquivo como TAREFA técnica na máquina (diagnóstico + correção "
                         "reversível; não mexe no cofre)")
    args = ap.parse_args()

    nota = os.path.abspath(args.nota)
    dry = args.dry_run
    if not os.path.isfile(nota):
        log(f"✗ captura inexistente: {nota}")
        return 1
    if not os.path.isfile(CLAUDE):
        log(f"✗ Claude Code não encontrado em {CLAUDE}")
        return 1

    os.makedirs(LOGS_DIR, exist_ok=True)
    os.makedirs(SNAP_DIR, exist_ok=True)
    etiqueta = os.path.basename(nota)[:34]
    run_log = os.path.join(LOGS_DIR, f"{datetime.now():%Y%m%d_%H%M%S}_{etiqueta}.log")

    log(f"{'[SIMULAÇÃO] ' if dry else ''}▶ Claude Code assumindo {os.path.basename(nota)}")

    if not args.sem_snapshot and not dry and not args.tarefa:
        snap = snapshot()
        if snap.startswith("ERRO"):
            log(f"✗ snapshot falhou ({snap}) — abortando por segurança")
            return 1

    os.makedirs(RELATORIOS, exist_ok=True)
    nome_base = os.path.splitext(etiqueta)[0]          # evita "arquivo.md.md"
    relatorio = os.path.join(RELATORIOS, f"{datetime.now():%Y%m%d_%H%M%S}_{nome_base}.md")
    if args.tarefa:
        with open(nota, encoding="utf-8") as f:
            prompt = montar_prompt_tarefa(f.read(), relatorio, dry)
    elif args.briefing:
        with open(nota, encoding="utf-8") as f:
            prompt = montar_prompt_briefing(f.read(), dry)
    else:
        prompt = montar_prompt(nota, dry)

    if args.tarefa:
        raiz   = HOME
        tools  = TOOLS_DRY if dry else TASK_TOOLS
        negar  = TASK_NOT
        pasta  = HOME
    else:
        raiz   = VAULT_ROOT
        tools  = TOOLS_DRY if dry else TOOLS_OK
        negar  = TOOLS_NOT
        pasta  = VAULT_ROOT

    cmd = [CLAUDE, "-p", prompt,
           "--add-dir", raiz,
           "--allowedTools", tools,
           "--disallowedTools", negar,
           "--output-format", "json"]

    inicio = time.time()
    try:
        r = subprocess.run(cmd, cwd=pasta, capture_output=True,
                           text=True, timeout=1500)
    except subprocess.TimeoutExpired:
        log("✗ Claude Code estourou o tempo (25 min) — nada foi arquivado")
        return 1
    except Exception as e:
        log(f"✗ falha ao chamar o Claude Code: {e}")
        return 1
    duracao = time.time() - inicio

    try:
        dados = json.loads(r.stdout)
    except Exception:
        dados = {"result": (r.stdout or r.stderr or "")[:2000], "is_error": True}

    resposta = (dados.get("result") or "").strip()
    erro = bool(dados.get("is_error")) or r.returncode != 0
    negados = dados.get("permission_denials") or []
    custo, total, n = registrar_uso(dados)

    with open(run_log, "w", encoding="utf-8") as f:
        f.write(f"nota: {nota}\ndry_run: {dry}\nduracao_s: {duracao:.1f}\n"
                f"exit: {r.returncode}\ntools_negadas: {json.dumps(negados, ensure_ascii=False)}\n"
                f"custo_lista_usd: {custo}\n\n--- resposta ---\n{resposta}\n\n"
                f"--- stderr ---\n{(r.stderr or '')[:4000]}\n")
    podar(LOGS_DIR, "", MAX_LOGS)

    # ⚠️ O estagiário pode bater no LIMITE da assinatura: a API devolve isso como
    # se fosse resposta normal ("You've hit your 5-hour limit · resets 5:10pm"),
    # com exit 0. Sem esta checagem, o script logava "✅ executada" sem nada feito.
    marcas_limite = ("5-hour limit", "usage limit", "rate limit", "quota exceeded",
                     "too many requests", "resets ")
    if any(m in resposta.lower() for m in marcas_limite):
        log("⏳ LIMITE DE USO do Claude atingido — nada foi executado. "
            + resposta.splitlines()[0][:100])
        print(f"   (a resposta foi: {resposta[:160]})")
        return 1

    print(f"\n── resposta do Claude Code ({duracao:.0f}s) ──\n{resposta}\n")
    if negados:
        print(f"⚠ ferramentas negadas: {json.dumps(negados, ensure_ascii=False)}\n")

    if erro and not resposta:
        log(f"✗ Claude Code falhou (exit {r.returncode}) — log: {run_log}")
        return 1

    if dry:
        log(f"✅ simulação concluída — nada foi escrito. log: {run_log}")
        return 2

    if args.briefing or args.tarefa:
        rotulo = "briefing aplicado" if args.briefing else "tarefa executada"
        # ⚠️ O executor pode "terminar com sucesso" e NÃO ter feito o trabalho (ex.: recusou por
        # contradição no briefing, ou bateu em permissão). Isso já aconteceu em 01/11 (o commit dos
        # cofres foi marcado como feito sem ter sido feito). Aqui a gente grita, para o gerente ver.
        marcas_bloqueio = ("não executado", "nao executado", "não foi executado",
                           "bloqueado por permissão", "bloqueado por permissao",
                           "não consegui concluir", "não pude executar")
        if any(m in resposta.lower() for m in marcas_bloqueio):
            log("⚠️ ATENÇÃO: a resposta indica que o trabalho NÃO foi feito — revisar antes de "
                "considerar concluído:")
            log("    " + resposta.strip().replace("\n", " ")[:220])
            registrar(f"⚠️ {etiqueta}: resposta indica BLOQUEIO (não executado) — revisar")
        registrar(f"{rotulo}: {etiqueta}")
        log(f"✅ {rotulo} ({etiqueta}) | custo de lista US$ {custo:.4f} "
            f"(acumulado US$ {total:.2f} em {n} execuções)")
        if args.tarefa:
            print(f"   relatório: {relatorio}")
        print(f"   log detalhado: {run_log}")
        if not args.tarefa:
            print(f"   snapshot para desfazer: {SNAP_DIR}")
        return 0

    # Se o Claude marcou algo como ambíguo, a nota NÃO vira "processado" —
    # vira "revisar", pra dar pra achar depois com uma busca só.
    try:
        with open(nota, encoding="utf-8") as f:
            conteudo = f.read()
    except Exception:
        conteudo = ""
    final = "revisar" if ("#revisar" in conteudo or "#revisar" in resposta) else "processado"
    marcar_processada(nota, final)
    destino = arquivar(nota)
    log(f"✅ {final}: {os.path.basename(nota)} → {os.path.relpath(destino, VAULT_ROOT)} "
        f"| custo de lista US$ {custo:.4f} (acumulado US$ {total:.2f} em {n} execuções)")
    print(f"   log detalhado: {run_log}")
    print(f"   snapshot para desfazer: {SNAP_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
