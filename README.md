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

## Instalação por sistema

Baixe o zip do seu sistema na página de **[Releases](https://github.com/DamaTech00/sussurro/releases/latest)** (ou clone o repositório) e use os scripts da pasta `plataformas/`:

| Sistema | Instalar (1ª vez) | Abrir |
|---|---|---|
| 🐧 **Linux (Ubuntu/Debian)** | `plataformas/linux/instalar.sh` | menu de aplicativos → *Sussurro*, ou `plataformas/linux/iniciar.sh` |
| 🪟 **Windows 10/11** | duplo clique em `plataformas\windows\instalar.bat` | atalho *Sussurro* na Área de Trabalho |
| 🍎 **macOS** | duplo clique em `plataformas/macos/instalar.command` | duplo clique em `plataformas/macos/iniciar.command` |

O instalador cuida das dependências do sistema (Python, Tkinter, PortAudio, ffmpeg), cria o ambiente `.venv` e copia o `config.example.json` para `config.json`.

**Diferenças entre sistemas**
- **Áudio do PC (loopback):** funciona no Windows (WASAPI) e no Linux (PulseAudio/PipeWire). No macOS o sistema não oferece loopback nativo — instale um driver virtual como o [BlackHole](https://github.com/ExistentialAudio/BlackHole) para gravar o áudio do computador; o microfone funciona normalmente.
- **macOS:** na primeira gravação, autorize o Terminal em *Ajustes → Privacidade e Segurança → Microfone*.
- **Auto-processamento com Claude Code** (`auto_processar.sh`, `claude_processar.py`): só Linux/macOS; vem desligado por padrão.

### Manual (qualquer sistema)
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
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
