import streamlit as st
from sqlalchemy import create_engine, text
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
import datetime
import json
import re
import pandas as pd
import locale  # Para formatar moeda

# =======================================
# 0️⃣ REGRAS DE EXEMPLO (Substitua pelo seu arquivo)
# =======================================
# Como eu não tenho seu arquivo 'regras_protheus', adicionei exemplos.
# Substitua estas linhas pelo seu 'from regras_protheus import ...'
REGRAS_NEGOCIO = """
- O campo D_E_L_E_T_ = ' ' sempre indica um registro ativo.
- O campo E_N_D_E_R_E_C_O (sem 'Ç') é usado para endereço.
- Use a filial '01' como padrão para tabelas exclusivas (modo 'E').
"""
REGRAS_PROTHEUS = {
    "SA1": "Cadastro de Clientes (Modo C)",
    "SB1": "Cadastro de Produtos (Modo C)",
    "SC5": "Cabeçalho de Pedidos de Venda (Modo E)",
    "SD2": "Itens de Venda da Nota Fiscal (Modo E)"
}
# =======================================
# 1️⃣ CONFIGURAÇÕES E CONEXÕES
# =======================================

st.set_page_config(page_title="🤖 Chatbot Protheus Inteligente", layout="centered")

st.title("🤖 Chatbot Protheus com Dicionário SX3/SIX Dinâmico")

# Carregamento seguro das chaves
try:
    GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
    DB_HOST = st.secrets["DB_HOST"]
    DB_NAME = st.secrets["DB_NAME"]
    DB_USER = st.secrets["DB_USER"]
    DB_PASS = st.secrets["DB_PASS"]
except KeyError as e:
    st.error(f"Atenção: A chave secreta {e} não foi encontrada. Configure-a no Streamlit.")
    st.stop()


CONNECTION_STRING = (
    f"mssql+pyodbc://{DB_USER}:{DB_PASS}@{DB_HOST}/"
    f"{DB_NAME}?driver=ODBC+Driver+17+for+SQL+Server"
)

# Bloco try-except para a conexão inicial
try:
    db_engine = create_engine(CONNECTION_STRING)
    # Testa a conexão
    with db_engine.connect() as conn:
        pass
except Exception as e:
    st.error(f"Falha ao conectar ao banco de dados: {e}")
    st.stop()


# Modelo Único (Eficiência)
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=GOOGLE_API_KEY, temperature=0.0)

# =======================================
# 2️⃣ LEITURA DO DICIONÁRIO SX3/SIX (OTIMIZADO)
# =======================================

@st.cache_data(ttl=3600, show_spinner=False)
def obter_mapeamento_protheus(_engine):
    """
    Busca o dicionário de dados (SX3) de forma OTIMIZADA para o LLM.
    Cria um mapeamento simples {tabela: {campo: "Tipo: ..., Descrição: ..."}}
    """
    tabelas = ["SC5", "SC6", "SD2", "SF2", "SB1", "SB2", "SA1", "SA2"]
    mapeamento = {}
    
    with _engine.connect() as conn:
        for tabela in tabelas:
            try:
                # 1. Query otimizada: Trazemos apenas o que o LLM precisa
                query = text(f"""
                    SELECT 
                        X3_CAMPO, 
                        X3_TIPO, 
                        X3_TITULO, 
                        X3_DESCRIC 
                    FROM SX3010
                    WHERE X3_ARQUIVO = '{tabela[:3]}' AND D_E_L_E_T_ = ' '
                    ORDER BY X3_ORDEM
                """)
                rows = conn.execute(query).fetchall()
                
                if not rows:
                    st.toast(f"ℹ️ Dicionário: Nenhum campo encontrado para {tabela} no SX3.", icon="ℹ️")
                    continue

                # 2. Cria o dicionário interno da tabela
                mapeamento_tabela = {}
                for r in rows:
                    campo = r[0].strip()
                    tipo = r[1].strip()
                    titulo = r[2].strip()
                    descricao = r[3].strip() # X3_DESCRIC

                    # 3. Combina título e descrição para dar o máximo de contexto
                    contexto_campo = titulo
                    if descricao and descricao.strip() != titulo:
                        contexto_campo = f"{titulo} ({descricao})"
                    
                    # 4. Cria a entrada final, muito mais leve
                    mapeamento_tabela[campo] = f"Tipo: {tipo}, Descrição: {contexto_campo}"

                mapeamento[tabela] = mapeamento_tabela
                
            except Exception as e:
                st.error(f"Erro ao ler dicionário para {tabela}: {e}")
                continue
    return mapeamento

with st.spinner("📚 Lendo dicionário SX3/SIX..."):
    MAPEAMENTO_TABELAS = obter_mapeamento_protheus(db_engine)
    if not MAPEAMENTO_TABELAS:
        st.error("Falha crítica: O mapeamento de tabelas está vazio. Verifique a conexão e a tabela SX3010.")
        st.stop()

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

# Carrega o prompt principal de um arquivo externo
try:
    prompt_template_content = open("prompt_template.txt", encoding="utf-8").read()
except FileNotFoundError:
    st.error("Erro: Arquivo 'prompt_template.txt' não encontrado.")
    # Define um template de fallback caso o arquivo não exista
    prompt_template_content = """
    ERRO: prompt_template.txt não encontrado.
    Pergunta: {pergunta}
    Gere um SQL simples baseado nesta pergunta, usando {mapeamento}.
    """

prompt_template = PromptTemplate(
    input_variables=["regras", "mapeamento", "data_hoje", "pergunta", "historico"],
    template=prompt_template_content
)

sql_chain = prompt_template | llm

# =======================================
# 4️⃣ EXECUÇÃO, SEGURANÇA E EXIBIÇÃO
# =======================================

# Tenta configurar o locale para R$ (Reais)
try:
    locale.setlocale(locale.LC_ALL, 'pt_BR.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, 'Portuguese_Brazil.1252')
    except locale.Error:
        st.toast("Não foi possível configurar o locale 'pt_BR' para formatar moeda.", icon="⚠️")

# (Segurança)
FORBIDDEN_KEYWORDS = [
    'DELETE', 'UPDATE', 'INSERT', 'DROP', 'TRUNCATE', 
    'ALTER', 'GRANT', 'REVOKE', 'EXEC', 'EXECUTE', 'CREATE',
    'MERGE', 'COMMIT', 'ROLLBACK'
]

def formatar_moeda(valor):
    """Tenta formatar um valor numérico como moeda (R$)."""
    try:
        return locale.currency(valor, grouping=True)
    except Exception:
        return f"R$ {valor:,.2f}"

def classificar_intencao(pergunta):
    resposta = llm.invoke(intent_prompt.format(pergunta=pergunta)).content.strip().lower()
    return "sql" if "sql" in resposta else "texto"

def gerar_resposta_texto(pergunta):
    return llm.invoke(short_answer_prompt.format(pergunta=pergunta)).content.strip()

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

def validar_e_executar_sql(sql_query):
    """
    (Segurança) Valida a query antes de executar.
    Levanta um ValueError se a query for insegura.
    """
    sql_upper = sql_query.upper()

    if not sql_upper.strip().startswith('SELECT'):
        raise ValueError("Ação não permitida. Apenas consultas 'SELECT' são autorizadas.")

    for keyword in FORBIDDEN_KEYWORDS:
        if keyword in sql_upper:
            raise ValueError(f"Ação não permitida. A consulta contém a palavra-chave bloqueada: '{keyword}'.")
    
    try:
        with db_engine.connect() as conn:
            result = conn.execute(text(sql_query))
            rows = result.mappings().all()
            return pd.DataFrame(rows)
    except Exception as e:
        raise e

def exibir_dados_de_forma_inteligente(df):
    """
    (Exibição Inteligente)
    Decide a melhor forma de exibir o dataframe no Streamlit
    e retorna o conteúdo em markdown para salvar no histórico.
    """
    
    # --- OPÇÃO 1: KPI (Metric) ---
    if len(df) == 1 and len(df.columns) == 1:
        nome_coluna = df.columns[0]
        valor = df.iloc[0, 0]
        
        # Exibição temporária (bonita)
        if isinstance(valor, (int, float)):
            if "Total" in nome_coluna or "Valor" in nome_coluna or "Venda" in nome_coluna:
                st.metric(label=nome_coluna, value=formatar_moeda(valor))
            else:
                st.metric(label=nome_coluna, value=f"{valor}")
        else:
            st.metric(label=nome_coluna, value=valor)
        
        # Conteúdo para salvar no histórico
        return f"**{nome_coluna}:** {valor}\n"

    # --- OPÇÃO 2: TABELA MODERNA (Data Editor) ---
    st.info("Visualização da tabela (primeiras 50 linhas):")
    st.data_editor(
        df.head(50), 
        use_container_width=True, 
        disabled=True, 
        hide_index=True
    )
    
    # Conteúdo para salvar no histórico (Markdown)
    markdown_para_salvar = df.head(20).to_markdown(index=False)
    if len(df) > 20:
        markdown_para_salvar += f"\n*(... e mais {len(df)-20} linhas)*"
        
    return markdown_para_salvar

# =======================================
# 5️⃣ INTERFACE DE CHAT (COM CORREÇÃO DE HISTÓRICO)
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
            # Respostas conceituais — simples
            with st.spinner("💬 Respondendo..."):
                resposta = gerar_resposta_texto(pergunta)
                st.markdown(resposta)
            st.session_state.messages.append({"role": "assistant", "content": resposta})

        else:
            # Respostas SQL — Lógica Refatorada
            with st.spinner("🧠 Gerando SQL real..."):
                historico = "\n".join(f"{m['role']}: {m['content']}" for m in st.session_state.messages[-5:])
                resposta_completa, sql_blocks = gerar_sql_real(pergunta, historico)

            # 1. Extrai o texto de explicação da resposta completa
            texto_resposta = resposta_completa
            if sql_blocks:
                for block in sql_blocks:
                    texto_resposta = texto_resposta.replace(f"```sql\n{block}\n```", "", 1).replace(f"```sql\n{block}```", "", 1)
            texto_resposta = texto_resposta.strip()

            # 2. 'conteudo_para_salvar' será o markdown COMPLETO
            conteudo_para_salvar = texto_resposta 
            
            # 3. Exibe a parte textual (se houver) AGORA
            if texto_resposta:
                st.markdown(texto_resposta)

            # 4. Processa e executa os blocos SQL
            if sql_blocks:
                for sql_query in sql_blocks:
                    sql_query = sql_query.strip()
                    
                    st.code(sql_query, language="sql")
                    conteudo_para_salvar += f"\n\n```sql\n{sql_query}\n```\n"
                    
                    try:
                        df = validar_e_executar_sql(sql_query) 
                        
                        if not df.empty:
                            msg_sucesso = f"✅ {len(df)} registros retornados."
                            st.success(msg_sucesso)
                            conteudo_para_salvar += f"\n{msg_sucesso}\n"

                            # Chama a nova função de exibição
                            markdown_dos_dados = exibir_dados_de_forma_inteligente(df)
                            conteudo_para_salvar += markdown_dos_dados

                        else:
                            msg_info = "ℹ️ Nenhum registro encontrado."
                            st.info(msg_info)
                            conteudo_para_salvar += f"\n{msg_info}"
                    
                    except ValueError as ve: 
                        msg_erro = f"⚠️ Consulta bloqueada: {ve}"
                        st.error(msg_erro) 
                        conteudo_para_salvar += f"\n{msg_erro}" 
                    except Exception as e: 
                        msg_erro_banco = "⚠️ Erro ao executar a consulta no banco."
                        st.error(msg_erro_banco)                         
                        conteudo_para_salvar += f"\n{msg_erro_banco}" 

            elif not texto_resposta:
                # Fallback se o LLM não gerar NADA
                conteudo_para_salvar = "Desculpe, não consegui gerar uma consulta SQL válida para isso."
                st.warning(conteudo_para_salvar)

            # 5. Salva o conteúdo COMPLETO e formatado no histórico
            st.session_state.messages.append({"role": "assistant", "content": conteudo_para_salvar.strip()})


st.markdown("---")
st.caption("Desenvolvido com ❤️ | Protheus + SQL Server + Streamlit + Gemini (v3 - Exibição Inteligente)")