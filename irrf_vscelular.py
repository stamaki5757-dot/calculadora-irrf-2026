import json
import re
from pathlib import Path
import streamlit as st

st.set_page_config(
    page_title="IRRF - Imposto de Renda Retido na Fonte",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# --- ESTILO RESPONSIVO (CELULAR E DESKTOP) ---
st.markdown(
    """
    <style>
    /* Reduz margens excessivas no topo em telas pequenas */
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }
    /* Estiliza cada st.metric como um cartão limpo e legível no celular */
    div[data-testid="stMetric"] {
        background-color: rgba(128, 128, 128, 0.08);
        border: 1px solid rgba(128, 128, 128, 0.2);
        border-radius: 10px;
        padding: 12px 14px;
    }
    /* Ajusta o tamanho da fonte dos valores no celular para não cortar números altos */
    @media (max-width: 768px) {
        div[data-testid="stMetricValue"] {
            font-size: 1.35rem !important;
        }
        h3 {
            font-size: 1.25rem !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# --- CARREGAMENTO DAS TABELAS EXTERNAS ---
@st.cache_data
def carregar_tabelas(caminho_arquivo: str = "tabelas.json") -> dict:
    caminho = Path(__file__).parent / caminho_arquivo
    with open(caminho, "r", encoding="utf-8") as f:
        dados = json.load(f)

    for regime in dados["previdencia"].values():
        for faixa in regime:
            if faixa["limite"] is None:
                faixa["limite"] = float("inf")

    for faixa in dados["irrf"]["faixas"]:
        if faixa["limite"] is None:
            faixa["limite"] = float("inf")

    return dados


TABELAS = carregar_tabelas()
ANO_VIGENCIA = TABELAS["ano_vigencia"]
CONST = TABELAS["constantes"]


# --- FUNÇÕES AUXILIARES DE FORMATAÇÃO ---
def formata_br(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def parse_moeda_br(texto: str) -> float:
    limpo = re.sub(r"[^\d.,]", "", texto.strip())
    if not limpo:
        return 0.0
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    elif limpo.count(".") > 1:
        limpo = limpo.replace(".", "")
    try:
        return max(0.0, float(limpo))
    except ValueError:
        return 0.0


def formatar_input_moeda(chave_estado: str):
    valor = parse_moeda_br(st.session_state[chave_estado])
    st.session_state[chave_estado] = (
        f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    )


def resetar_campos():
    st.session_state.regime = "RGPS"
    st.session_state.aposentado = "não"
    st.session_state.idade = "menor 65 anos"
    st.session_state.dependentes = 0
    st.session_state.rend_texto = "0,00"
    st.session_state.outras_deducoes_texto = "0,00"


# --- FUNÇÕES DE CÁLCULO (DINÂMICAS PELO JSON) ---
def calc_previdencia_rgps(rend_bruto: float, is_aposentado: bool, tabelas: dict) -> float:
    if is_aposentado or rend_bruto <= 0:
        return 0.0

    const = tabelas["constantes"]
    if rend_bruto >= const["teto_rgps"]:
        return const["contrib_teto_rgps"]

    for faixa in tabelas["previdencia"]["rgps"]:
        if rend_bruto <= faixa["limite"]:
            return round((rend_bruto * faixa["aliquota"]) - faixa["deducao"], 2)
    return 0.0


def calc_previdencia_rpps(rend_bruto: float, is_aposentado: bool, tabelas: dict) -> float:
    if rend_bruto <= 0:
        return 0.0

    const = tabelas["constantes"]
    for faixa in tabelas["previdencia"]["rpps_federal"]:
        if rend_bruto <= faixa["limite"]:
            desconto = (rend_bruto * faixa["aliquota"]) - faixa["deducao"]
            if is_aposentado:
                desconto -= const["contrib_teto_rgps"]
            return round(max(0.0, desconto), 2)
    return 0.0


def calc_irrf_detalhado(
    rend_bruto: float,
    contrib_prev: float,
    num_dependentes: int,
    outras_deducoes: float,
    is_aposentado: bool,
    is_maior_65: bool,
    tabelas: dict,
) -> dict:
    if rend_bruto <= 0:
        return {
            "irrf_final": 0.0,
            "rend_tributavel": 0.0,
            "deducoes_legais_total": 0.0,
            "deducao_aplicada": 0.0,
            "tipo_deducao": "Nenhuma",
            "base_calculo": 0.0,
            "irrf_tabela": 0.0,
            "reducao_lei": 0.0,
        }

    const = tabelas["constantes"]
    regras_irrf = tabelas["irrf"]
    regra_red = regras_irrf["reducao_lei_15270"]

    isencao_etaria = const["isencao_65_anos"] if (
        is_aposentado and is_maior_65) else 0.0
    rend_tributavel = max(0.0, rend_bruto - isencao_etaria)

    deducoes_legais = (
        contrib_prev + (const["deducao_dependente"] *
                        num_dependentes) + outras_deducoes
    )

    if deducoes_legais >= const["desconto_simplificado"]:
        deducao_aplicada = deducoes_legais
        tipo_deducao = "Deduções Legais"
    else:
        deducao_aplicada = const["desconto_simplificado"]
        tipo_deducao = "Desconto Simplificado"

    base_calculo = max(0.0, rend_tributavel - deducao_aplicada)

    irrf_tabela = 0.0
    for faixa in regras_irrf["faixas"]:
        if base_calculo <= faixa["limite"]:
            irrf_tabela = max(
                0.0, (base_calculo * faixa["aliquota"]) - faixa["deducao"])
            break

    if rend_tributavel <= regra_red["limite_isencao_total"]:
        reducao_lei = regra_red["valor_reducao_total"]
    elif rend_tributavel <= regra_red["limite_reducao_gradual"]:
        reducao_lei = max(
            0.0, regra_red["formula_base"] -
            (regra_red["formula_fator"] * rend_tributavel)
        )
    else:
        reducao_lei = 0.0

    irrf_final = round(max(0.0, irrf_tabela - reducao_lei), 2)

    return {
        "irrf_final": irrf_final,
        "rend_tributavel": round(rend_tributavel, 2),
        "deducoes_legais_total": round(deducoes_legais, 2),
        "deducao_aplicada": round(deducao_aplicada, 2),
        "tipo_deducao": tipo_deducao,
        "base_calculo": round(base_calculo, 2),
        "irrf_tabela": round(irrf_tabela, 2),
        "reducao_lei": round(reducao_lei, 2),
    }


# --- INICIALIZAÇÃO DE ESTADO ---
if "rend_texto" not in st.session_state:
    st.session_state.rend_texto = "0,00"
if "outras_deducoes_texto" not in st.session_state:
    st.session_state.outras_deducoes_texto = "0,00"


# --- CABEÇALHO RESPONSIVO ---
col_titulo, col_btn = st.columns([8, 2], vertical_alignment="center")
with col_titulo:
    st.markdown('')
    st.markdown('')
    st.markdown('')
    st.subheader(f"Calculadora IRRF ({ANO_VIGENCIA})")
with col_btn:
    st.button("Limpar", icon=":material/refresh:",
              on_click=resetar_campos, use_container_width=True)


# --- ENTRADAS OTIMIZADAS PARA MOBILE E DESKTOP ---
# Linha 1: Campo principal em destaque (Rendimento Bruto) + Regime
row1_c1, row1_c2 = st.columns(2)
with row1_c1:
    st.text_input(
        "Rendimento bruto (R$):",
        key="rend_texto",
        on_change=formatar_input_moeda,
        args=("rend_texto",),
    )
with row1_c2:
    regime = st.selectbox("Regime previdenciário:", [
                          "RGPS", "RPPS Federal"], key="regime")

# Linha 2: Perfil do contribuinte em 3 colunas equilibradas
row2_c1, row2_c2, row2_c3 = st.columns(3)
with row2_c1:
    aposentado = st.selectbox("Aposentado:", ["não", "sim"], key="aposentado")
with row2_c2:
    idade = st.selectbox(
        "Faixa etária:",
        ["menor 65 anos", "maior 65 anos"],
        key="idade",
        disabled=(aposentado == "não"),
    )
with row2_c3:
    dependente_quant = st.number_input(
        "Dependentes:", min_value=0, max_value=30, value=0, step=1, key="dependentes"
    )

# Campo opcional recolhido
tem_outras_deducoes = parse_moeda_br(
    st.session_state.outras_deducoes_texto) > 0
with st.expander("Outras deduções legais (opcional)", expanded=tem_outras_deducoes):
    col_ded1, col_ded2 = st.columns([1, 1], vertical_alignment="center")
    with col_ded1:
        st.text_input(
            "Valor total (R$):",
            key="outras_deducoes_texto",
            on_change=formatar_input_moeda,
            args=("outras_deducoes_texto",),
            help="Informe valores mensais dedutíveis na fonte, como pensão alimentícia judicial ou previdência complementar (PGBL/Funpresp).",
        )
    with col_ded2:
        st.caption(
            "Inclua descontos mensais permitidos pela Receita Federal na base de cálculo do IRRF, "
            "como **pensão alimentícia judicial** ou **previdência complementar**."
        )


# --- EXECUÇÃO DOS CÁLCULOS ---
rend_bruto = parse_moeda_br(st.session_state.rend_texto)
outras_deducoes = parse_moeda_br(st.session_state.outras_deducoes_texto)
is_aposentado = aposentado == "sim"
is_maior_65 = idade == "maior 65 anos"

contrib_prev = (
    calc_previdencia_rgps(rend_bruto, is_aposentado, TABELAS)
    if regime == "RGPS"
    else calc_previdencia_rpps(rend_bruto, is_aposentado, TABELAS)
)

resultado = calc_irrf_detalhado(
    rend_bruto=rend_bruto,
    contrib_prev=contrib_prev,
    num_dependentes=dependente_quant,
    outras_deducoes=outras_deducoes,
    is_aposentado=is_aposentado,
    is_maior_65=is_maior_65,
    tabelas=TABELAS,
)

irrf_valor = resultado["irrf_final"]
deducao_dep = dependente_quant * CONST["deducao_dependente"]
liquido = max(0.0, rend_bruto - contrib_prev - irrf_valor)
aliquota_efetiva = (irrf_valor / rend_bruto * 100) if rend_bruto > 0 else 0.0

st.divider()

# --- RESULTADOS EM GRADE RESPONSIVA (2 DESTAQUES + 3 DETALHES) ---
# Destaque principal no topo (fácil de ler sem rolar no celular)
res_top1, res_top2 = st.columns(2)
res_top1.metric("Rendimento Bruto", formata_br(rend_bruto))
res_top2.metric("Rendimento Líquido", formata_br(liquido))

# Detalhes secundários logo abaixo
res_bot1, res_bot2, res_bot3 = st.columns(3)
res_bot1.metric(
    "IRRF Retido",
    formata_br(irrf_valor),
    delta=f"Alíquota efetiva: {aliquota_efetiva:.2f}%" if rend_bruto > 0 else None,
    delta_color="inverse" if irrf_valor > 0 else "off",
)
res_bot2.metric("Previdência", formata_br(contrib_prev),
                delta=regime, delta_color="off")
res_bot3.metric(
    "Dedução Dependentes",
    formata_br(deducao_dep),
    delta=f"+ {formata_br(outras_deducoes)} outras" if outras_deducoes > 0 else None,
    delta_color="off",
)


# --- MEMÓRIA DE CÁLCULO ---

if rend_bruto > 0:
    with st.expander("Ver memória de cálculo detalhada"):
        d1, d2 = st.columns(2)
        d1.write(
            f"Rendimento Tributável:\n{formata_br(resultado['rend_tributavel'])}")
        d2.write(
            f"Dedução Aplicada ({resultado['tipo_deducao']}):\n"
            f"- {formata_br(resultado['deducao_aplicada'])} (Legais: {formata_br(resultado['deducoes_legais_total'])})"
        )
        d3, d4 = st.columns(2)
        d3.write(
            f"Base de Cálculo IRRF:\n{formata_br(resultado['base_calculo'])}")
        d4.write(
            f"Redução Lei nº 15.270/2025:\n"
            f"- {formata_br(resultado['reducao_lei'])} (Tabela: {formata_br(resultado['irrf_tabela'])})"
        )
if outras_deducoes > 0:
    st.caption(
        "Nota: O Rendimento Líquido exibido acima considera apenas os descontos obrigatórios de Previdência e IRRF, "
        "sem subtrair o valor informado em Outras Deduções."
    )
    st.divider()
    st.caption(
        f"""
Aviso Legal (Disclaimer): Esta ferramenta tem caráter estritamente informativo e educacional,
baseada nas tabelas progressivas, limites previdenciários e regras de isenção/redução do IRRF vigentes em {ANO_VIGENCIA}
(Lei nº 15.270/2025 e normas da Receita Federal). Os resultados são simulações estimadas e podem variar conforme
rubricas específicas do seu contracheque (como verbas indenizatórias, previdência complementar, pensão alimentícia
ou dependentes). Esta calculadora não substitui o cálculo oficial do departamento pessoal/órgão pagador nem a
orientação de um contador. Privacidade: Nenhum dado financeiro inserido nesta página é armazenado ou compartilhado.
"""
    )
