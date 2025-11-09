import streamlit as st
from sqlalchemy import create_engine, text
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
import datetime
import json
import re
import pandas as pd
from regras_protheus import REGRAS_NEGOCIO, REGRAS_PROTHEUS

# =======================================
# 1️⃣ CONFIGURAÇÕES E CONEXÕES
# =======================================

st.set_page_config(page_title="🤖 Chatbot Protheus Inteligente", layout="centered")
st.title("🤖 Chatbot Protheus com Dicionário SX3/SIX Dinâmico")

GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
DB_HOST = st.secrets["DB_HOST"]
DB_NAME = st.secrets["DB_NAME"]
DB_USER = st.secrets["DB_USER"]
DB_PASS = st.secrets["DB_PASS"]

CONNECTION_STRING = (
    f"mssql+pyodbc://{DB_USER}:{DB_PASS}@{DB_HOST}/"
    f"{DB_NAME}?driver=ODBC+Driver+17+for+SQL+Server"
)

db_engine = create_engine(CONNECTION_STRING)

# Modelos
llm_sql = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=GOOGLE_API_KEY)
llm_texto = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key=GOOGLE_API_KEY)
#modo_debug = st.sidebar.checkbox("Ativar modo debug (mostrar SQL)")

# =======================================
# 2️⃣ LEITURA DO DICIONÁRIO SX3/SIX
# =======================================

@st.cache_data(ttl=3600, show_spinner=False)
def obter_mapeamento_protheus(_engine):
    tabelas = ["SC5", "SC6", "SD2", "SF2", "SB1", "SB2", "SA1", "SA2"]
    mapeamento = {}
    with _engine.connect() as conn:
        for tabela in tabelas:
            try:
                query = text(f"""
                    SELECT X3_CAMPO, X3_TIPO, X3_TAMANHO, X3_DECIMAL, X3_TITULO, X3_DESCRIC
                    FROM SX3010
                    WHERE X3_ARQUIVO = '{tabela[:3]}' AND D_E_L_E_T_ = ' '
                    ORDER BY X3_ORDEM
                """)
                rows = conn.execute(query).fetchall()
                mapeamento[tabela] = {
                    "campos": [
                        {
                            "campo": r[0],
                            "tipo": r[1],
                            "tamanho": r[2],
                            "decimal": r[3],
                            "titulo": r[4],
                            "descricao": r[5],
                        }
                        for r in rows
                    ]
                }
            except Exception:
                continue
    return mapeamento

with st.spinner("📚 Lendo dicionário SX3/SIX..."):
    MAPEAMENTO_TABELAS = obter_mapeamento_protheus(db_engine)

mapeamento_formatado = json.dumps(MAPEAMENTO_TABELAS, indent=2, ensure_ascii=False)

# =======================================
# 3️⃣ PROMPTS DE COMPORTAMENTO
# =======================================

intent_prompt = """
Você é um classificador de intenção para um assistente de negócios do Protheus.
Analise a pergunta do usuário e responda **apenas** com uma palavra:
- "sql" → se a pergunta requer **dados reais** do banco (consultas sobre pedidos, vendas, produtos, estoques, valores, contagens, listagens, agregações, períodos, filiais, clientes, etc.)
- "texto" → se a pergunta requer uma **resposta conceitual, explicativa, saudação, teste ou ajuda de procedimento**.

Regras:
- Perguntas curtas como "teste", "oi", "funciona?" → "texto"
- Pedidos de definição ou explicação ("o que é SC5?", "como cadastrar produto?") → "texto"
- Perguntas com "total", "quantidade", "por filial", "mês", "ano", "vendas" → "sql"
- Em caso de dúvida → "texto"

Pergunta:
{pergunta}

Retorne apenas: sql ou texto
"""

short_answer_prompt = """
Você é um assistente conversacional para usuários de negócio do Protheus.
Responda em **português claro**, de forma **curta, direta e amigável**.

Regras:
1. Máximo de **2 frases curtas**.
2. Tom profissional e simpático — sem jargões técnicos.
3. Se for uma saudação ou teste (ex: "teste", "oi"), diga algo leve, como "Tudo certo — pronto pra ajudar! 😊"
4. Se for explicação, resuma (ex: "SC5 é o cabeçalho de pedidos, com cliente e valores.").
5. Nunca gere SQL aqui.

Pergunta:
{pergunta}
"""

prompt_template = PromptTemplate(
    input_variables=["regras", "mapeamento", "data_hoje", "pergunta", "historico"],
    template=open("prompt_template.txt", encoding="utf-8").read()
)
sql_chain = prompt_template | llm_sql

# =======================================
# 4️⃣ EXECUÇÃO
# =======================================

def classificar_intencao(pergunta):
    resposta = llm_texto.invoke(intent_prompt.format(pergunta=pergunta)).content.strip().lower()
    return "sql" if "sql" in resposta else "texto"

def gerar_resposta_texto(pergunta):
    return llm_texto.invoke(short_answer_prompt.format(pergunta=pergunta)).content.strip()

def gerar_sql_real(pergunta, historico):
    data_hoje = datetime.date.today().strftime("%Y-%m-%d")
    entrada = {
        "regras": REGRAS_NEGOCIO + "\n\n" + json.dumps(REGRAS_PROTHEUS, ensure_ascii=False, indent=2),
        "mapeamento": mapeamento_formatado,
        "data_hoje": data_hoje,
        "pergunta": pergunta,
        "historico": historico,
    }
    resposta = sql_chain.invoke(entrada).content
    sql_blocks = re.findall(r"```sql\s+(.*?)```", resposta, flags=re.DOTALL | re.IGNORECASE)
    return resposta, sql_blocks

def executar_sql_real(sql_query):
    try:
        with db_engine.connect() as conn:
            result = conn.execute(text(sql_query))
            rows = result.mappings().all()
            return pd.DataFrame(rows)
    except Exception as e:
        # if modo_debug:
        #     st.exception(e)
        # else:
        st.error("⚠️ Erro ao executar a consulta SQL.")
        #return pd.DataFrame()

# =======================================
# 5️⃣ INTERFACE DE CHAT
# =======================================

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Olá 👋! Posso gerar consultas SQL reais do Protheus ou responder perguntas simples. O que deseja saber?"}
    ]

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if pergunta := st.chat_input("Digite sua pergunta sobre o Protheus..."):
    st.session_state.messages.append({"role": "user", "content": pergunta})
    with st.chat_message("user"):
        st.markdown(pergunta)

    with st.chat_message("assistant"):
        with st.spinner("🎯 Entendendo sua intenção..."):
            tipo = classificar_intencao(pergunta)

        if tipo == "texto":
            # respostas conceituais — pode usar markdown
            with st.spinner("💬 Respondendo..."):
                resposta = gerar_resposta_texto(pergunta)
                st.markdown(resposta)
            st.session_state.messages.append({"role": "assistant", "content": resposta})

        else:
            # respostas SQL — NÃO renderizar o markdown completo
            with st.spinner("🧠 Gerando SQL real..."):
                historico = "\n".join(f"{m['role']}: {m['content']}" for m in st.session_state.messages[-5:])
                resposta, sql_blocks = gerar_sql_real(pergunta, historico)

            if sql_blocks:
                for sql_query in sql_blocks:
                    sql_query = sql_query.strip()
                    st.code(sql_query, language="sql")  # Exibe só o código
                    # if modo_debug:
                    #     st.info(f"Executando no banco {DB_NAME}...")

                    df = executar_sql_real(sql_query)
                    if not df.empty:
                        st.success(f"✅ {len(df)} registros retornados.")
                        st.dataframe(df, use_container_width=True)
                    else:
                        st.info("ℹ️ Nenhum registro encontrado.")
            else:
                st.warning("⚠️ Nenhuma query SQL detectada.")


st.markdown("---")
st.caption("Desenvolvido com ❤️ | Protheus + SQL Server + Streamlit + Gemini Inteligente")
