"""
AI Provider — MaestroVault
Provedor unificado com CASCATA DE FALLBACK:
  DeepSeek (padrão, mais barato) → Gemini (rápido) → Anthropic → OpenAI.
Detecta automaticamente quais chaves estão configuradas e, se o provedor da vez
falhar (erro de API ou resposta fora de JSON), cai pro próximo da cadeia.
Só "morre" (retorna {'erro'}) quando TODOS falham.
"""

import os
import json
import re
from dotenv import load_dotenv

# Fonte de verdade das chaves: arquivos centrais em ~/.config/fernanda/.
# Carregamos aqui (não só via ~/.profile) para que QUALQUER entrada — a GUI do
# Sussurro, o auto-processador do inbox, scripts ad-hoc — enxergue as MESMAS
# chaves. override=True faz um edit no arquivo valer na hora. A ordem importa:
# o último carregado vence; secrets.env (canônico) fica por último.
_HOME = os.path.expanduser("~")
for _p in (
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),  # local (se existir)
    os.path.join(_HOME, ".config", "fernanda", ".env"),
    os.path.join(_HOME, ".config", "fernanda", "secrets.env"),
):
    if os.path.exists(_p):
        load_dotenv(dotenv_path=_p, override=True)

MODELOS_PADRAO = {
    "deepseek":  "deepseek-chat",
    "gemini":    "gemini-2.5-flash",
    "anthropic": "claude-haiku-4-5-20251001",
    "openai":    "gpt-4o-mini",
}

NOMES_AMIGAVEIS = {
    "deepseek":  "DeepSeek V3",
    "gemini":    "Gemini 2.5 Flash",
    "anthropic": "Claude Haiku",
    "openai":    "GPT-4o Mini",
}

ICONS_PROVEDOR = {
    "deepseek":  "◇",
    "gemini":    "✦",
    "anthropic": "◈",
    "openai":    "◎",
}

# Ordem da cascata de fallback (mais barato → mais caro). O provedor escolhido em
# AI_PROVIDER vai pra frente da fila; os demais entram como rede de segurança.
ORDEM_FALLBACK = ["deepseek", "gemini", "anthropic", "openai"]

# Teto de saída. A nota de voz preserva a transcrição INTEIRA corrigida, então
# precisa de folga (um despejo de 10 min vira bastante texto + JSON).
MAX_TOKENS = 8000


def provedor_ativo() -> str | None:
    """Retorna o provedor configurado em AI_PROVIDER (ou o primeiro disponível)."""
    preferido = os.environ.get("AI_PROVIDER", "deepseek").lower()
    if _tem_chave(preferido):
        return preferido
    for p in ORDEM_FALLBACK:
        if _tem_chave(p):
            return p
    return None


def cadeia_provedores() -> list[str]:
    """Ordem de tentativa COM FALLBACK: o AI_PROVIDER na frente, o resto atrás."""
    preferido = os.environ.get("AI_PROVIDER", "deepseek").lower()
    ordem = [preferido] + [p for p in ORDEM_FALLBACK if p != preferido]
    return [p for p in ordem if _tem_chave(p)]


def provedores_disponiveis() -> list[str]:
    return [p for p in ORDEM_FALLBACK if _tem_chave(p)]


def label_provedor(p: str) -> str:
    icon = ICONS_PROVEDOR.get(p, "◆")
    nome = NOMES_AMIGAVEIS.get(p, p)
    return f"{icon} {nome}"


def _tem_chave(provedor: str) -> bool:
    chaves = {
        "deepseek":  "DEEPSEEK_API_KEY",
        "gemini":    "GEMINI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "openai":    "OPENAI_API_KEY",
    }
    k = chaves.get(provedor, "")
    return bool(os.environ.get(k, "").strip())


# ── Cascata de despacho ───────────────────────────────────────────────────────

def _despachar(prompt: str, provedor: str) -> dict:
    """Manda o prompt p/ UM provedor e devolve o dict (JSON parseado ou _fallback)."""
    if provedor == "deepseek":
        return _deepseek(prompt)
    if provedor == "gemini":
        return _gemini(prompt)
    if provedor == "anthropic":
        return _anthropic(prompt)
    if provedor == "openai":
        return _openai(prompt)
    raise ValueError(f"Provedor desconhecido: {provedor}")


def _em_cascata(prompt: str, provedor: str | None = None,
                incluir_claude_cli: bool = False) -> dict:
    """
    Núcleo do fallback. `provedor`, se vier, é só o LÍDER da fila — a cascata
    continua nos demais se ele falhar (resiliência mesmo com seleção explícita
    na GUI). Devolve o 1º JSON VÁLIDO; em erro de API ou resposta fora de JSON,
    tenta o próximo. `incluir_claude_cli`: usa o `claude -p` (login Pro/Max, SEM
    API key nem custo por token) como ÚLTIMO recurso, após todo o resto falhar.
    """
    if provedor:
        cadeia = [provedor] + [p for p in cadeia_provedores() if p != provedor]
    else:
        cadeia = cadeia_provedores()
    if not cadeia and not incluir_claude_cli:
        return {"erro": "Nenhuma chave de API configurada no .env"}

    ult_erro = None
    fallback_guardado = None
    for p in cadeia:
        try:
            r = _despachar(prompt, p)
        except Exception as e:
            ult_erro = f"[{p}] {e}"
            continue
        if isinstance(r, dict) and r.get("erro"):
            ult_erro = r["erro"]
            continue
        if isinstance(r, dict) and r.pop("_fallback", False):
            ult_erro = f"[{p}] resposta não veio em JSON"
            fallback_guardado = fallback_guardado or r
            continue
        if isinstance(r, dict):
            r["_provedor"] = p  # rastro: quem de fato respondeu
        return r

    # Último recurso: Claude via CLI (assinatura Pro/Max, sem chave de API).
    if incluir_claude_cli:
        try:
            r = _claude_cli(prompt)
            if not (isinstance(r, dict) and r.pop("_fallback", False)):
                if isinstance(r, dict):
                    r["_provedor"] = "claude-cli"
                return r
            fallback_guardado = fallback_guardado or r
        except Exception as e:
            ult_erro = f"[claude-cli] {e}"

    if fallback_guardado is not None:
        return fallback_guardado
    return {"erro": ult_erro or "todos os provedores falharam"}


# ── API pública ───────────────────────────────────────────────────────────────

def polir_transcricao(texto_bruto: str, idioma_code: str = "pt",
                      provedor: str | None = None) -> dict:
    """
    Lapida uma transcrição e retorna dict:
      texto_lapidado, tags, resumo, tipo  (ou erro)
    """
    return _em_cascata(_build_prompt(texto_bruto, idioma_code), provedor,
                       incluir_claude_cli=True)


def processar_brainstorm(texto_bruto: str, idioma_code: str = "pt",
                         provedor: str | None = None) -> dict:
    """
    Processa uma nota falada de brainstorm e devolve material "mastigado"
    para o Claude agir depois. Retorna dict:
      texto_lapidado, resumo, tags, tipo, categoria_sugerida,
      problemas (list), sugestoes (list)  (ou erro)
    """
    return _em_cascata(_build_brainstorm_prompt(texto_bruto, idioma_code), provedor,
                       incluir_claude_cli=True)


def processar_voz(texto_bruto: str, idioma_code: str = "pt",
                  provedor: str | None = None) -> dict:
    """
    Processa QUALQUER nota falada (fluxo unificado do Sussurro).
    NÃO resume: preserva a transcrição inteira CORRIGIDA pelo contexto (conserta
    palavras ouvidas errado), destaca em **negrito** os verbos de comando à IA,
    extrai tags/conexões e detecta COMANDOS dirigidos ao Claude.

    Retorna dict:
      texto_lapidado (transcrição corrigida, não resumo), resumo (1 frase),
      tags, tipo, categoria_sugerida, comandos (list), tem_comando (bool),
      conexoes (list)  (ou erro)
    """
    result = _em_cascata(_build_voz_prompt(texto_bruto, idioma_code), provedor,
                         incluir_claude_cli=True)

    # Normaliza conexões: remove colchetes [[ ]] se a IA já os tiver incluído
    # (o Markdown da nota é quem embrulha em [[ ]], senão viraria [[[[x]]]]).
    if isinstance(result, dict) and result.get("conexoes"):
        result["conexoes"] = [
            str(c).strip().strip("[]").strip()
            for c in result["conexoes"] if str(c).strip().strip("[]").strip()
        ]
    return result


def planejar_inbox_kepano(nota_md: str, titulos_existentes=None,
                          paginas_livro=None, idioma_code: str = "pt",
                          provedor: str | None = None) -> dict:
    """
    Pede à IA um PLANO de arquivamento kepano para uma nota do inbox: que notas
    atômicas criar, com frontmatter pronto e [[links]].
    O script `processar_inbox.py` é quem executa esse plano no filesystem.

    Retorna dict:
      {
        "escalar_claude": bool,   # True = a IA se declara insegura → Claude assume
        "motivo": str,
        "inbox_status": "processado" | "revisar",
        "log": str,               # 1 linha-resumo do que decidiu
        "notas": [ {"tipo","pasta","titulo","markdown"} , ... ]
      }
    ou {"erro": ...}
    """
    prompt = _build_inbox_kepano_prompt(
        nota_md, titulos_existentes or [], paginas_livro or [], idioma_code)
    return _em_cascata(prompt, provedor)


def _build_inbox_kepano_prompt(nota_md, titulos, paginas_livro, idioma_code):
    nomes = {"pt": "Português", "en": "English", "es": "Español", "de": "Deutsch"}
    lang = nomes.get(idioma_code, idioma_code)
    titulos_txt = "\n".join(f"- {t}" for t in titulos[:200]) or "(nenhuma ainda)"
    livros_txt = "\n".join(f"- {p}" for p in paginas_livro) or "(nenhum livro ainda)"
    return f"""Você é o ORGANIZADOR de um cofre Obsidian estilo kepano (em {lang}).
Recebeu UMA nota capturada por voz (já lapidada) que está no Inbox. Sua tarefa é
planejar como arquivá-la no cofre: quebrar em notas ATÔMICAS (1 ideia por nota) e
escrever cada uma já no formato certo, com [[links]] de verdade.

NOTA DO INBOX (frontmatter + transcrição):
---INICIO---
{nota_md}
---FIM---

TIPOS kepano (use o `tipo`, a `pasta` e a categoria certos):
- evergreen  → pasta "Notes"        · categories: [[Evergreen]]   · ideia atômica/ensaio
- paper      → pasta "Notes"        · categories: [[Papers]]      · ficha de artigo (PICO/viés/GRADE)
- condition  → pasta "Notes"        · categories: [[Conditions]]  · condição clínica (ANONIMIZAR)
- post       → pasta "Notes"        · categories: [[Posts]]       · ideia/roteiro do canal
- cena       → pasta "<PASTA_DO_LIVRO>" · categories: [[Cenas]]        · book/capitulo/ordem/pov/local/status
- personagem → pasta "<PASTA_DO_LIVRO>" · categories: [[Personagens]]  · book/papel/arco
- cenario    → pasta "<PASTA_DO_LIVRO>" · categories: [[Cenários]]     · book/tipo
- acontecimento → pasta "<PASTA_DO_LIVRO>" · categories: [[Acontecimentos]] · book/quando
- contexto   → pasta "<PASTA_DO_LIVRO>" · categories: [[Contextos]]    · book/tema
- capitulo   → pasta "<PASTA_DO_LIVRO>" · categories: [[Capítulos]]    · book/numero

LIVROS existentes (página-mãe → pasta) para os tipos de ficção:
{livros_txt}

NOTAS já existentes (linke para estas quando fizer sentido; link p/ nota inexistente
também é OK, é migalha kepano):
{titulos_txt}

REGRAS:
1. Quebre despejos amplos (mundo+política+vários personagens) em VÁRIAS notas atômicas.
2. Cada nota: frontmatter YAML com `categories` do tipo + `created` + `tags` (plural, minúsculas, com hífen) + campos do tipo; corpo limpo; conexões [[ ]].
3. Ficção: SEMPRE inclua `book: "[[<página-mãe do livro>]]"` no frontmatter e use a PASTA do livro.
4. Caso clínico: remova TODO dado identificável (LGPD).
5. Se a intenção for ops (financa/agenda/email/reuniao): NÃO crie nota de conhecimento; devolva notas:[] e escalar_claude:false, e em `log` descreva a ação como "TODO (interativo)".
6. Se você ficar INSEGURA (classificação dúbia, conflito com nota existente, tarefa criativa pesada como roteiro): ponha escalar_claude:true, notas:[] e explique em `motivo` — o Claude assume.
7. `titulo` = nome do arquivo (sem extensão, sem caracteres / \\ : * ? " < > |).

Responda SOMENTE em JSON (nada fora do JSON):
{{
  "escalar_claude": false,
  "motivo": "",
  "inbox_status": "processado",
  "log": "resumo de 1 linha do que foi feito",
  "notas": [
    {{"tipo": "evergreen", "pasta": "Notes", "titulo": "Título da nota",
      "markdown": "---\\ncategories:\\n  - \\"[[Evergreen]]\\"\\ncreated: 2026-06-10\\ntags:\\n  - exemplo\\n---\\n\\nCorpo da nota com [[links]].\\n"}}
  ]
}}"""


def resposta_livre(mensagem: str, provedor: str | None = None,
                   system: str = "") -> str:
    """Texto simples com cascata: provedor (líder) → resto → Claude CLI (Pro/Max)."""
    if provedor:
        cadeia = [provedor] + [p for p in cadeia_provedores() if p != provedor]
    else:
        cadeia = cadeia_provedores()
    ult_erro = None
    for p in cadeia:
        try:
            if p == "deepseek":
                return _deepseek_livre(mensagem, system)
            if p == "gemini":
                return _gemini_livre(mensagem, system)
            if p == "anthropic":
                return _anthropic_livre(mensagem, system)
            if p == "openai":
                return _openai_livre(mensagem, system)
        except Exception as e:
            ult_erro = f"Erro: {e}"
            continue
    # Último recurso: Claude via CLI (assinatura, sem API key).
    try:
        return _claude_cli_livre(mensagem, system)
    except Exception as e:
        return ult_erro or f"Erro: {e}"


# ── Builders de prompt ────────────────────────────────────────────────────────

def _build_prompt(texto, idioma_code):
    nomes = {"pt": "Português", "en": "English", "es": "Español", "de": "Deutsch"}
    lang = nomes.get(idioma_code, idioma_code)
    return f"""Você recebeu uma transcrição bruta de áudio em {lang}.

TRANSCRIÇÃO:
{texto}

Tarefas:
1. Corrija erros de transcrição e remova preenchimentos ("ééé", "hmmm", repetições).
2. Mantenha o estilo e a voz originais — apenas limpe, não reescreva.
3. Extraia 3 a 6 tags dos tópicos principais.
4. Escreva um resumo de 1-2 frases.
5. Classifique o tipo: roteiro | anotacao | ideia | reuniao | outro

Responda SOMENTE em JSON (sem texto fora do JSON):
{{
  "texto_lapidado": "...",
  "tags": ["tag1", "tag2"],
  "resumo": "...",
  "tipo": "..."
}}"""


def _build_brainstorm_prompt(texto, idioma_code):
    nomes = {"pt": "Português", "en": "English", "es": "Español", "de": "Deutsch"}
    lang = nomes.get(idioma_code, idioma_code)
    return f"""Você recebeu uma anotação falada (brainstorm), transcrita de áudio em {lang}.
Ela pode misturar ideias soltas, problemas, dúvidas e tarefas.

TRANSCRIÇÃO:
{texto}

Seu trabalho é "mastigar" essa nota para que um assistente (Claude) possa agir depois.
NÃO invente nada que não esteja na nota. Não responda os problemas em profundidade —
apenas organize, classifique e dê encaminhamentos iniciais curtos.

Tarefas:
1. texto_lapidado: limpe preenchimentos ("ééé", repetições) e organize em parágrafos/bullets, sem mudar o sentido.
2. resumo: 1 a 3 frases sobre o que é a nota.
3. tags: 3 a 6 tópicos principais.
4. tipo: um de [ideia, problema, tarefa, reflexao, pesquisa, conteudo, misto].
5. categoria_sugerida: onde isso se encaixa no vault. Escolha UMA string EXATA:
   "04_PROJECTS/marca-pessoal", "04_PROJECTS/metascouts", "04_PROJECTS/deep-sync",
   "04_PROJECTS/medai-notes", "08_CONTEXTS", "07_SKILLS", "02_WORKFLOWS",
   "10_FINANCE", "05_LOGS", "inbox" (use "inbox" se estiver incerto).
6. problemas: liste cada problema, dúvida ou pergunta que a pessoa levantou, como itens
   curtos e acionáveis. Se não houver, use lista vazia [].
7. sugestoes: uma sugestão inicial curta de solução/encaminhamento para cada problema
   (ou no geral). Se não houver, use [].

Responda SOMENTE em JSON (sem texto fora do JSON):
{{
  "texto_lapidado": "...",
  "resumo": "...",
  "tags": ["..."],
  "tipo": "...",
  "categoria_sugerida": "...",
  "problemas": ["..."],
  "sugestoes": ["..."]
}}"""


def _build_voz_prompt(texto, idioma_code):
    nomes = {"pt": "Português", "en": "English", "es": "Español", "de": "Deutsch"}
    lang = nomes.get(idioma_code, idioma_code)
    return f"""Você recebeu uma nota falada da Fernanda, transcrita de áudio em {lang}.
Ela usa o gravador "Sussurro" para despejar QUALQUER COISA: resumo do dia,
ideias de conteúdo, pauta de podcast, rascunho de newsletter, liturgia/reflexões
cristãs, perguntas a resolver, lembretes, ou pedidos diretos ao assistente (Claude).

TRANSCRIÇÃO BRUTA (pode conter palavras que o transcritor OUVIU ERRADO):
{texto}

PRINCÍPIO CENTRAL — NÃO RESUMA e NÃO CORTE conteúdo. Preserve a transcrição
INTEIRA, com TODOS os assuntos, na mesma ordem e com a voz dela. Seu trabalho é
entregar a MESMA fala, porém CORRIGIDA pelo CONTEXTO: conserte palavras ouvidas
errado (termos técnicos, nomes próprios, siglas) deduzindo o termo certo pelo
assunto. Exemplos de correção contextual:
  "Cloud Code" / "cloud coding" / "código de hoje"  → "Claude Code"
  "metanárias" / "metadeira" / "meta-nares"          → "metanálise"
  "FAPSP"                                              → "FAPESP"
  "vibe-colding"                                       → "vibe coding"
  "Metas Cotes" / "Metas Cotes"                        → "MetaScouts"
Use SEMPRE o assunto para inferir a grafia certa. Remova só ruído de fala
("ééé", "hmmm", gaguejo, repetição involuntária) — sem perder nenhum tópico.

NÃO invente nada que não esteja na nota.

Tarefas:
1. texto_lapidado: a transcrição COMPLETA e corrigida pelo contexto (ISTO NÃO É
   UM RESUMO — é o texto inteiro arrumado). Organize em parágrafos legíveis.
   DESTAQUE em **negrito** todo VERBO/FRASE DE COMANDO que ela dirige ao
   assistente (ex.: "**cria** um roteiro sobre X", "**me lembra** de Y",
   "**pesquisa** Z", "**resolve** isso", "**agenda**..."). Só marque comandos
   dirigidos à IA — não destaque verbos comuns do relato dela.
2. resumo: 1 frase curta (serve só de subtítulo/metadado).
3. tags: 3 a 8 tópicos REAIS presentes no texto (minúsculas, sem #).
4. tipo: UM de [resumo_dia, ideia_conteudo, pauta_podcast, newsletter,
   liturgia, reflexao, pergunta, tarefa, anotacao, misto].
5. categoria_sugerida: onde arquivar. Escolha UMA string EXATA:
   "04_PROJECTS/marca-pessoal", "04_PROJECTS/metascouts", "04_PROJECTS/deep-sync",
   "04_PROJECTS/medai-notes", "04_PROJECTS/desenvolvimento-pessoal",
   "04_PROJECTS/doutorado", "08_CONTEXTS", "07_SKILLS", "02_WORKFLOWS",
   "10_FINANCE", "05_LOGS", "inbox" (use "inbox" se incerto).
6. comandos: liste cada PEDIDO ACIONÁVEL dirigido ao Claude, como instruções
   curtas e imperativas (ex.: "Criar 3 ideias de Reels sobre metanálise").
   Se a nota for só registro/desabafo/reflexão SEM pedido, devolva [].
7. tem_comando: true se "comandos" tiver pelo menos 1 item; senão false.
8. conexoes: 3 a 8 NOTAS/TÓPICOS do vault com que esta nota se relaciona.
   Devolva só o tópico em texto puro, SEM os colchetes [[ ]] (o sistema embrulha).
   SEMPRE preencha (nunca devolva lista vazia).

Responda SOMENTE em JSON (sem texto fora do JSON):
{{
  "texto_lapidado": "...",
  "resumo": "...",
  "tags": ["..."],
  "tipo": "...",
  "categoria_sugerida": "...",
  "comandos": ["..."],
  "tem_comando": false,
  "conexoes": ["..."]
}}"""


def _extrair_json(raw: str) -> dict | None:
    m = re.search(r'\{[\s\S]+\}', raw)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass
    return None


def _fallback(raw: str) -> dict:
    # _fallback=True sinaliza p/ a cascata "não veio JSON" → tenta o próximo provedor.
    return {"texto_lapidado": raw, "tags": [], "resumo": "", "tipo": "outro",
            "_fallback": True}


# Claude via CLI — ÚLTIMO recurso da cascata (login Claude Code Pro/Max, SEM
# chave de API e SEM custo por token; só roda quando todo o resto falha).
def _claude_bin() -> str:
    import shutil
    b = os.path.expanduser("~/.local/bin/claude")
    return b if os.path.exists(b) else (shutil.which("claude") or "claude")


def _claude_cli(prompt: str) -> dict:
    import subprocess
    full = prompt + ("\n\nResponda APENAS com o JSON pedido — sem cercas de "
                     "código (```), sem texto antes ou depois.")
    r = subprocess.run([_claude_bin(), "-p", full],
                       capture_output=True, text=True, timeout=240)
    if r.returncode != 0:
        raise RuntimeError(f"claude -p saiu {r.returncode}: {(r.stderr or '').strip()[:200]}")
    raw = (r.stdout or "").strip()
    return _extrair_json(raw) or _fallback(raw)


def _claude_cli_livre(msg: str, system: str) -> str:
    import subprocess
    full = f"{system}\n\n{msg}" if system else msg
    r = subprocess.run([_claude_bin(), "-p", full],
                       capture_output=True, text=True, timeout=240)
    if r.returncode != 0:
        raise RuntimeError(f"claude -p saiu {r.returncode}: {(r.stderr or '').strip()[:200]}")
    return (r.stdout or "").strip()


# ── Implementações por provedor ───────────────────────────────────────────────

# DeepSeek (API compatível com OpenAI: base_url própria)
def _deepseek(prompt: str) -> dict:
    from openai import OpenAI
    client = OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    )
    r = client.chat.completions.create(
        model=MODELOS_PADRAO["deepseek"],
        messages=[{"role": "user", "content": prompt}],
        max_tokens=MAX_TOKENS,
        response_format={"type": "json_object"},  # exige a palavra "json" no prompt (tem)
    )
    raw = r.choices[0].message.content
    return _extrair_json(raw) or _fallback(raw)


def _deepseek_livre(msg: str, system: str) -> str:
    from openai import OpenAI
    client = OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    )
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": msg})
    return client.chat.completions.create(
        model=MODELOS_PADRAO["deepseek"], messages=msgs, max_tokens=MAX_TOKENS
    ).choices[0].message.content


# Gemini
def _gemini(prompt: str) -> dict:
    import google.generativeai as genai
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel(MODELOS_PADRAO["gemini"])
    resp = model.generate_content(prompt)
    return _extrair_json(resp.text) or _fallback(resp.text)


def _gemini_livre(msg: str, system: str) -> str:
    import google.generativeai as genai
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    full = f"{system}\n\n{msg}" if system else msg
    model = genai.GenerativeModel(MODELOS_PADRAO["gemini"])
    return model.generate_content(full).text


# Anthropic
def _anthropic(prompt: str) -> dict:
    import anthropic
    client = anthropic.Anthropic(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        base_url=os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
    )
    msg = client.messages.create(
        model=MODELOS_PADRAO["anthropic"],
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    return _extrair_json(msg.content[0].text) or _fallback(msg.content[0].text)


def _anthropic_livre(msg: str, system: str) -> str:
    import anthropic
    client = anthropic.Anthropic(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        base_url=os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
    )
    kwargs = {"model": MODELOS_PADRAO["anthropic"], "max_tokens": MAX_TOKENS,
              "messages": [{"role": "user", "content": msg}]}
    if system:
        kwargs["system"] = system
    return client.messages.create(**kwargs).content[0].text


# OpenAI
def _openai(prompt: str) -> dict:
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    r = client.chat.completions.create(
        model=MODELOS_PADRAO["openai"],
        messages=[{"role": "user", "content": prompt}],
        max_tokens=MAX_TOKENS,
    )
    raw = r.choices[0].message.content
    return _extrair_json(raw) or _fallback(raw)


def _openai_livre(msg: str, system: str) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": msg})
    return client.chat.completions.create(
        model=MODELOS_PADRAO["openai"], messages=msgs, max_tokens=MAX_TOKENS
    ).choices[0].message.content
