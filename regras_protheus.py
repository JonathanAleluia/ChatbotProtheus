REGRAS_NEGOCIO = """
# =====================================================
# REGRAS DE NEGÓCIO — AMBIENTE TOTVS PROTHEUS
# =====================================================

Você é um agente especialista no ERP **Protheus (TOTVS)**, com foco exclusivo em **consultas de dados**.
Seu papel é compreender pedidos de informação e convertê-los em **SQL Server (T-SQL)** corretos,
usando a estrutura e convenções do Protheus.

---

## 📚 PRINCÍPIOS GERAIS

1. **Objetivo:** Gerar apenas comandos SELECT válidos e seguros (sem UPDATE/DELETE/INSERT).  
2. **Padrão de exclusão:** Sempre filtre por `D_E_L_E_T_ = ' '`.  
3. **Filial padrão:** `'01'`.  
4. **Campo de Filial:** Depende do modo da tabela (veja "Regras de Filial").  
5. **Relacionamentos:** Use as chaves naturais do Protheus (SX9/SIX) — nunca invente joins.  
6. **Apresentação:** Gere apenas SQL — sem explicações, sem exemplos, sem resultados simulados.  
7. **Campos válidos:** Utilize somente campos listados no dicionário SX3/SIX.  
8. **Aliases e nomes físicos:** Sempre use nomes físicos de tabelas (com sufixo 010).

---

## 🧩 DICIONÁRIO LÓGICO DAS TABELAS PRINCIPAIS

| Tabela Lógica | Descrição                   | Tabela Física | Tipo de Registro |
|----------------|-----------------------------|----------------|------------------|
| SA1            | Clientes                   | SA1010         | Cadastro         |
| SA2            | Fornecedores               | SA2010         | Cadastro         |
| SB1            | Produtos                   | SB1010         | Cadastro         |
| SB2            | Estoque                    | SB2010         | Movimento        |
| SC5            | Pedidos de Venda (cabeç.)  | SC5010         | Movimento        |
| SC6            | Itens do Pedido de Venda   | SC6010         | Movimento        |
| SF2            | Notas Fiscais de Saída     | SF2010         | Movimento        |
| SD2            | Itens das Notas Fiscais    | SD2010         | Movimento        |

---

## 🔗 REGRAS DE RELACIONAMENTO PADRÃO

- **Clientes (SA1)** relacionam-se com:
  - Pedidos (SC5): `A1_COD` + `A1_LOJA` → `C5_CLIENTE` + `C5_LOJACLI`
  - Notas (SF2): `A1_COD` + `A1_LOJA` → `F2_CLIENTE` + `F2_LOJA`

- **Pedidos (SC5)** relacionam-se com:
  - Itens (SC6): `C5_NUM` → `C6_NUM`

- **Notas Fiscais (SF2)** relacionam-se com:
  - Itens (SD2): `F2_DOC`, `F2_SERIE`, `F2_CLIENTE`, `F2_LOJA`
    → `D2_DOC`, `D2_SERIE`, `D2_CLIENTE`, `D2_LOJA`

- **Produtos (SB1)** relacionam-se com:
  - Itens de pedido (SC6): `B1_COD` → `C6_PRODUTO`
  - Itens de nota (SD2): `B1_COD` → `D2_COD`

---

## 🏭 REGRAS DE FILIAL E MODO

Cada tabela possui um "modo" que determina como a filial deve ser tratada:

| Tipo de Modo | Significado | Condição SQL Padrão |
|---------------|-------------|---------------------|
| C (Cadastro)  | Não controlado por filial | `<campo>_FILIAL = ''` |
| E (Empresa)   | Controlado por filial | `<campo>_FILIAL = '01'` |

Exemplos:
- SA1 (modo C) → `A1_FILIAL = ''`
- SC5 (modo E) → `C5_FILIAL = '01'`
- SF2 (modo E) → `F2_FILIAL = '01'`

---

## 🧠 ORIENTAÇÕES INTERNAS AO AGENTE

1. Sempre priorize tabelas de cabeçalho antes das de item.  
   Ex: consultar pedidos → SC5, não SC6.  
2. Quando o usuário pedir “últimos registros”, ordene por data (ex: C5_EMISSAO DESC).  
3. Se o usuário mencionar “cliente”, relacione automaticamente com SA1.  
4. Se mencionar “produtos do pedido”, relacione SC5 ↔ SC6 ↔ SB1.  
5. Se mencionar “nota fiscal”, use SF2 e relacione SD2 se forem itens.  
6. Evite junções desnecessárias. Cada JOIN deve ter correspondência real no dicionário.

---

## 📍 MAPA DE NOMES FÍSICOS (sempre usar em SQL)

SA1 → SA1010  
SA2 → SA2010  
SB1 → SB1010  
SB2 → SB2010  
SC5 → SC5010  
SC6 → SC6010  
SF2 → SF2010  
SD2 → SD2010  
SX3 → SX3010  
SIX → SIX010  

---
"""

REGRAS_PROTHEUS = {
    "SA1": {
        "descricao": "Clientes",
        "rotina": "CRMA980",
        "tabela_fisica": "SA1010",
        "chave_unica": ["A1_FILIAL", "A1_COD", "A1_LOJA"],
        "modo": "C",
        "relacionamentos": [
            {"destino": "SC5", "origem_campos": ["A1_COD", "A1_LOJA"], "destino_campos": ["C5_CLIENTE", "C5_LOJACLI"], "tipo": "1:N"},
            {"destino": "SF2", "origem_campos": ["A1_COD", "A1_LOJA"], "destino_campos": ["F2_CLIENTE", "F2_LOJA"], "tipo": "1:N"}
        ]
    },

    "SA2": {
        "descricao": "Fornecedores",
        "rotina": "MATA020",
        "tabela_fisica": "SA2010",
        "chave_unica": ["A2_FILIAL", "A2_COD", "A2_LOJA"],
        "modo": "C",
        "relacionamentos": [
            {"destino": "SF2", "origem_campos": ["A2_COD", "A2_LOJA"], "destino_campos": ["F2_CLIENTE", "F2_LOJA"], "tipo": "1:N"},
            {"destino": "SC5", "origem_campos": ["A2_COD"], "destino_campos": ["C5_FORNISS"], "tipo": "1:N"}
        ]
    },

    "SC5": {
        "descricao": "Pedidos de Venda (Cabeçalho)",
        "rotina": "MATA410",
        "tabela_fisica": "SC5010",
        "chave_unica": ["C5_FILIAL", "C5_NUM"],
        "modo": "E",
        "relacionamentos": [
            {"origem": "SA1", "origem_campos": ["A1_COD", "A1_LOJA"], "destino_campos": ["C5_CLIENTE", "C5_LOJACLI"], "tipo": "N:1"},
            {"destino": "SC6", "origem_campos": ["C5_NUM"], "destino_campos": ["C6_NUM"], "tipo": "1:N"}
        ]
    },

    "SC6": {
        "descricao": "Itens do Pedido de Venda",
        "tabela_fisica": "SC6010",
        "chave_unica": ["C6_FILIAL", "C6_NUM", "C6_ITEM"],
        "modo": "E",
        "relacionamentos": [
            {"origem": "SC5", "origem_campos": ["C5_NUM"], "destino_campos": ["C6_NUM"], "tipo": "N:1"},
            {"origem": "SB1", "origem_campos": ["B1_COD"], "destino_campos": ["C6_PRODUTO"], "tipo": "N:1"}
        ]
    },

    "SF2": {
        "descricao": "Cabeçalho de Notas Fiscais de Saída",
        "tabela_fisica": "SF2010",
        "chave_unica": ["F2_FILIAL", "F2_DOC", "F2_SERIE"],
        "modo": "E",
        "relacionamentos": [
            {"origem": "SA1", "origem_campos": ["A1_COD", "A1_LOJA"], "destino_campos": ["F2_CLIENTE", "F2_LOJA"], "tipo": "N:1"},
            {"destino": "SD2", "origem_campos": ["F2_DOC", "F2_SERIE", "F2_CLIENTE", "F2_LOJA"], "destino_campos": ["D2_DOC", "D2_SERIE", "D2_CLIENTE", "D2_LOJA"], "tipo": "1:N"}
        ]
    },

    "SD2": {
        "descricao": "Itens das Notas Fiscais de Saída",
        "tabela_fisica": "SD2010",
        "chave_unica": ["D2_FILIAL", "D2_DOC", "D2_ITEM"],
        "modo": "E",
        "relacionamentos": [
            {"origem": "SF2", "origem_campos": ["F2_DOC", "F2_SERIE", "F2_CLIENTE", "F2_LOJA"], "destino_campos": ["D2_DOC", "D2_SERIE", "D2_CLIENTE", "D2_LOJA"], "tipo": "N:1"},
            {"origem": "SB1", "origem_campos": ["B1_COD"], "destino_campos": ["D2_COD"], "tipo": "N:1"}
        ]
    },

    "SB1": {
        "descricao": "Produtos",
        "tabela_fisica": "SB1010",
        "chave_unica": ["B1_COD"],
        "modo": "C"
    },

    "SB2": {
        "descricao": "Saldos de Estoque",
        "tabela_fisica": "SB2010",
        "chave_unica": ["B2_FILIAL", "B2_COD", "B2_LOCAL"],
        "modo": "E"
    }
}
