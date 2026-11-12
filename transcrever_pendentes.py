#!/usr/bin/env python3
"""
Transcreve os áudios do Sussurro que ficaram SEM nota (backlog), usando o Whisper
local na GPU — de graça, sem IA de lapidação. Depois, opcionalmente, entrega cada
nota ao Claude Code para organizar no cofre.

Por que existe: o app transcreve o que você grava ao vivo, mas áudios antigos
(ou gravados fora do app) ficam órfãos em transcricoes/*.wav, sem virar nota.

Uso:
  transcrever_pendentes.py                 # lista o que falta
  transcrever_pendentes.py --rodar         # transcreve tudo que falta p/ o Inbox
  transcrever_pendentes.py --rodar --processar   # + organiza cada nota com o Claude Code
  transcrever_pendentes.py --rodar --limite 1    # só o menor pendente (teste)
"""
import argparse
import glob
import os
import sys
from datetime import datetime

HOME      = os.path.expanduser("~")
SUSSURRO  = os.path.join(HOME, "sussurro")
WAV_DIR   = os.path.join(SUSSURRO, "transcricoes")
INBOX     = os.path.join(HOME, "Documentos", "FernandaOS", "MySpace", "Inbox")
MODELO    = "large-v3-turbo"


def _carregar_dicionario():
    """Dicionário pessoal de correções (sem IA) — fonte única: sussurro.py."""
    try:
        sys.path.insert(0, SUSSURRO)
        from sussurro import aplicar_correcoes, carregar_correcoes
        regras = carregar_correcoes()
        print(f"🔤 dicionário pessoal: {len(regras)} regra(s)")
        return lambda texto: aplicar_correcoes(texto, regras)
    except Exception as e:
        print(f"⚠ dicionário pessoal indisponível ({e}) — seguindo sem correções")
        return lambda texto: texto


def ja_transcrito(wav: str) -> bool:
    """Existe nota correspondente no Inbox, em _processados, ou um .md irmão?"""
    base = os.path.splitext(os.path.basename(wav))[0]
    candidatos = [os.path.join(os.path.dirname(wav), base + ".md"),
                  os.path.join(INBOX, base + "_inbox.md"),
                  os.path.join(INBOX, "_processados", base + "_inbox.md")]
    if any(os.path.exists(c) for c in candidatos):
        return True
    # a nota do app pode citar o áudio no frontmatter
    for pasta in (INBOX, os.path.join(INBOX, "_processados")):
        for md in glob.glob(os.path.join(pasta, "*.md")):
            try:
                with open(md, encoding="utf-8", errors="ignore") as f:
                    if base in f.read(4000):
                        return True
            except Exception:
                pass
    return False


def pendentes():
    wavs = [w for w in glob.glob(os.path.join(WAV_DIR, "*.wav")) if not ja_transcrito(w)]
    wavs.sort(key=os.path.getsize)
    return wavs


def montar_nota(wav: str, texto: str, duracao: float, tipo: str = "nota") -> str:
    base = os.path.splitext(os.path.basename(wav))[0]
    data, hora = (base.split("_") + ["", ""])[:2]
    hora = hora.replace("-", ":")
    return (
        "---\n"
        f'titulo: "Captura {data} {hora}"\n'
        f"data: {data}\n"
        f'hora: "{hora}"\n'
        "idioma: Português\n"
        f"duracao_segundos: {duracao:.0f}\n"
        "tags: []\n"
        f"tipo: {tipo}\n"
        f"intencao: {tipo}\n"
        "status: inbox\n"
        f'arquivo_audio: "{os.path.basename(wav)}"\n'
        "transcrito_local: whisper-" + MODELO + "\n"
        "---\n\n"
        f"# Captura — {data} às {hora}\n\n"
        f"> **Duração:** {duracao:.0f}s  |  **Modelo:** {MODELO} (local, GPU)\n"
        "> (sem lapidação por IA — transcrição crua do Whisper)\n\n"
        "---\n\n"
        "## Transcrição\n\n" + texto.strip() + "\n"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rodar", action="store_true", help="transcreve de verdade")
    ap.add_argument("--processar", action="store_true", help="entrega ao Claude Code depois")
    ap.add_argument("--limite", type=int, default=0)
    args = ap.parse_args()

    wavs = pendentes()
    if args.limite:
        wavs = wavs[:args.limite]
    if not wavs:
        print("✅ nenhum áudio pendente — tudo já tem nota.")
        return 0

    print(f"{len(wavs)} áudio(s) sem nota:")
    for w in wavs:
        mb = os.path.getsize(w) / 1e6
        print(f"   {mb:7.1f} MB  {os.path.basename(w)}")
    if not args.rodar:
        print("\n(simulação — rode com --rodar para transcrever)")
        return 0

    from faster_whisper import WhisperModel
    print(f"\ncarregando {MODELO} na GPU…")
    modelo = WhisperModel(MODELO, device="cuda", compute_type="int8_float16")
    os.makedirs(INBOX, exist_ok=True)
    corrigir = _carregar_dicionario()
    feitos = []
    for w in wavs:
        base = os.path.splitext(os.path.basename(w))[0]
        print(f"\n▶ {base} …", flush=True)
        try:
            segs, info = modelo.transcribe(w, language="pt", vad_filter=True,
                                           vad_parameters={"min_silence_duration_ms": 500})
            texto = corrigir("".join(s.text for s in segs).strip())
            duracao = getattr(info, "duration", 0) or 0
            if not texto:
                print("   ✗ sem fala detectada — nada salvo")
                continue
            destino = os.path.join(INBOX, f"{base}_inbox.md")
            with open(destino, "w", encoding="utf-8") as f:
                f.write(montar_nota(w, texto, duracao))
            print(f"   ✅ nota criada: {os.path.basename(destino)} ({len(texto)} caracteres)")
            feitos.append(destino)
        except Exception as e:
            print(f"   ✗ falhou: {e}")

    if args.processar and feitos:
        import subprocess
        print(f"\nentregando {len(feitos)} nota(s) ao Claude Code…")
        for nota in feitos:
            subprocess.run([sys.executable, os.path.join(SUSSURRO, "claude_processar.py"), nota])
    elif feitos:
        print(f"\n{len(feitos)} nota(s) no Inbox. Para organizar: "
              f"python3 {os.path.join(SUSSURRO, 'claude_processar.py')} <nota.md>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
