import streamlit as st

st.set_page_config(
    page_title="IRRF - Imposto de Renda Retido na Fonte",
    layout="wide",
    initial_sidebar_state="expanded",
)


def formata_br(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def resetar_campos():
    st.session_state.regime = "RGPS"
    st.session_state.aposentado = "não"
    st.session_state.idade = "menor 65 anos"
    st.session_state.dependentes = 0
    st.session_state.rend_texto = "0,00"


col1, col2 = st.columns([18, 2])
with col1:
    st.subheader("IRRF - Imposto de Renda Retido na Fonte (2026)")
with col2:
    st.button("Limpar", icon=":material/refresh:", on_click=resetar_campos, use_container_width=True)

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    regime = st.selectbox("Regime :", ["RGPS", "RPPS Federal"], key="regime")
with col2:
    aposentado = st.selectbox("Aposentado :", ["não", "sim"], key="aposentado")
with col3:
    idade = st.selectbox("Faixa etária :", ["menor 65 anos", "maior 65 anos"], key="idade")
with col4:
    dependente_quant = st.number_input(
        "Número dependentes:", min_value=0, max_value=30, value=0, step=1, key="dependentes"
    )
with col5:
    if "rend_texto" not in st.session_state:
        st.session_state.rend_texto = "0,00"

    def formatar_moeda():
        texto_usuario = st.session_state.rend_texto
        try:
            texto_limpo = texto_usuario.replace(".", "").replace(",", ".")
            valor_float = max(0.0, float(texto_limpo))
            texto_formatado = (
                f"{valor_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            )
            st.session_state.rend_texto = texto_formatado
        except ValueError:
            pass

    st.text_input("Rendimento bruto:", key="rend_texto", on_change=formatar_moeda)

    try:
        rend_bruto = max(
            0.0, float(st.session_state.rend_texto.replace(".", "").replace(",", "."))
        )
    except ValueError:
        rend_bruto = 0.0


def contrib_prev_rgps(rend_bruto: float) -> float:
    faixas = [
        (1621.00, 0.075, 0.0),
        (2902.84, 0.09, 24.32),
        (4354.27, 0.12, 111.40),
        (8475.55, 0.14, 198.49),
    ]
    teto_prev = 8475.55
    if aposentado == "sim" or rend_bruto <= 0:
        return 0.00
    if rend_bruto >= teto_prev:
        return round(teto_prev * 0.14 - 198.49, 2)

    contrib_prev = 0.0
    for limite, aliquota, deducao in faixas:
        if rend_bruto <= limite:
            contrib_prev = (rend_bruto * aliquota) - deducao
            break
    return round(contrib_prev, 2)


def contrib_prev_rpps(rend_bruto: float) -> float:
    if rend_bruto <= 0:
        return 0.00
    faixas = [
        (1621.00, 0.075, 0.0),
        (2902.84, 0.09, 24.32),
        (4354.27, 0.12, 111.40),
        (8475.55, 0.14, 198.49),
        (14514.30, 0.145, 240.86),
        (29028.57, 0.165, 531.15),
        (56606.73, 0.19, 1256.86),
        (float("inf"), 0.22, 2955.04),
    ]
    contrib_prev_teto = 988.09
    contrib_prev = 0.0
    for limite, aliquota, deducao in faixas:
        if rend_bruto <= limite:
            if aposentado == "sim":
                contrib_prev = max(0.00, (rend_bruto * aliquota) - deducao - contrib_prev_teto)
            else:
                contrib_prev = max(0.00, (rend_bruto * aliquota) - deducao)
            break
    return round(contrib_prev, 2)


contrib_prev = (
    contrib_prev_rgps(rend_bruto) if regime == "RGPS" else contrib_prev_rpps(rend_bruto)
)


def calc_irrf(rend_bruto: float) -> float:
    if rend_bruto <= 0:
        return 0.00

    faixas = [
        (2428.80, 0.0, 0.0),
        (2826.65, 0.075, 182.16),
        (3751.05, 0.15, 394.16),
        (4664.68, 0.225, 675.49),
        (float("inf"), 0.275, 908.73),
    ]

    if aposentado == "sim" and idade == "maior 65 anos":
        rend_tributavel = max(0.0, rend_bruto - 1903.98)
    else:
        rend_tributavel = rend_bruto

    desc_simpl = 607.20
    dependente_vr = 189.59
    deducoes_legais = contrib_prev + (dependente_vr * dependente_quant)

    base_calc = max(0.0, rend_tributavel - max(deducoes_legais, desc_simpl))

    irrf_bruto = 0.0
    for limite, aliquota, deducao in faixas:
        if base_calc <= limite:
            irrf_bruto = max(0.0, (base_calc * aliquota) - deducao)
            break

    if rend_tributavel <= 5000.00:
        reducao = 312.89
    elif rend_tributavel <= 7350.00:
        reducao = 978.62 - (0.133145 * rend_tributavel)
    else:
        reducao = 0.0

    irrf_final = max(0.0, irrf_bruto - reducao)
    return round(irrf_final, 2)


st.markdown("___")

deducao_dep = dependente_quant * 189.59
irrf_valor = calc_irrf(rend_bruto)
liquido = max(0.0, rend_bruto - contrib_prev - irrf_valor)

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Rendimento Bruto", formata_br(rend_bruto))
m2.metric("Previdência", formata_br(contrib_prev))
m3.metric("Dedução Dependentes", formata_br(deducao_dep))
m4.metric("IRRF Retido", formata_br(irrf_valor))
m5.metric("Rendimento Líquido", formata_br(liquido))

st.divider()
st.caption(
    """
    **Aviso Legal (Disclaimer):** Esta ferramenta tem caráter estritamente informativo e educacional, 
    baseada nas tabelas progressivas, limites previdenciários e regras de isenção/redução do IRRF vigentes em 2026 
    (Lei nº 15.270/2025 e normas da Receita Federal). Os resultados são simulações estimadas e podem variar conforme 
    rubricas específicas do seu contracheque (como verbas indenizatórias, previdência complementar, pensão alimentícia 
    ou dependentes). Esta calculadora não substitui o cálculo oficial do departamento pessoal/órgão pagador nem a 
    orientação de um contador. **Privacidade:** Nenhum dado financeiro inserido nesta página é armazenado ou compartilhado.
    """
)
