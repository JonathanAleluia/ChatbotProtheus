import streamlit as st
from sqlalchemy import create_engine, text
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
import datetime

# Importa seu "Manual de Regras"
from regras_protheus import REGRAS_NEGOCIO

# --- 1. CONFIGURAÇÕES (PREENCHA AQUI) ---

GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]

DB_HOST = st.secrets["DB_HOST"]
DB_NAME = st.secrets["DB_NAME"]
DB_USER = st.secrets["DB_USER"]
DB_PASS = st.secrets["DB_PASS"]

# Monta a string de conexão (SQL Server / pyodbc)
# Garanta que você tenha o 'ODBC Driver 17 for SQL Server' (ou mais novo) instalado
try:
    CONNECTION_STRING = (
        f"mssql+pyodbc://{DB_USER}:{DB_PASS}@{DB_HOST}/"
        f"{DB_NAME}?driver=ODBC+Driver+17+for+SQL+Server"
    )
except Exception as e:
    st.error(f"Erro ao montar a string de conexão: {e}")
    st.stop()


# --- 2. INICIALIZAÇÃO ---

# Configura a página do Streamlit
st.set_page_config(page_title="Chatbot Protheus", layout="centered")
st.title("🤖 Chatbot Protheus (PoC)")

# Inicializa o LLM (Gemini)
try:    
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=GOOGLE_API_KEY)
except Exception as e:
    st.error(f"Erro ao inicializar o LLM. Verifique sua API Key. Erro: {e}")
    st.stop()

# Inicializa a conexão com o banco de dados
try:
    db_engine = create_engine(CONNECTION_STRING)
except Exception as e:
    st.error(f"Erro ao conectar ao banco. Verifique os dados de conexão e o driver ODBC. Erro: {e}")
    st.stop()

# Template do Prompt (O "Molde" da pergunta)
prompt_template = PromptTemplate(
    input_variables=["regras", "data_hoje", "pergunta", "historico"],
    template="""{regras}
    
    Data de Hoje: {data_hoje}
    Histórico da Conversa (para contexto):
    {historico}
    
    Pergunta do Usuário: {pergunta}
    
    Gere APENAS o código SQL para esta pergunta:
    """
)

# Cria a "Cadeia" (Chain) do LangChain
sql_chain = prompt_template | llm 

# --- 3. LÓGICA DO CHAT ---

# Inicializa o histórico do chat no Streamlit
if "messages" not in st.session_state:
    st.session_state.messages = []

# Exibe as mensagens do histórico
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Captura a pergunta do usuário
if prompt_usuario := st.chat_input("Pergunte algo sobre vendas ou estoque..."):
    # Adiciona a pergunta ao histórico e exibe
    st.session_state.messages.append({"role": "user", "content": prompt_usuario})
    with st.chat_message("user"):
        st.markdown(prompt_usuario)

    # --- 🔹 NOVO TRATAMENTO: Mensagens simples (saudações, etc.)
    saudacoes = ["oi", "olá", "ola", "bom dia", "boa tarde", "boa noite", "e aí", "tudo bem"]
    if prompt_usuario.lower().strip() in saudacoes:
        resposta = "Olá! 😊 Como posso te ajudar com informações sobre vendas ou estoque?"
        with st.chat_message("assistant"):
            st.markdown(resposta)
        st.session_state.messages.append({"role": "assistant", "content": resposta})
        st.stop()

    # --- Se não for saudação, segue o fluxo normal ---
    with st.chat_message("assistant"):
        with st.spinner("Analisando seu banco..."):
            try:
                # 1. PREPARAR O PROMPT
                data_hoje = datetime.date.today().strftime("%Y-%m-%d")
                historico_formatado = "\n".join(
                    [f"{m['role']}: {m['content']}" for m in st.session_state.messages[-4:]]
                )
                
                # Monta o dicionário de input
                input_data = {
                    "regras": REGRAS_NEGOCIO,
                    "data_hoje": data_hoje,
                    "pergunta": prompt_usuario,
                    "historico": historico_formatado
                }

                # 2. GERAR O SQL (O LLM pensa)
                resposta_llm_objeto = sql_chain.invoke(input_data)
                sql_bruto = resposta_llm_objeto.content
                sql_gerado = sql_bruto.replace("```sql", "").replace("```", "").strip()
                
                # 3. CAMADA DE SEGURANÇA
                if not sql_gerado.upper().strip().startswith("SELECT"):
                    resposta = "Posso te ajudar a gerar consultas sobre vendas e estoque. O que deseja saber exatamente?"
                    st.markdown(resposta)
                    st.session_state.messages.append({"role": "assistant", "content": resposta})
                    st.stop()
                
                st.code(sql_gerado, language="sql")

                # 4. EXECUTAR O SQL
                with db_engine.connect() as conn:
                    resultado = conn.execute(text(sql_gerado))
                    dados = resultado.fetchall()

                # 5. TRADUZIR O RESULTADO
                prompt_traducao = (
                    f"A pergunta foi: '{prompt_usuario}'.\n"
                    f"O SQL gerado foi: '{sql_gerado}'.\n"
                    f"Os dados do banco são: {dados}\n\n"
                    f"Com base nisso, dê uma resposta curta e amigável em português para o usuário."
                )
                
                resposta_traducao_objeto = llm.invoke(prompt_traducao)
                resposta_final = resposta_traducao_objeto.content
                
                st.markdown(resposta_final)
                st.session_state.messages.append({"role": "assistant", "content": resposta_final})

            except Exception as e:
                st.error(f"Ocorreu um erro: {e}")
                st.session_state.messages.append({"role": "assistant", "content": f"Ocorreu um erro: {e}"})
