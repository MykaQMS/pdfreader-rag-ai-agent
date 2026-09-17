"""
streamlit_app.py
Interface interativa em Streamlit para o projeto de estudo PDF RAG AI Agent.
Permite o upload de arquivos PDF, disparo assíncrono de eventos de ingestão e
consultas contextualizadas (RAG) utilizando Inngest, Qdrant e OpenAI.
"""

import asyncio
import os
from pathlib import Path
import time
import requests
import streamlit as st
import inngest
from dotenv import load_dotenv

load_dotenv()

# Configuração da página
st.set_page_config(
    page_title="PDF RAG AI Agent | Portfólio de Estudos",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Estilização visual customizada (design limpo, moderno e profissional)
st.markdown(
    """
    <style>
    /* Estilo geral e tipografia */
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        background: linear-gradient(120deg, #2563eb, #7c3aed);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        color: #64748b;
        font-size: 1.05rem;
        margin-bottom: 1.5rem;
    }
    .status-card {
        padding: 0.8rem 1rem;
        border-radius: 8px;
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        margin-bottom: 0.6rem;
        font-size: 0.88rem;
    }
    .metric-badge {
        display: inline-block;
        padding: 0.25rem 0.6rem;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 600;
        background-color: #e0f2fe;
        color: #0369a1;
        margin-right: 0.4rem;
    }
    .context-box {
        background-color: #f1f5f9;
        border-left: 4px solid #3b82f6;
        padding: 0.75rem 1rem;
        border-radius: 0 8px 8px 0;
        margin-bottom: 0.6rem;
        font-size: 0.9rem;
        color: #334155;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_inngest_client() -> inngest.Inngest:
    """Retorna uma instância única do cliente Inngest para o app Streamlit."""
    return inngest.Inngest(app_id="rag_app", is_production=False)


def _inngest_api_base() -> str:
    """Obtém a URL base da API do Inngest Dev Server a partir do .env ou usa o padrão local."""
    return os.getenv("INNGEST_API_BASE", "http://127.0.0.1:8288/v1")


def check_services_health() -> dict[str, bool]:
    """Verifica a conectividade com os 3 serviços fundamentais do ecossistema."""
    health = {}
    # 1. FastAPI Backend
    try:
        r = requests.get("http://127.0.0.1:8000/", timeout=1.5)
        health["FastAPI (Backend)"] = r.status_code == 200
    except Exception:
        health["FastAPI (Backend)"] = False

    # 2. Inngest Dev Server
    try:
        r = requests.get("http://127.0.0.1:8288/", timeout=1.5)
        health["Inngest (Workflows)"] = r.status_code == 200
    except Exception:
        health["Inngest (Workflows)"] = False

    # 3. Qdrant Vector Database
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    try:
        r = requests.get(f"{qdrant_url}/healthz", timeout=1.5)
        health["Qdrant (Vector DB)"] = r.status_code == 200
    except Exception:
        health["Qdrant (Vector DB)"] = False

    return health


def save_uploaded_pdf(file) -> Path:
    """Salva o arquivo PDF enviado na pasta local 'uploads'."""
    uploads_dir = Path("uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    file_path = uploads_dir / file.name
    file_bytes = file.getbuffer()
    file_path.write_bytes(file_bytes)
    return file_path


async def send_rag_ingest_event(pdf_path: Path) -> str:
    """Envia o evento 'rag/ingest_pdf' para o Inngest iniciar o pipeline de ingestão assíncrona."""
    client = get_inngest_client()
    result = await client.send(
        inngest.Event(
            name="rag/ingest_pdf",
            data={
                "pdf_path": str(pdf_path.resolve()),
                "source_id": pdf_path.name,
            },
        )
    )
    return result[0] if result else ""


async def send_rag_query_event(question: str, top_k: int) -> str:
    """Dispara o evento 'rag/query_pdf_ai' para o Inngest e retorna o ID do evento para rastreamento."""
    client = get_inngest_client()
    result = await client.send(
        inngest.Event(
            name="rag/query_pdf_ai",
            data={
                "question": question,
                "top_k": top_k,
            },
        )
    )
    return result[0]


def fetch_runs(event_id: str) -> list[dict]:
    """Consulta os detalhes e o estado de execução de um evento no Inngest Dev Server."""
    url = f"{_inngest_api_base()}/events/{event_id}/runs"
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])
    except requests.exceptions.RequestException:
        return []


def wait_for_run_output(
    event_id: str, timeout_s: float = 120.0, poll_interval_s: float = 0.5
) -> dict:
    """
    Executa polling na API do Inngest até que o workflow seja concluído e retorne os resultados.
    """
    start = time.time()
    last_status = None
    while True:
        runs = fetch_runs(event_id)
        if runs:
            run = runs[0]
            status = run.get("status")
            last_status = status or last_status
            if status in ("Completed", "Succeeded", "Success", "Finished"):
                return run.get("output") or {}
            if status in ("Failed", "Cancelled"):
                raise RuntimeError(f"Workflow finalizado com status: {status}")
        if time.time() - start > timeout_s:
            raise TimeoutError(
                f"Tempo limite excedido aguardando execução (Último status: {last_status})"
            )
        time.sleep(poll_interval_s)


# ==============================================================================
# BARRA LATERAL (SIDEBAR): Status da Arquitetura e Controles
# ==============================================================================
with st.sidebar:
    st.markdown("### 🤖 Sobre o Projeto")
    st.markdown(
        """
        Este é um **projeto prático de estudos** construído para demonstrar
        uma arquitetura **RAG Orientada a Eventos** (*Event-Driven*) com execuções
        duráveis, desacoplando tarefas pesadas de ingestão da interface do usuário.
        """
    )

    st.markdown("---")
    st.markdown("#### 📡 Status dos Serviços")
    health = check_services_health()
    for service, is_ok in health.items():
        if is_ok:
            st.markdown(f"🟢 **{service}**: `Online`")
        else:
            st.markdown(f"🔴 **{service}**: `Desconectado`")

    st.markdown("---")
    st.markdown("#### ⚙️ Parâmetros de Recuperação")
    top_k = st.slider(
        "Quantidade de chunks a recuperar (Top-K)",
        min_value=1,
        max_value=10,
        value=5,
        help="Controla quantos fragmentos de texto do Qdrant serão inseridos no prompt do LLM.",
    )

    st.markdown("---")
    st.markdown("#### 🛠️ Links Úteis")
    st.markdown("- [Painel do Inngest Dev Server](http://127.0.0.1:8288)")
    st.markdown("- [Documentação da API (FastAPI)](http://127.0.0.1:8000/docs)")


# ==============================================================================
# CORPO PRINCIPAL DA APLICAÇÃO
# ==============================================================================
st.markdown('<div class="main-header">PDF RAG AI Agent</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-header">'
    "Arquitetura de Recuperação Aumentada por Geração (RAG) com Workflows Duráveis "
    "(FastAPI · Inngest · Qdrant · LlamaIndex · OpenAI)"
    "</div>",
    unsafe_allow_html=True,
)

# Inicializa o estado de sessão para arquivos ingeridos
if "ingested_files" not in st.session_state:
    st.session_state.ingested_files = set()

# Divisão em duas colunas funcionais
col_left, col_right = st.columns([1.1, 1.4], gap="large")

# ------------------------------------------------------------------------------
# COLUNA ESQUERDA: Ingestão de Documentos (PDF)
# ------------------------------------------------------------------------------
with col_left:
    st.markdown("### 📄 1. Ingestão de Documento")
    st.write("Envie um PDF para extração de texto, chunking e indexação vetorial no Qdrant.")

    uploaded = st.file_uploader("Selecione um arquivo PDF", type=["pdf"], accept_multiple_files=False)

    if uploaded is not None:
        file_size_kb = uploaded.size / 1024
        st.info(f"**Arquivo selecionado:** `{uploaded.name}` ({file_size_kb:.1f} KB)")

        # Botão explícito para ingestão (evita loop involuntário a cada rerun do Streamlit)
        if st.button("🚀 Processar e Indexar Documento", type="primary", use_container_width=True):
            with st.spinner("Gravando arquivo e despachando workflow para o Inngest..."):
                saved_path = save_uploaded_pdf(uploaded)
                event_id = asyncio.run(send_rag_ingest_event(saved_path))
                st.session_state.ingested_files.add(uploaded.name)

            st.success(f"Evento de ingestão disparado com sucesso para: `{saved_path.name}`")
            st.caption(
                f"ID do evento: `{event_id}`. Acompanhe os steps em tempo real no "
                "[Inngest Dashboard](http://127.0.0.1:8288)."
            )

    if st.session_state.ingested_files:
        st.markdown("##### Documentos indexados nesta sessão:")
        for doc in st.session_state.ingested_files:
            st.markdown(f"- 📑 `{doc}`")

# ------------------------------------------------------------------------------
# COLUNA DIREITA: Perguntas e Respostas (RAG Query)
# ------------------------------------------------------------------------------
with col_right:
    st.markdown("### 💬 2. Consulta Semântica")
    st.write("Faça perguntas sobre os documentos indexados. A resposta será fundamentada nos trechos recuperados.")

    with st.form("rag_query_form"):
        question = st.text_input(
            "Digite sua pergunta sobre o documento:",
            placeholder="Ex: Quais são os principais tópicos abordados neste arquivo?",
        )
        submitted = st.form_submit_button("Perguntar ao Agente", type="primary", use_container_width=True)

    if submitted:
        if not question.strip():
            st.warning("Por favor, digite uma pergunta antes de enviar.")
        else:
            with st.spinner("Executando busca vetorial e gerando resposta com o LLM..."):
                try:
                    # Envia o evento de consulta para a fila do Inngest
                    event_id = asyncio.run(send_rag_query_event(question.strip(), int(top_k)))
                    # Aguarda a conclusão dos steps duráveis no backend
                    output = wait_for_run_output(event_id)

                    answer = output.get("answer", "")
                    sources = output.get("sources", [])
                    num_contexts = output.get("num_contexts", 0)
                    contexts = output.get("contexts", [])

                    # Exibição organizada do resultado
                    st.markdown("#### 💡 Resposta:")
                    st.markdown(answer or "*(Nenhuma resposta gerada pelo modelo)*")

                    # Exibição das fontes e metadados
                    st.markdown("---")
                    col_meta1, col_meta2 = st.columns(2)
                    with col_meta1:
                        st.markdown(f"**Chunks consultados:** `{num_contexts}`")
                    with col_meta2:
                        if sources:
                            st.markdown(f"**Fonte(s):** `{', '.join(sources)}`")
                        else:
                            st.markdown("**Fonte:** `Nenhuma`")

                    # Expansor para visualização dos fragmentos reais recuperados (ótimo para portfólio)
                    if contexts:
                        with st.expander(f"🔍 Inspecionar os {len(contexts)} fragmentos recuperados no Qdrant"):
                            for idx, c_text in enumerate(contexts, 1):
                                st.markdown(f"**Fragmento #{idx}:**")
                                st.markdown(f'<div class="context-box">{c_text}</div>', unsafe_allow_html=True)

                except requests.exceptions.ConnectionError:
                    st.error(
                        "Erro de conexão: Não foi possível comunicar com o Inngest Dev Server. "
                        "Certifique-se de que o comando `npx inngest-cli dev` está ativo."
                    )
                except Exception as e:
                    st.error(f"Ocorreu um erro ao processar a consulta: {e}")
