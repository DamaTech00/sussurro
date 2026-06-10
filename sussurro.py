"""
Sussurro v3 — Gravador e Transcritor Inteligente
IA: Gemini (padrão) / Anthropic / OpenAI  ·  Salva no Obsidian
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import sounddevice as sd
import numpy as np
try:
    import soundcard as sc        # captura do áudio do PC (loopback WASAPI)
except Exception:
    sc = None
import wave
import threading
import os
import sys
import subprocess
import json
import re
import glob
from datetime import datetime
from faster_whisper import WhisperModel
from dotenv import load_dotenv, set_key

# Carrega .env do pai (09_AUTOMATIONS)
ENV_PATH    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
load_dotenv(dotenv_path=ENV_PATH, override=False)

# Importa o módulo unificado de IA
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ai_provider

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
WAV_DIR     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "transcricoes")
ICONS_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "icons")
# inbox do vault (../../inbox a partir de 09_AUTOMATIONS/whisper-ui)
INBOX_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "inbox")

SAMPLE_RATE = 16000
CHANNELS    = 1

IDIOMAS = {
    "🇧🇷 Português":   "pt",
    "🇺🇸 English":     "en",
    "🇪🇸 Español":     "es",
    "🇩🇪 Deutsch":     "de",
    "🔍 Auto-detectar": None,
}

# Modos de uso do Sussurro: padrão "áudio → transformação → destino/ação".
# 'intencao' vai no frontmatter; 'instrucao' é o que o Claude deve FAZER com a nota
# ao processar o inbox; 'inbox' força o envio pro Claude executar a ação.
MODOS = [
    {"label": "📝 Nota / Transcrição", "intencao": "nota", "inbox": False,
     "desc": "Transcrição corrigida pelo contexto, conectada ao vault.", "instrucao": ""},
    {"label": "🤝 Reunião → ata + tarefas", "intencao": "reuniao", "inbox": True,
     "desc": "Vira ata + tarefas + eventos no Calendar (grave com 🔊 áudio do PC ligado).",
     "instrucao": "Gerar uma ATA (decisões e pontos-chave), extrair TAREFAS com prazos, "
                  "criar os compromissos no Google Calendar (calendário correspondente) e "
                  "registrar as pendências."},
    {"label": "📅 Agenda → Google Calendar", "intencao": "agenda", "inbox": True,
     "desc": "Fala os compromissos e o Claude cria os eventos no calendário certo.",
     "instrucao": "Extrair cada compromisso (título, data, hora) e criar no Google "
                  "Calendar, no calendário correspondente."},
    {"label": "📚 Estudo → flashcards (MedCof)", "intencao": "estudo", "inbox": True,
     "desc": "Dúvida falada vira flashcard Anki + caderno de erros na matéria certa.",
     "instrucao": "Transformar dúvidas e erros em flashcards Anki e entradas no caderno de "
                  "erros do MedCof, na matéria correta."},
    {"label": "🎮 Jogo MedCof (rodada)", "intencao": "jogo", "inbox": False,
     "desc": "Rodada do jogo de questões — transcrição crua da tua resposta/raciocínio, "
             "guardada separada em jogo-sessoes/ (não vira nota nem inbox).",
     "instrucao": ""},
    {"label": "💰 Gasto → finanças", "intencao": "financa", "inbox": True,
     "desc": "Fala um gasto e o Claude registra valor/categoria/data nas finanças.",
     "instrucao": "Extrair valor, categoria e data e registrar no controle financeiro "
                  "(10_FINANCE). Detalhe sensível só na planilha (privacidade)."},
    {"label": "🎬 Ideia → roteiro (canal)", "intencao": "roteiro", "inbox": True,
     "desc": "Ideia bruta vira roteiro do The Deep Sync com as marcações de edição.",
     "instrucao": "Estruturar como roteiro do The Deep Sync, no DNA de voz da Fernanda, "
                  "com as marcações [PICO/VISUAL/BATIDA/CLOSE]."},
    {"label": "🔬 Artigo → ficha de leitura", "intencao": "pesquisa", "inbox": True,
     "desc": "Comentário sobre um paper vira ficha (PICO, viés, GRADE).",
     "instrucao": "Estruturar como ficha de leitura científica: PICO, risco de viés, GRADE "
                  "e o que aproveitar; salvar na biblioteca de pesquisa."},
    {"label": "✉️ E-mail → rascunho", "intencao": "email", "inbox": True,
     "desc": "Dita o e-mail e o Claude deixa o RASCUNHO pronto (não envia).",
     "instrucao": "Redigir um RASCUNHO de e-mail no Gmail conforme o pedido. NÃO enviar — "
                  "só deixar pronto para a Fernanda revisar."},
    {"label": "🩺 Caso clínico (anonimizar)", "intencao": "caso", "inbox": True,
     "desc": "Narra um caso de plantão → vira caso de estudo SEM dado identificável.",
     "instrucao": "Estruturar como caso clínico ANONIMIZADO para estudo: remover TODO dado "
                  "identificável (LGPD/sigilo médico). Nunca expor o paciente."},
    {"label": "🔒 Diário privado", "intencao": "diario", "inbox": False,
     "desc": "Desabafo/diário: só transcreve limpo e guarda no vault PRIVADO. Não vira conteúdo.",
     "instrucao": ""},
    {"label": "🧠 Brainstorm → inbox", "intencao": "brainstorm", "inbox": True,
     "desc": "Mastiga uma ideia solta em problemas + sugestões pro Claude resolver.",
     "instrucao": ""},
]
MODO_LABELS     = [m["label"] for m in MODOS]
MODOS_POR_LABEL = {m["label"]: m for m in MODOS}

FONT  = "Segoe UI"
BG    = "#fafaf9"
BG2   = "#f3f4f6"
CARD  = "#ffffff"
REC   = "#ef4444"
TR    = "#6366f1"
GREEN = "#059669"
AMBER = "#f59e0b"
TXT   = "#111827"
TXT2  = "#6b7280"
BORDER = "#e5e7eb"


def load_config():
    cfg = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
    return cfg


def save_config(cfg):
    safe = {k: v for k, v in cfg.items()
            if "key" not in k.lower() and "secret" not in k.lower()}
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(safe, f, ensure_ascii=False, indent=2)


def save_env_key(name, value):
    env_file = ENV_PATH if os.path.exists(ENV_PATH) else ENV_PATH
    set_key(env_file, name, value)
    os.environ[name] = value


class Sussurro:
    def __init__(self, root):
        self.root = root
        self.root.title("Sussurro")
        self.root.geometry("800x660")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)
        _set_icon(root, os.path.join(ICONS_DIR, "sussurro.ico"))

        self.cfg          = load_config()
        self.recording    = False
        self.audio_mic    = []     # chunks do microfone (16 kHz mono)
        self.audio_media  = []     # chunks do áudio do PC (loopback, taxa nativa)
        self.streams      = []     # streams abertos nesta gravação
        self.model        = None
        self.current_wav  = None
        self.current_ts   = None
        self._timer_sec   = 0

        os.makedirs(WAV_DIR, exist_ok=True)
        obs = self.cfg.get("pasta_obsidian", "")
        if obs:
            os.makedirs(obs, exist_ok=True)

        self._build_ui()
        threading.Thread(target=self._load_model, daemon=True).start()

    # ─── UI ──────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Cabeçalho
        hdr = tk.Frame(self.root, bg=BG)
        hdr.pack(fill="x", padx=22, pady=(18, 0))
        tk.Label(hdr, text="🎙  Sussurro", font=(FONT, 20, "bold"),
                 fg=TXT, bg=BG).pack(side="left")
        tk.Button(hdr, text="⚙  Config", font=(FONT, 10),
                  bg=BG2, fg=TXT2, relief="flat", padx=10, pady=5,
                  cursor="hand2", command=self._open_settings).pack(side="right")

        tk.Label(self.root,
                 text="Grave, transcreva em qualquer idioma e salve no Obsidian.",
                 font=(FONT, 10), fg=TXT2, bg=BG).pack(anchor="w", padx=24, pady=(2, 10))

        # Barra de idioma + provedor
        bar = tk.Frame(self.root, bg=CARD,
                        highlightbackground=BORDER, highlightthickness=1)
        bar.pack(fill="x", padx=22, pady=(0, 10))

        tk.Label(bar, text="  Idioma:", font=(FONT, 10, "bold"),
                 fg=TXT, bg=CARD).pack(side="left", padx=(10, 4), pady=8)
        self.lang_var = tk.StringVar(value="🇧🇷 Português")
        ttk.Combobox(bar, textvariable=self.lang_var, values=list(IDIOMAS.keys()),
                     state="readonly", width=18, font=(FONT, 10)).pack(side="left", pady=8)

        tk.Label(bar, text="  IA:", font=(FONT, 10, "bold"),
                 fg=TXT, bg=CARD).pack(side="left", padx=(14, 4))
        self.prov_var = tk.StringVar()
        self.prov_combo = ttk.Combobox(bar, textvariable=self.prov_var,
                                        state="readonly", width=18, font=(FONT, 10))
        self.prov_combo.pack(side="left", pady=8)
        self._refresh_providers()

        tk.Label(bar, text="  Modo:", font=(FONT, 10, "bold"),
                 fg=TXT, bg=CARD).pack(side="left", padx=(14, 4))
        self.mode_var = tk.StringVar(value=MODO_LABELS[0])
        ttk.Combobox(bar, textvariable=self.mode_var, values=MODO_LABELS,
                     state="readonly", width=26, font=(FONT, 10)).pack(side="left", pady=8)
        tk.Button(bar, text="ℹ", font=(FONT, 11, "bold"), bg=CARD, fg=TR,
                  relief="flat", cursor="hand2", padx=4,
                  command=self._show_modos_help).pack(side="left", padx=(2, 0))

        # Toggle de lapidação por IA — desmarcado = só transcreve (texto cru),
        # não chama o Gemini/provider. Liga/desliga na hora.
        self.ia_lapidar_var = tk.BooleanVar(
            value=self.cfg.get("usar_ia_para_lapidacao", True))
        tk.Checkbutton(bar, text="🤖 Lapidar com IA", variable=self.ia_lapidar_var,
                       font=(FONT, 10), bg=CARD, fg=TXT, activebackground=CARD,
                       selectcolor=BG, cursor="hand2",
                       command=self._toggle_lapidar).pack(side="left", padx=(14, 0))

        self.ia_lbl = tk.Label(bar, text="", font=(FONT, 9), fg=GREEN, bg=CARD)
        self.ia_lbl.pack(side="right", padx=14)
        self._update_ia_badge()

        # Fonte de áudio — microfone e/ou mídia do PC (loopback)
        srcf = tk.Frame(self.root, bg=BG)
        srcf.pack(fill="x", padx=24, pady=(0, 4))
        tk.Label(srcf, text="Capturar:", font=(FONT, 10, "bold"),
                 fg=TXT, bg=BG).pack(side="left")
        self.mic_var   = tk.BooleanVar(value=True)
        self.media_var = tk.BooleanVar(value=False)
        tk.Checkbutton(srcf, text="🎤 Meu microfone", variable=self.mic_var,
                       font=(FONT, 10), bg=BG, fg=TXT, activebackground=BG,
                       selectcolor=CARD, cursor="hand2").pack(side="left", padx=(8, 0))
        tk.Checkbutton(srcf, text="🔊 Áudio do PC (mídia)", variable=self.media_var,
                       font=(FONT, 10), bg=BG, fg=TXT, activebackground=BG,
                       selectcolor=CARD, cursor="hand2").pack(side="left", padx=(8, 0))
        tk.Label(srcf, text="(marque os dois p/ misturar)", font=(FONT, 9),
                 fg=TXT2, bg=BG).pack(side="left", padx=(8, 0))

        # Status + timer
        sf = tk.Frame(self.root, bg=BG)
        sf.pack(fill="x", padx=22, pady=(0, 4))
        self.status_var = tk.StringVar(value="Carregando modelo Whisper...")
        self.status_lbl = tk.Label(sf, textvariable=self.status_var,
                                    font=(FONT, 11), fg=TXT2, bg=BG, anchor="w")
        self.status_lbl.pack(side="left")
        self.timer_var = tk.StringVar(value="")
        tk.Label(sf, textvariable=self.timer_var,
                 font=("Courier New", 13, "bold"), fg=REC, bg=BG).pack(side="right")

        # Botões
        bf = tk.Frame(self.root, bg=BG)
        bf.pack(pady=6)
        self.rec_btn = tk.Button(bf, text="⏺  GRAVAR",
                                  font=(FONT, 13, "bold"), bg=REC, fg="white",
                                  relief="flat", padx=24, pady=11, width=12,
                                  cursor="hand2", command=self.toggle_recording,
                                  activebackground="#dc2626", activeforeground="white")
        self.rec_btn.pack(side="left", padx=8)
        self.tr_btn = tk.Button(bf, text="✨  TRANSCREVER",
                                 font=(FONT, 13, "bold"), bg=TR, fg="white",
                                 relief="flat", padx=24, pady=11, width=14,
                                 cursor="hand2", command=self.transcribe,
                                 activebackground="#4f46e5", activeforeground="white",
                                 state="disabled")
        self.tr_btn.pack(side="left", padx=8)
        self.txt_btn = tk.Button(bf, text="📋  PROCESSAR TEXTO",
                                  font=(FONT, 12, "bold"), bg=GREEN, fg="white",
                                  relief="flat", padx=18, pady=11,
                                  cursor="hand2", command=self.process_text,
                                  activebackground="#047857", activeforeground="white")
        self.txt_btn.pack(side="left", padx=8)

        tk.Label(self.root,
                 text="↳ Grave a voz e clique Transcrever  ·  OU cole um texto na aba "
                      "“📝 Transcrição” e clique Processar Texto",
                 font=(FONT, 9), fg=TXT2, bg=BG).pack(pady=(0, 2))

        # Progress
        self.progress = ttk.Progressbar(self.root, mode="indeterminate", length=300)

        # Notebook
        nf = tk.Frame(self.root, bg=BG)
        nf.pack(fill="both", expand=True, padx=22, pady=(6, 4))
        self.nb = ttk.Notebook(nf)
        self.nb.pack(fill="both", expand=True)

        self.text_raw = self._tab(self.nb, "📝  Transcrição", "raw")
        self.text_ia  = self._tab(self.nb, "✨  Versão IA",   "ia", toolbar=True)
        self.text_md  = self._tab(self.nb, "📄  Notion",      "md",
                                   font=("Consolas", 10), bg="#1e1e2e",
                                   fg="#cdd6f4", toolbar=True)
        self._build_history_tab()

        # Rodapé
        ft = tk.Frame(self.root, bg=BG)
        ft.pack(fill="x", padx=22, pady=(2, 12))
        self.file_lbl = tk.Label(ft, text="Nenhuma gravação ainda.",
                                  font=(FONT, 9), fg=TXT2, bg=BG, anchor="w")
        self.file_lbl.pack(side="left")
        tk.Button(ft, text="📂 Abrir pasta", font=(FONT, 9),
                  bg=BG, fg=TXT2, relief="flat", cursor="hand2",
                  command=self._open_folder).pack(side="right")
        tk.Button(ft, text="🗑  Limpar", font=(FONT, 9),
                  bg=BG, fg=TXT2, relief="flat", cursor="hand2",
                  command=self.clear).pack(side="right", padx=8)

    def _tab(self, nb, label, attr, font=None, bg=CARD, fg=TXT, toolbar=False):
        frame = tk.Frame(nb, bg=bg)
        nb.add(frame, text=label)
        t = scrolledtext.ScrolledText(frame, wrap=tk.WORD,
                                       font=font or (FONT, 11),
                                       bg=bg, fg=fg, insertbackground=fg,
                                       relief="flat", padx=12, pady=10)
        setattr(self, f"text_{attr}", t)
        if toolbar:
            self._build_fmt_toolbar(frame, f"text_{attr}")
            self._setup_md_highlight(t)
        t.pack(fill="both", expand=True)
        return t

    def _build_fmt_toolbar(self, parent, target_attr):
        """Barra de formatação CLICÁVEL reutilizável (sem precisar saber Markdown).
        target_attr: nome do atributo que guarda o widget de texto-alvo."""
        def tgt():
            return getattr(self, target_attr)
        fmt_row = tk.Frame(parent, bg=BG2)
        fmt_row.pack(fill="x")
        fmt_btns = [
            ("H1",  lambda: self._fmt_line("# ", tgt())),
            ("H2",  lambda: self._fmt_line("## ", tgt())),
            ("H3",  lambda: self._fmt_line("### ", tgt())),
            ("N",   lambda: self._fmt_wrap("**", target=tgt())),         # negrito
            ("I",   lambda: self._fmt_wrap("*", target=tgt())),          # itálico
            ("S",   lambda: self._fmt_wrap("<u>", "</u>", target=tgt())),  # sublinhado
            ("• Lista", lambda: self._fmt_line("- ", tgt())),
            ("☐ Tarefa", lambda: self._fmt_line("- [ ] ", tgt())),
            ("❝ Citação", lambda: self._fmt_line("> ", tgt())),
            ("▸ Bloco", lambda: self._fmt_block(tgt())),                 # título colapsável
            ("‹ Código ›", lambda: self._fmt_wrap("`", target=tgt())),
            ("🔗 Link", lambda: self._fmt_link(tgt())),
            ("― Linha", lambda: tgt().insert("insert", "\n---\n")),
        ]
        for label, cmd in fmt_btns:
            tk.Button(fmt_row, text=label, font=(FONT, 9), bg=BG2, fg=TXT,
                      relief="flat", padx=6, pady=4, cursor="hand2",
                      command=cmd).pack(side="left", padx=1, pady=2)
        return fmt_row

    def _build_history_tab(self):
        frame = tk.Frame(self.nb, bg=CARD)
        self.nb.add(frame, text="📚  Histórico")

        top = tk.Frame(frame, bg=CARD)
        top.pack(fill="x", padx=10, pady=8)
        tk.Label(top, text="Transcrições salvas:", font=(FONT, 10, "bold"),
                 fg=TXT, bg=CARD).pack(side="left")
        tk.Button(top, text="Atualizar lista", font=(FONT, 9),
                  bg=BG2, fg=TXT2, relief="flat", padx=8, pady=4,
                  cursor="hand2", command=self._load_history).pack(side="right")

        pane = tk.PanedWindow(frame, orient="horizontal", bg=CARD)
        pane.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Lista de arquivos
        list_frame = tk.Frame(pane, bg=CARD, width=220)
        self.hist_list = tk.Listbox(list_frame, font=(FONT, 10),
                                     bg=BG2, fg=TXT, selectbackground=TR,
                                     selectforeground="white", relief="flat",
                                     highlightthickness=0)
        self.hist_list.pack(fill="both", expand=True)
        self.hist_list.bind("<<ListboxSelect>>", self._on_hist_select)
        pane.add(list_frame)

        # Visualizador
        view_frame = tk.Frame(pane, bg=CARD)

        # Linha 1 — ações
        btn_row = tk.Frame(view_frame, bg=CARD)
        btn_row.pack(fill="x", pady=(0, 4))
        tk.Button(btn_row, text="🔄 Reprocessar", font=(FONT, 9),
                  bg=TR, fg="white", relief="flat", padx=10, pady=5,
                  cursor="hand2", command=self._reprocess_hist).pack(side="left", padx=3)
        tk.Button(btn_row, text="💾 Salvar", font=(FONT, 9),
                  bg=GREEN, fg="white", relief="flat", padx=10, pady=5,
                  cursor="hand2", command=self._save_hist_edits).pack(side="left", padx=3)
        tk.Button(btn_row, text="🗑 Nota", font=(FONT, 9),
                  bg="#fee2e2", fg="#b91c1c", relief="flat", padx=10, pady=5,
                  cursor="hand2", command=self._delete_nota).pack(side="left", padx=3)
        tk.Button(btn_row, text="🗑 Áudio", font=(FONT, 9),
                  bg="#fee2e2", fg="#b91c1c", relief="flat", padx=10, pady=5,
                  cursor="hand2", command=self._delete_audio).pack(side="left", padx=3)

        # Linha 2 — formatação clicável (sem precisar saber Markdown)
        fmt_row = tk.Frame(view_frame, bg=BG2)
        fmt_row.pack(fill="x", pady=(0, 4))
        fmt_btns = [
            ("H1",  lambda: self._fmt_line("# ")),
            ("H2",  lambda: self._fmt_line("## ")),
            ("H3",  lambda: self._fmt_line("### ")),
            ("N",   lambda: self._fmt_wrap("**")),          # negrito
            ("I",   lambda: self._fmt_wrap("*")),           # itálico
            ("S",   lambda: self._fmt_wrap("<u>", "</u>")), # sublinhado
            ("• Lista", lambda: self._fmt_line("- ")),
            ("☐ Tarefa", lambda: self._fmt_line("- [ ] ")),
            ("❝ Citação", lambda: self._fmt_line("> ")),
            ("▸ Bloco", lambda: self._fmt_block()),         # título colapsável
            ("‹ Código ›", lambda: self._fmt_wrap("`")),
            ("🔗 Link", self._fmt_link),
            ("― Linha", lambda: self.hist_view.insert("insert", "\n---\n")),
        ]
        for label, cmd in fmt_btns:
            tk.Button(fmt_row, text=label, font=(FONT, 9), bg=BG2, fg=TXT,
                      relief="flat", padx=7, pady=4, cursor="hand2",
                      command=cmd).pack(side="left", padx=1, pady=2)

        self.hist_view = scrolledtext.ScrolledText(
            view_frame, wrap=tk.WORD, font=(FONT, 10),
            bg=CARD, fg=TXT, insertbackground=TXT,
            relief="flat", padx=10, pady=8
        )
        self.hist_view.pack(fill="both", expand=True)
        self._setup_md_highlight(self.hist_view)
        pane.add(view_frame)

        self._hist_files = []
        self._hist_current = None
        self._load_history()

    # ─── History ─────────────────────────────────────────────────────────────

    def _load_history(self):
        self.hist_list.delete(0, tk.END)
        self._hist_files = []
        pastas = [self.cfg.get("pasta_obsidian", "") or WAV_DIR, INBOX_DIR]
        encontrados = {}
        for pasta in pastas:
            for f in glob.glob(os.path.join(pasta, "*.md")):
                encontrados[os.path.abspath(f)] = f
        files = sorted(encontrados.values(),
                       key=lambda p: os.path.basename(p), reverse=True)
        for f in files:
            name = os.path.basename(f).replace(".md", "")
            prefixo = "🧠 " if "_brainstorm" in name else ""
            self.hist_list.insert(tk.END, f"{prefixo}{name}")
            self._hist_files.append(f)

    def _on_hist_select(self, _evt):
        sel = self.hist_list.curselection()
        if not sel:
            return
        path = self._hist_files[sel[0]]
        self._hist_current = path
        with open(path, encoding="utf-8") as f:
            content = f.read()
        self.hist_view.delete("1.0", tk.END)
        self.hist_view.insert("1.0", content)
        self._apply_md_highlight(self.hist_view)

    # ─── Formatação clicável + realce Markdown ─────────────────────────────────

    def _fmt_wrap(self, left, right=None, target=None):
        right = left if right is None else right
        t = target or self.hist_view
        try:
            sel = t.get("sel.first", "sel.last")
            t.delete("sel.first", "sel.last")
            t.insert("insert", f"{left}{sel}{right}")
        except tk.TclError:
            pos = t.index("insert")
            t.insert("insert", f"{left}{right}")
            t.mark_set("insert", f"{pos}+{len(left)}c")
        t.focus_set()
        self._apply_md_highlight(t)

    def _fmt_line(self, prefix, target=None):
        t = target or self.hist_view
        t.insert("insert linestart", prefix)
        t.focus_set()
        self._apply_md_highlight(t)

    def _fmt_link(self, target=None):
        t = target or self.hist_view
        try:
            sel = t.get("sel.first", "sel.last")
            t.delete("sel.first", "sel.last")
        except tk.TclError:
            sel = "texto"
        t.insert("insert", f"[{sel}](url)")
        t.focus_set()
        self._apply_md_highlight(t)

    def _fmt_block(self, target=None):
        """Insere um bloco/título COLAPSÁVEL (callout dobrável do Obsidian).
        O `-` depois de [!nota] faz o bloco abrir/fechar ao clicar, como no Notion."""
        t = target or self.hist_view
        try:
            sel = t.get("sel.first", "sel.last")
            t.delete("sel.first", "sel.last")
        except tk.TclError:
            sel = ""
        titulo = sel.split("\n")[0] if sel else "Título"
        corpo  = "\n".join(sel.split("\n")[1:]) if "\n" in sel else "Conteúdo aqui..."
        bloco = f"\n> [!nota]- {titulo}\n> {corpo}\n"
        t.insert("insert", bloco)
        t.focus_set()
        self._apply_md_highlight(t)

    def _setup_md_highlight(self, t):
        t.tag_configure("md_h",   font=(FONT, 12, "bold"), foreground="#4f46e5")
        t.tag_configure("md_bold", font=(FONT, 10, "bold"))
        t.tag_configure("md_underline", underline=True)
        t.tag_configure("md_quote", foreground=TXT2)
        t.tag_configure("md_code", font=("Consolas", 10), foreground="#b91c1c")
        t.tag_configure("md_task", foreground=GREEN)
        t.tag_configure("md_hr",  foreground=BORDER)

    def _apply_md_highlight(self, t):
        for tag in ("md_h", "md_bold", "md_underline", "md_quote",
                    "md_code", "md_task", "md_hr"):
            t.tag_remove(tag, "1.0", tk.END)
        linhas = t.get("1.0", tk.END).split("\n")
        for i, linha in enumerate(linhas, start=1):
            ls, le = f"{i}.0", f"{i}.end"
            if linha.startswith("#"):
                t.tag_add("md_h", ls, le)
            elif linha.startswith(("- [ ]", "- [x]")):
                t.tag_add("md_task", ls, le)
            elif linha.startswith(">"):
                t.tag_add("md_quote", ls, le)
            elif linha.strip() == "---":
                t.tag_add("md_hr", ls, le)
            # realce inline: **negrito** e <u>sublinhado</u>
            for m in re.finditer(r"\*\*(.+?)\*\*", linha):
                t.tag_add("md_bold", f"{i}.{m.start()}", f"{i}.{m.end()}")
            for m in re.finditer(r"<u>(.+?)</u>", linha):
                t.tag_add("md_underline", f"{i}.{m.start()}", f"{i}.{m.end()}")

    # ─── Deletar ───────────────────────────────────────────────────────────────

    def _delete_nota(self):
        if not self._hist_current:
            return
        nome = os.path.basename(self._hist_current)
        if not messagebox.askyesno("Deletar nota", f"Apagar definitivamente?\n\n{nome}"):
            return
        try:
            os.remove(self._hist_current)
        except OSError as e:
            messagebox.showerror("Erro", str(e))
            return
        self._hist_current = None
        self.hist_view.delete("1.0", tk.END)
        self._load_history()
        self._set_status(f"Nota apagada: {nome}", AMBER)

    def _delete_audio(self):
        if not self._hist_current:
            return
        base = os.path.basename(self._hist_current)
        base = base.replace(".md", "").replace("_brainstorm", "")
        wav = os.path.join(WAV_DIR, base + ".wav")
        if not os.path.exists(wav):
            messagebox.showinfo("Áudio", "Nenhum áudio .wav encontrado para esta nota.")
            return
        if not messagebox.askyesno("Deletar áudio",
                                   f"Apagar o áudio?\n\n{os.path.basename(wav)}\n\n"
                                   "(a nota de texto é mantida)"):
            return
        try:
            os.remove(wav)
        except OSError as e:
            messagebox.showerror("Erro", str(e))
            return
        self._set_status(f"Áudio apagado: {os.path.basename(wav)}", AMBER)

    def _save_hist_edits(self):
        if not self._hist_current:
            return
        content = self.hist_view.get("1.0", tk.END)
        with open(self._hist_current, "w", encoding="utf-8") as f:
            f.write(content)
        messagebox.showinfo("Salvo", f"Arquivo atualizado:\n{os.path.basename(self._hist_current)}")

    def _reprocess_hist(self):
        if not self._hist_current:
            return
        content = self.hist_view.get("1.0", tk.END)
        # Extrai a transcrição bruta entre os marcadores
        m = re.search(r'## 📝 Transcrição Original\n\n(.+?)(?:\n---|\Z)', content, re.DOTALL)
        texto = m.group(1).strip() if m else content.strip()
        provedor = IDIOMAS.get(self.lang_var.get())
        prov = self._prov_code()
        self._set_status("Re-processando com IA...", TR)
        threading.Thread(
            target=self._reprocess_thread,
            args=(texto, "pt", prov, self._hist_current),
            daemon=True
        ).start()

    def _reprocess_thread(self, texto, lang, prov, path):
        result = ai_provider.polir_transcricao(texto, lang, prov)
        if "erro" in result:
            self._set_status(f"Erro: {result['erro']}", REC)
            return
        with open(path, encoding="utf-8") as f:
            old = f.read()
        # Substitui ou adiciona a seção lapidada
        nova_secao = (
            f"\n---\n\n## 💡 Resumo (IA)\n\n{result.get('resumo','')}\n"
            f"\n---\n\n## ✨ Versão Lapidada (IA)\n\n{result.get('texto_lapidado','')}\n"
            f"\n---\n\n## 🏷️ Tópicos\n\n"
            + "  ".join(f"`{t}`" for t in result.get("tags", [])) + "\n"
        )
        # Remove seções antigas de IA e adiciona novas
        novo = re.sub(r'\n---\n\n## 💡.*', '', old, flags=re.DOTALL) + nova_secao
        with open(path, "w", encoding="utf-8") as f:
            f.write(novo)
        self.root.after(0, lambda: self.hist_view.delete("1.0", tk.END))
        self.root.after(0, lambda: self.hist_view.insert("1.0", novo))
        self._set_status("Re-processado e salvo!", GREEN)

    # ─── Providers ───────────────────────────────────────────────────────────

    def _refresh_providers(self):
        disponiveis = ai_provider.provedores_disponiveis()
        labels = [ai_provider.label_provedor(p) for p in disponiveis]
        self.prov_combo["values"] = labels if labels else ["Nenhum configurado"]
        if labels:
            pref = os.environ.get("AI_PROVIDER", "gemini")
            pref_label = ai_provider.label_provedor(pref)
            self.prov_var.set(pref_label if pref_label in labels else labels[0])
        else:
            self.prov_var.set("Nenhum configurado")

    def _prov_code(self) -> str | None:
        label = self.prov_var.get()
        for code in ["gemini", "anthropic", "openai"]:
            if ai_provider.label_provedor(code) == label:
                return code
        return ai_provider.provedor_ativo()

    def _toggle_lapidar(self):
        """Liga/desliga a lapidação por IA na hora e persiste no config."""
        self.cfg["usar_ia_para_lapidacao"] = self.ia_lapidar_var.get()
        save_config(self.cfg)
        self._update_ia_badge()

    def _update_ia_badge(self):
        if hasattr(self, "ia_lapidar_var") and not self.ia_lapidar_var.get():
            self.ia_lbl.configure(text="IA OFF · transcrição crua", fg=AMBER)
            return
        p = ai_provider.provedor_ativo()
        if p:
            self.ia_lbl.configure(text=f"IA: {ai_provider.NOMES_AMIGAVEIS[p]}", fg=GREEN)
        else:
            self.ia_lbl.configure(text="IA: não configurada", fg=TXT2)

    # ─── Modelo ──────────────────────────────────────────────────────────────

    def _load_model(self):
        try:
            size = self.cfg.get("modelo_whisper", "base")
            self.model = WhisperModel(size, device="cpu", compute_type="int8")
            self._set_status("Pronta! Selecione o idioma e clique Gravar.", GREEN)
        except Exception as e:
            self._set_status(f"Erro ao carregar modelo: {e}", REC)

    # ─── Gravação ────────────────────────────────────────────────────────────

    def toggle_recording(self):
        (self._stop_recording if self.recording else self._start_recording)()

    def _start_recording(self):
        if self.model is None:
            self._set_status("Aguarde, modelo ainda carregando...", AMBER)
            return

        cap_mic   = self.mic_var.get()
        cap_media = self.media_var.get()
        if not (cap_mic or cap_media):       # nada marcado → assume microfone
            cap_mic = True
            self.mic_var.set(True)
        self._cap_mic   = cap_mic
        self._cap_media = cap_media

        self.recording   = True
        self.audio_mic   = []
        self.audio_media = []
        self.streams     = []
        self._timer_sec  = 0
        self.rec_btn.configure(text="⏹  PARAR", bg="#dc2626")
        self.tr_btn.configure(state="disabled")

        # Microfone — 16 kHz mono (dispositivo de entrada padrão)
        if cap_mic:
            def cb_mic(indata, *_):
                if self.recording:
                    self.audio_mic.append(indata.copy())
            mic_stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS,
                                        dtype="float32", callback=cb_mic)
            mic_stream.start()
            self.streams.append(mic_stream)

        # Áudio do PC — loopback WASAPI via soundcard (gravado em thread própria)
        warn = None
        self._media_thread = None
        if cap_media:
            try:
                if sc is None:
                    raise RuntimeError("biblioteca 'soundcard' não instalada")
                spk = sc.default_speaker()
                self._loop_mic = sc.get_microphone(spk.name, include_loopback=True)
                self._media_sr = SAMPLE_RATE     # soundcard reamostra para 16 kHz
                self._media_thread = threading.Thread(
                    target=self._record_media_loop, daemon=True)
                self._media_thread.start()
            except Exception as e:
                self._cap_media = False
                warn = "⚠ Áudio do PC indisponível ({}). ".format(e)
                if not self._cap_mic:        # só mídia foi pedida e falhou → aborta
                    self.recording = False
                    self._close_streams()
                    self.rec_btn.configure(text="⏺  GRAVAR", bg=REC)
                    self._set_status(warn + "Nada para gravar.", REC)
                    return

        fontes = []
        if self._cap_mic:   fontes.append("🎤 microfone")
        if self._cap_media: fontes.append("🔊 áudio do PC")
        msg = "🔴  Gravando (" + " + ".join(fontes) + ")... clique PARAR quando terminar."
        self._set_status((warn + msg) if warn else msg, AMBER if warn else REC)
        self._tick_timer()

    def _record_media_loop(self):
        """Captura contínua do áudio do PC (loopback) numa thread, até parar."""
        try:
            with self._loop_mic.recorder(samplerate=SAMPLE_RATE) as rec:
                while self.recording:
                    data = rec.record(numframes=2048)   # ~128 ms por bloco
                    if self.recording and data is not None and len(data):
                        self.audio_media.append(data.copy())
        except Exception as e:
            self._set_status(f"⚠ Falha ao capturar áudio do PC: {e}", AMBER)

    def _close_streams(self):
        for s in getattr(self, "streams", []):
            try:
                s.stop()
                s.close()
            except Exception:
                pass
        self.streams = []
        th = getattr(self, "_media_thread", None)
        if th is not None:
            th.join(timeout=1.0)
            self._media_thread = None

    @staticmethod
    def _resample(x, sr_in, sr_out):
        if len(x) == 0 or sr_in == sr_out:
            return x.astype(np.float32)
        n_out = int(round(len(x) * sr_out / float(sr_in)))
        if n_out <= 0:
            return np.zeros(0, dtype=np.float32)
        old_idx = np.linspace(0.0, 1.0, num=len(x), endpoint=False)
        new_idx = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
        return np.interp(new_idx, old_idx, x).astype(np.float32)

    def _collect_audio(self):
        """Junta as fontes selecionadas numa faixa mono 16 kHz (soma + clip)."""
        tracks = []
        if getattr(self, "_cap_mic", False) and self.audio_mic:
            mic = np.concatenate(self.audio_mic, axis=0).astype(np.float32).reshape(-1)
            tracks.append(mic)
        if getattr(self, "_cap_media", False) and self.audio_media:
            med = np.concatenate(self.audio_media, axis=0).astype(np.float32)
            if med.ndim > 1:
                med = med.mean(axis=1)             # estéreo → mono
            med = self._resample(med, self._media_sr, SAMPLE_RATE)
            tracks.append(med)
        if not tracks:
            return None
        n = max(len(t) for t in tracks)
        mixed = np.zeros(n, dtype=np.float32)
        for t in tracks:
            if len(t) < n:
                t = np.pad(t, (0, n - len(t)))
            mixed += t
        if len(tracks) > 1:
            mixed *= 0.8                            # evita estouro ao somar fontes
        return mixed

    def _tick_timer(self):
        if self.recording:
            m, s = divmod(self._timer_sec, 60)
            self.timer_var.set(f"{m:02d}:{s:02d}")
            self._timer_sec += 1
            self.root.after(1000, self._tick_timer)
        else:
            self.timer_var.set("")

    def _stop_recording(self):
        self.recording = False
        self._close_streams()
        self.rec_btn.configure(text="⏺  GRAVAR", bg=REC)
        if self._save_wav():
            self._set_status(
                f"Gravação encerrada ({self._timer_sec}s). Clique Transcrever.", GREEN)
            self.tr_btn.configure(state="normal")
        else:
            self._set_status("Nenhum áudio capturado nesta gravação.", AMBER)

    def _save_wav(self):
        audio = self._collect_audio()
        if audio is None or len(audio) == 0:
            return False
        ts   = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        path = os.path.join(WAV_DIR, f"{ts}.wav")
        audio_i16 = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
        with wave.open(path, "w") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio_i16.tobytes())
        self.current_wav = path
        self.current_ts  = ts
        self.file_lbl.configure(text=f"Áudio: {os.path.basename(path)}")
        return True

    # ─── Transcrição ─────────────────────────────────────────────────────────

    def transcribe(self):
        if not self.current_wav or self.model is None:
            return
        for t in [self.text_raw, self.text_ia, self.text_md]:
            t.delete("1.0", tk.END)
        self.tr_btn.configure(state="disabled")
        self.rec_btn.configure(state="disabled")
        self._set_status("Transcrevendo...", TR)
        self.progress.pack(pady=4)
        self.progress.start(12)
        threading.Thread(target=self._run_transcription, daemon=True).start()

    def process_text(self):
        """Processa TEXTO digitado/colado na aba '📝 Transcrição' pelo modo atual.
        Permite usar resumo do MedCof, transcrição de YouTube, etc., sem gravar voz."""
        texto = self.text_raw.get("1.0", tk.END).strip()
        if not texto:
            self._set_status("Cole ou digite um texto na aba '📝 Transcrição' primeiro.", AMBER)
            self.nb.select(0)
            return
        for t in [self.text_ia, self.text_md]:
            t.delete("1.0", tk.END)
        self.current_ts  = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.current_wav = None        # sem áudio — origem é texto
        self.tr_btn.configure(state="disabled")
        self.rec_btn.configure(state="disabled")
        self.txt_btn.configure(state="disabled")
        self._set_status("Processando texto...", TR)
        self.progress.pack(pady=4)
        self.progress.start(12)
        lang = IDIOMAS.get(self.lang_var.get()) or "pt"
        threading.Thread(target=self._process_texto, args=(texto, lang, 0),
                         daemon=True).start()

    def _end_processing_ui(self):
        self.root.after(0, self.progress.stop)
        self.root.after(0, self.progress.pack_forget)
        self.root.after(0, lambda: (self.tr_btn.configure(state="normal"),
                                     self.rec_btn.configure(state="normal"),
                                     self.txt_btn.configure(state="normal")))

    def _run_transcription(self):
        try:
            lang_code = IDIOMAS.get(self.lang_var.get())
            segments, info = self.model.transcribe(self.current_wav, language=lang_code)
            texto = " ".join(s.text.strip() for s in segments).strip()
            lang_detected = lang_code or info.language
            duracao = info.duration
            self.root.after(0, lambda: self.text_raw.insert("1.0", texto))
        except Exception as e:
            self._set_status(f"Erro na transcrição: {e}", REC)
            self._end_processing_ui()
            return
        self._process_texto(texto, lang_detected, duracao)

    def _process_texto(self, texto, lang_detected, duracao):
        """Roteia um texto (vindo de voz OU colado) pelo modo selecionado."""
        if not (texto or "").strip():
            self._set_status("Nada para processar (texto vazio).", AMBER)
            self._end_processing_ui()
            return
        try:
            prov = self._prov_code()
            if not self.cfg.get("usar_ia_para_lapidacao", True):
                prov = None   # IA desligada → só transcrição crua, sem chamar o provider
            modo = self._selected_modo()

            if modo["intencao"] == "brainstorm":
                if not prov:
                    self._set_status("Brainstorm precisa de uma IA configurada.", REC)
                    self.root.after(0, lambda: self.text_ia.insert("1.0", texto))
                    return
                self._set_status(
                    f"Mastigando brainstorm com {ai_provider.NOMES_AMIGAVEIS.get(prov, prov)}...", TR)
                ia = ai_provider.processar_brainstorm(texto, lang_detected, prov)
                if "erro" in ia:
                    self._set_status(f"Erro: {ia['erro']}", REC)
                    self.root.after(0, lambda: self.text_ia.insert("1.0", texto))
                    return
                md = self._build_brainstorm_md(texto, ia, lang_detected, duracao)
                path = self._save_inbox(md)
                ia_text = self._brainstorm_preview(ia)
                self.root.after(0, lambda: (self.text_ia.insert("1.0", ia_text),
                                            self._apply_md_highlight(self.text_ia)))
                self.root.after(0, lambda: (self.text_md.insert("1.0", md),
                                            self._apply_md_highlight(self.text_md)))
                self.root.after(0, lambda: self.nb.select(1))
                self._set_status(
                    f"Brainstorm salvo no inbox: {os.path.basename(path)}. "
                    f"Peça ao Claude para processar o inbox.", GREEN)
                self.root.after(0, self._load_history)
                return

            # ── Fluxo unificado: nota de voz com detecção de comando + conexões ──
            ia = None
            if prov:
                self._set_status(
                    f"Mastigando com {ai_provider.NOMES_AMIGAVEIS.get(prov, prov)}...", TR)
                ia = ai_provider.processar_voz(texto, lang_detected, prov)
                if "erro" in ia:
                    self._set_status(f"IA indisponível ({ia['erro']}). Salvando só o texto.", AMBER)
                    ia = None

            md = self._build_voz_md(texto, ia, lang_detected, duracao,
                                    intencao=modo["intencao"],
                                    extra_instrucao=modo["instrucao"])
            tem_comando = bool(ia and ia.get("tem_comando"))

            if modo["intencao"] == "diario":
                # Diário/desabafo: NÃO vira comando, NÃO vai pro Claude. Guarda no vault privado.
                path = self._save_private(md)
                destino_msg = f"🔒 Diário salvo (privado): {os.path.basename(path)}."
            elif modo["intencao"] == "jogo":
                # Rodada do jogo: guarda separada; a Fernanda cola a transcrição pro Claude.
                path = self._save_jogo(md)
                destino_msg = (f"🎮 Rodada salva em jogo-sessoes: {os.path.basename(path)}. "
                               f"Cola a transcrição pro Claude jogar/corrigir.")
            elif modo["inbox"] or tem_comando:
                # Modos de ação (ou nota com comando) → inbox p/ o Claude executar.
                path = self._save_inbox(md)
                destino_msg = (f"{modo['label']} → inbox: {os.path.basename(path)}. "
                               f"Peça ao Claude para processar o inbox (ele executa).")
            else:
                self._save_md(md)
                destino_msg = "Nota salva e conectada. Veja a aba 'Markdown' ou 'Histórico'."

            ia_text = texto
            if ia:
                partes = []
                if ia.get("resumo"):   partes.append(f"📌 {ia['resumo']}")
                if ia.get("comandos"): partes.append("\n🤖 Comandos pro Claude:\n"
                                                      + "\n".join(f"  • {c}" for c in ia["comandos"]))
                if ia.get("conexoes"): partes.append("\n🔗 Conexões:\n"
                                                      + "  ".join(f"[[{c}]]" for c in ia["conexoes"]))
                if ia.get("texto_lapidado"):
                    partes.append("\n---\n" + ia["texto_lapidado"])
                ia_text = "\n".join(partes) if partes else texto

            self.root.after(0, lambda: (self.text_ia.insert("1.0", ia_text),
                                        self._apply_md_highlight(self.text_ia)))
            self.root.after(0, lambda: (self.text_md.insert("1.0", md),
                                        self._apply_md_highlight(self.text_md)))
            self.root.after(0, lambda: self.nb.select(1))
            self._set_status(destino_msg, GREEN)
            self.root.after(0, self._load_history)

        except Exception as e:
            self._set_status(f"Erro: {e}", REC)
        finally:
            self._end_processing_ui()

    def _build_md(self, texto, ia, lang, duracao):
        ts   = self.current_ts or datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        data = ts[:10]
        hora = ts[11:16].replace("-", ":")
        nomes = {"pt": "Português", "en": "English", "es": "Español", "de": "Deutsch"}
        lang_nome = nomes.get(lang, lang)

        tipo   = ia.get("tipo",   "anotacao") if ia else "anotacao"
        tags   = ia.get("tags",   [])         if ia else []
        resumo = ia.get("resumo", "")         if ia else ""
        tags_yaml = "[" + ", ".join(tags) + "]"

        md = (
            f"---\n"
            f'titulo: "Transcrição {data} {hora}"\n'
            f"data: {data}\n"
            f'hora: "{hora}"\n'
            f"idioma: {lang_nome}\n"
            f"duracao_segundos: {duracao:.0f}\n"
            f"tags: {tags_yaml}\n"
            f"tipo: {tipo}\n"
            f"projeto: metascouts\n"
            f'arquivo_audio: "{os.path.basename(self.current_wav or "")}"\n'
            f"---\n\n"
            f"# Transcricao — {data} as {hora}\n\n"
            f"> **Idioma:** {lang_nome}  |  **Duracao:** {duracao:.0f}s  |  **Tipo:** {tipo}\n\n"
            f"---\n\n"
            f"## Transcricao Original\n\n{texto}\n"
        )
        if resumo:
            md += f"\n---\n\n## Resumo (IA)\n\n{resumo}\n"
        if ia and "texto_lapidado" in ia:
            md += f"\n---\n\n## Versao Lapidada (IA)\n\n{ia['texto_lapidado']}\n"
        if tags:
            md += "\n---\n\n## Topicos\n\n" + "  ".join(f"`{t}`" for t in tags) + "\n"
        return md

    def _save_md(self, md):
        ts    = self.current_ts or datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        pasta = self.cfg.get("pasta_obsidian", "") or WAV_DIR
        path  = os.path.join(pasta, f"{ts}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(md)
        self.root.after(0, lambda: self.file_lbl.configure(
            text=f"Salvo: {os.path.basename(path)}"))

    def _save_private(self, md):
        """Modo Diário: salva no vault PRIVADO (desenvolvimento-pessoal), nunca no inbox."""
        ts    = self.current_ts or datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        vault = os.path.dirname(INBOX_DIR)
        pasta = os.path.join(vault, "04_PROJECTS", "desenvolvimento-pessoal", "diario-voz")
        os.makedirs(pasta, exist_ok=True)
        path  = os.path.join(pasta, f"{ts}_diario.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(md)
        self.root.after(0, lambda: self.file_lbl.configure(
            text=f"🔒 Privado: {os.path.basename(path)}"))
        return path

    def _save_jogo(self, md):
        """Modo Jogo: rodadas do jogo de questões num lugar só, fora das notas/inbox."""
        ts    = self.current_ts or datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        vault = os.path.dirname(INBOX_DIR)
        pasta = os.path.join(vault, "04_PROJECTS", "residency-system", "jogo-sessoes")
        os.makedirs(pasta, exist_ok=True)
        path  = os.path.join(pasta, f"{ts}_rodada.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(md)
        self.root.after(0, lambda: self.file_lbl.configure(
            text=f"🎮 Rodada: {os.path.basename(path)}"))
        return path

    def _build_voz_md(self, texto, ia, lang, duracao, intencao="nota", extra_instrucao=""):
        """Nota de voz unificada: transcrição corrigida + ação do modo + conexões [[ ]]."""
        ts   = self.current_ts or datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        data = ts[:10]
        hora = ts[11:16].replace("-", ":")
        nomes = {"pt": "Português", "en": "English", "es": "Español", "de": "Deutsch"}
        lang_nome = nomes.get(lang, lang)

        ia = ia or {}
        texto_lap = ia.get("texto_lapidado", texto) or texto
        resumo    = ia.get("resumo", "")
        tags      = ia.get("tags", []) or []
        tipo      = ia.get("tipo", "anotacao")
        categoria = ia.get("categoria_sugerida", "inbox")
        comandos  = ia.get("comandos", []) or []
        conexoes  = ia.get("conexoes", []) or []
        tem_cmd   = bool(ia.get("tem_comando"))
        acionavel = bool(extra_instrucao) or tem_cmd
        status    = ("privada" if intencao == "diario"
                     else "rodada_jogo" if intencao == "jogo"
                     else "aguardando_claude" if acionavel else "arquivada")
        tags_yaml = "[" + ", ".join(str(t) for t in tags) + "]"
        conx_yaml = "[" + ", ".join(f'"{c}"' for c in conexoes) + "]"

        md = (
            f"---\n"
            f'titulo: "Nota de voz {data} {hora}"\n'
            f"data: {data}\n"
            f'hora: "{hora}"\n'
            f"idioma: {lang_nome}\n"
            f"duracao_segundos: {duracao:.0f}\n"
            f"tags: {tags_yaml}\n"
            f"tipo: {tipo}\n"
            f"intencao: {intencao}\n"
            f"categoria_sugerida: {categoria}\n"
            f"conexoes: {conx_yaml}\n"
            f"tem_comando: {str(tem_cmd).lower()}\n"
            f"status: {status}\n"
            f'arquivo_audio: "{os.path.basename(self.current_wav or "")}"\n'
            f"---\n\n"
            f"# Nota de voz — {data} às {hora}\n\n"
            f"> **Tipo:** {tipo}  |  **Idioma:** {lang_nome}  |  **Duração:** {duracao:.0f}s\n\n"
        )
        if resumo:
            md += f"## Resumo\n\n{resumo}\n\n"
        md += "## 🤖 Comandos pro Claude\n\n"
        if intencao == "diario":
            md += ("_Diário privado — registro pessoal. NÃO arquivar fora do espaço privado "
                   "e NÃO usar como conteúdo._\n")
        elif intencao == "jogo":
            md += ("_Rodada do jogo de questões (MedCof) — transcrição crua do raciocínio/resposta. "
                   "O Claude corrige fora do personagem e só registra no caderno de erros se houve erro._\n")
        elif extra_instrucao or comandos:
            if extra_instrucao:
                md += f"**Ação deste modo:** {extra_instrucao}\n\n"
            if comandos:
                md += "".join(f"- [ ] {c}\n" for c in comandos)
            partes = []
            if comandos:
                partes.append("EXECUTAR cada comando acima e marcar `[x]`")
            if extra_instrucao:
                partes.append("realizar a AÇÃO do modo descrita acima")
            partes += [f"ARQUIVAR esta nota em `{categoria}`",
                       "SEMPRE adicionar conexões `[[ ]]` ao vault",
                       "marcar `status: processado`"]
            md += "\n> Ao processar o inbox, o Claude deve: " + "; ".join(partes) + ".\n"
        else:
            md += (f"_Sem comando explícito. O Claude deve ARQUIVAR esta nota em `{categoria}` "
                   f"e SEMPRE adicionar conexões `[[ ]]`._\n")
        md += f"\n## Conteúdo (transcrição corrigida pelo contexto)\n\n{texto_lap}\n"
        if conexoes:
            md += "\n## 🔗 Conexões\n\n" + "  ".join(f"[[{c}]]" for c in conexoes) + "\n"
        md += f"\n---\n\n<details><summary>Transcrição original</summary>\n\n{texto}\n\n</details>\n"
        return md

    # ─── Brainstorm → inbox ────────────────────────────────────────────────────

    def _build_brainstorm_md(self, texto, ia, lang, duracao):
        ts   = self.current_ts or datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        data = ts[:10]
        hora = ts[11:16].replace("-", ":")
        nomes = {"pt": "Português", "en": "English", "es": "Español", "de": "Deutsch"}
        lang_nome = nomes.get(lang, lang)

        resumo    = ia.get("resumo", "")
        texto_lap = ia.get("texto_lapidado", texto)
        tags      = ia.get("tags", [])
        tipo      = ia.get("tipo", "ideia")
        categoria = ia.get("categoria_sugerida", "inbox")
        problemas = ia.get("problemas", []) or []
        sugestoes = ia.get("sugestoes", []) or []
        tags_yaml = "[" + ", ".join(str(t) for t in tags) + "]"

        md = (
            f"---\n"
            f'titulo: "Brainstorm {data} {hora}"\n'
            f"data: {data}\n"
            f'hora: "{hora}"\n'
            f"idioma: {lang_nome}\n"
            f"duracao_segundos: {duracao:.0f}\n"
            f"tags: {tags_yaml}\n"
            f"tipo: brainstorm\n"
            f"subtipo: {tipo}\n"
            f"categoria_sugerida: {categoria}\n"
            f"status: aguardando_claude\n"
            f'arquivo_audio: "{os.path.basename(self.current_wav or "")}"\n'
            f"---\n\n"
            f"# Brainstorm — {data} às {hora}\n\n"
            f"> **Idioma:** {lang_nome}  |  **Tipo:** {tipo}  |  "
            f"**Categoria sugerida:** {categoria}\n\n"
            f"---\n\n## Resumo (Gemini)\n\n{resumo}\n\n"
            f"---\n\n## Texto lapidado\n\n{texto_lap}\n\n"
            f"---\n\n## Problemas / questões levantadas\n\n"
        )
        if problemas:
            md += "".join(f"- [ ] {p}\n" for p in problemas)
        else:
            md += "_Nenhum problema explícito identificado._\n"
        md += "\n---\n\n## Sugestões iniciais (Gemini)\n\n"
        if sugestoes:
            md += "".join(f"- {s}\n" for s in sugestoes)
        else:
            md += "_Sem sugestões automáticas._\n"
        md += (
            "\n---\n\n## Para o Claude resolver\n\n"
            "> Ao processar o inbox, o Claude deve: (1) resolver/encaminhar cada problema "
            "acima, (2) refinar as sugestões, (3) mover esta nota para a categoria sugerida "
            "e (4) marcar `status: processado`.\n"
        )
        return md

    def _save_inbox(self, md):
        ts   = self.current_ts or datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        os.makedirs(INBOX_DIR, exist_ok=True)
        path = os.path.join(INBOX_DIR, f"{ts}_brainstorm.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(md)
        self.root.after(0, lambda: self.file_lbl.configure(
            text=f"Inbox: {os.path.basename(path)}"))
        return path

    def _brainstorm_preview(self, ia):
        partes = []
        if ia.get("resumo"):
            partes.append(f"📌 Resumo: {ia['resumo']}")
        if ia.get("categoria_sugerida"):
            partes.append(f"📂 Categoria sugerida: {ia['categoria_sugerida']}")
        if ia.get("problemas"):
            partes.append("\n❓ Problemas levantados:\n"
                          + "\n".join(f"  • {p}" for p in ia["problemas"]))
        if ia.get("sugestoes"):
            partes.append("\n💡 Sugestões iniciais:\n"
                          + "\n".join(f"  • {s}" for s in ia["sugestoes"]))
        partes.append("\n→ Salvo no inbox com status 'aguardando_claude'.")
        return "\n".join(partes)

    # ─── Config ──────────────────────────────────────────────────────────────

    def _open_settings(self):
        win = tk.Toplevel(self.root)
        win.title("Configurações")
        win.geometry("540x400")
        win.configure(bg=BG)
        win.grab_set()

        tk.Label(win, text="⚙  Configurações", font=(FONT, 14, "bold"),
                 fg=TXT, bg=BG).pack(pady=(18, 12))

        fields = [
            ("Chave Gemini (GEMINI_API_KEY):",  "GEMINI_API_KEY",    True),
            ("Chave Anthropic (ANTHROPIC_API_KEY):", "ANTHROPIC_API_KEY", True),
            ("Chave OpenAI (OPENAI_API_KEY):",   "OPENAI_API_KEY",    True),
            ("Pasta Obsidian (destino .md):",    "pasta_obsidian",    False),
        ]
        vars_ = {}
        for label, key, secret in fields:
            row = tk.Frame(win, bg=BG)
            row.pack(fill="x", padx=20, pady=5)
            tk.Label(row, text=label, font=(FONT, 10), fg=TXT, bg=BG,
                     width=30, anchor="w").pack(side="left")
            val = os.environ.get(key, "") if secret else self.cfg.get(key, "")
            v = tk.StringVar(value=val)
            vars_[key] = (v, secret)
            tk.Entry(row, textvariable=v, font=(FONT, 10), bg=BG2, fg=TXT,
                     show="•" if secret else "", relief="flat", width=28,
                     highlightbackground=BORDER, highlightthickness=1).pack(
                         side="left", padx=6, ipady=4)

        ia_var = tk.BooleanVar(value=self.cfg.get("usar_ia_para_lapidacao", True))
        row = tk.Frame(win, bg=BG)
        row.pack(fill="x", padx=20, pady=5)
        tk.Label(row, text="Lapidar com IA automaticamente:", font=(FONT, 10),
                 fg=TXT, bg=BG, width=30, anchor="w").pack(side="left")
        tk.Checkbutton(row, variable=ia_var, bg=BG).pack(side="left")

        tk.Label(win, text="Chaves ficam salvas em .env — nunca em config.json.",
                 font=(FONT, 9), fg=TXT2, bg=BG).pack(pady=(10, 0))

        def salvar():
            for key, (var, is_secret) in vars_.items():
                val = var.get().strip()
                if is_secret:
                    if val:
                        save_env_key(key, val)
                else:
                    self.cfg[key] = val
                    os.makedirs(val, exist_ok=True) if val else None
            self.cfg["usar_ia_para_lapidacao"] = ia_var.get()
            self.ia_lapidar_var.set(ia_var.get())   # mantém o toggle da barra em sincronia
            save_config(self.cfg)
            self._refresh_providers()
            self._update_ia_badge()
            win.destroy()

        tk.Button(win, text="Salvar", font=(FONT, 11, "bold"),
                  bg=TR, fg="white", relief="flat", padx=20, pady=8,
                  cursor="hand2", command=salvar).pack(pady=14)

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _selected_modo(self):
        return MODOS_POR_LABEL.get(self.mode_var.get(), MODOS[0])

    def _show_modos_help(self):
        linhas = ["Cada modo segue o padrão:  falar → a IA transforma → vira ação/arquivo.\n"]
        for m in MODOS:
            destino = "→ inbox (Claude executa)" if m["inbox"] else "→ arquiva no vault"
            linhas.append(f"{m['label']}  {destino}\n   {m['desc']}\n")
        messagebox.showinfo("Usos do Sussurro", "\n".join(linhas))

    def _set_status(self, msg, color=TXT2):
        self.root.after(0, lambda: (
            self.status_var.set(msg),
            self.status_lbl.configure(fg=color)
        ))

    def _open_folder(self):
        pasta = self.cfg.get("pasta_obsidian") or WAV_DIR
        try:
            if sys.platform == "win32":
                os.startfile(pasta)               # Windows
            elif sys.platform == "darwin":
                subprocess.run(["open", pasta])    # macOS
            else:
                subprocess.run(["xdg-open", pasta])  # Linux
        except Exception as e:
            self._set_status(f"Não consegui abrir a pasta: {e}", AMBER)

    def clear(self):
        for t in [self.text_raw, self.text_ia, self.text_md]:
            t.delete("1.0", tk.END)
        self.file_lbl.configure(text="Nenhuma gravação ainda.")
        self.current_wav = None
        self.tr_btn.configure(state="disabled")
        self._set_status("Pronta para gravar.")


def _set_icon(root, path):
    try:
        if os.path.exists(path):
            root.iconbitmap(path)
    except Exception:
        pass


if __name__ == "__main__":
    root = tk.Tk()
    Sussurro(root)
    root.mainloop()
