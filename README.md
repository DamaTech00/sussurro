# Sussurro — Gravador e Transcritor Inteligente

App de desktop (Python/Tkinter) que **grava áudio, transcreve com [faster-whisper](https://github.com/SYSTRAN/faster-whisper)** e usa IA para lapidar o texto, salvando direto numa pasta do Obsidian.

## O que faz
- Grava do microfone (e opcionalmente do áudio do PC via loopback).
- Transcreve localmente com `faster-whisper` (modelos `base`/`small`/...).
- **Lapidação por IA** (limpa/organiza a transcrição) com provedor configurável: **Gemini** (padrão), Anthropic ou OpenAI — via módulo unificado `ai_provider.py`.
- Salva a nota `.md` na pasta de inbox do Obsidian.
- Tem modo "IA OFF" (transcrição crua) e um modo 🎮 de estudo.

## Stack
- **Python** (`sussurro.py`, UI em Tkinter)
- Transcrição: `faster-whisper`
- Áudio: `sounddevice`, `soundcard`, `numpy`
- IA: `ai_provider.py` (Gemini / Anthropic / OpenAI)

## Rodar
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.example.json config.json    # ajuste os caminhos
python sussurro.py
```

## Configuração
- `config.json` — modelo do whisper, idioma, pasta do Obsidian (use o `config.example.json` como base).
- `.env` — chaves de IA (`GEMINI_API_KEY`, etc.). **Nunca** coloque chave no `config.json`.

> Extraído da minha suíte pessoal de automações. O `ai_provider.py` acompanha para a importação de IA resolver; alguns caminhos assumem a estrutura original (ajuste conforme seu ambiente).

---
© 2026 **Fernanda Damasceno de Souza** · **Dama Tech**. Todos os direitos reservados — ver [LICENSE](LICENSE).

Programa de computador de autoria própria (Lei 9.609/1998). Repositório público para fins de demonstração e comprovação de autoria/anterioridade.
