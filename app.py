import streamlit as st
import pandas as pd
import re
from youtube_transcript_api import YouTubeTranscriptApi
from google import genai
import json
from io import BytesIO

st.set_page_config(page_title="Monitor de Falas - Michel Saad", layout="wide")

st.title("🏛️ Monitor de Sessões Plenárias: Falas e Menções")
st.write("Cole o link da sessão da Câmara Municipal no YouTube para mapear automaticamente as intervenções e menções.")

# Configuração da Chave da API do Gemini
gemini_api_key = st.secrets.get("GEMINI_API_KEY", "")

if not gemini_api_key:
    gemini_api_key = st.sidebar.text_input("Gemini API Key", type="password", help="Insira sua chave gratuita do Google AI Studio.")

def extrair_video_id(url):
    padrao = r'(?:v=|\\/)([0-9A-Za-z_-]{11}).*'
    match = re.search(padrao, url)
    return match.group(1) if match else None

def segundos_para_hhmmss(segundos):
    segundos = int(segundos)
    h = segundos // 3600
    m = (segundos % 3600) // 60
    s = segundos % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

url_video = st.text_input("URL do Vídeo do YouTube:", placeholder="https://www.youtube.com/watch?v=haWDPmx5Kkw")

if st.button("Analisar Sessão", type="primary"):
    if not url_video:
        st.warning("Por favor, informe a URL do vídeo.")
    elif not gemini_api_key:
        st.error("Chave da API do Gemini não configurada.")
    else:
        video_id = extrair_video_id(url_video)
        if not video_id:
            st.error("URL do YouTube inválida.")
        else:
            with st.spinner("Extraindo transcrição do vídeo..."):
                try:
                    # Instancia e busca a transcrição
                    ytt_api = YouTubeTranscriptApi()
                    transcript = ytt_api.fetch(video_id, languages=['pt', 'pt-BR'])
                    
                    texto_com_tempo = ""
                    for item in transcript:
                        t_str = segundos_para_hhmmss(item.start)
                        texto_com_tempo += f"[{t_str}] (segundos: {int(item.start)}) {item.text}\n"
                except Exception as e:
                    st.error(f"Erro ao extrair transcrição: {e}")
                    st.stop()

            with st.spinner("Analisando intervenções e menções com IA..."):
                try:
                    client = genai.Client(api_key=gemini_api_key)
                    prompt = f"""
                    Você é um analista legislativo especialista em monitoramento político.
                    Analise a transcrição de sessão plenária abaixo.
                    Identifique todas as intervenções, discursos, apartes ou menções referentes ao vereador Michel Saad (ou falas dele).
                    Retorne estritamente um array JSON de objetos, onde cada objeto tem:
                    - "data": Data da sessão (infira pelo contexto/transcrição se houver, ou use formato DD/MM/AAAA)
                    - "quem_falou": Nome do orador ou quem fez a menção (ex: 'Michel Saad', 'Daniel Marques', 'Douglas Gomes')
                    - "tempo_segundos": número inteiro com o segundo inicial exato do vídeo
                    - "tempo_hhmmss": texto no formato 'HH:MM:SS'
                    - "assunto": resumo claro, conciso e objetivo da fala ou menção

                    Transcrição:
                    {texto_com_tempo[:90000]}
                    """

                    response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=prompt,
                        config={'response_mime_type': 'application/json'}
                    )
                    
                    dados = json.loads(response.text)
                    linhas = []
                    for item in dados:
                        seg = int(item.get('tempo_segundos', 0))
                        link_yt = f"https://www.youtube.com/watch?v={video_id}&t={seg}s"
                        linhas.append({
                            "Data": item.get("data", ""),
                            "Quem falou sobre o Michel": item.get("quem_falou", ""),
                            "Horário": item.get("tempo_hhmmss", "00:00:00"),
                            "Link do Vídeo": link_yt,
                            "Assunto": item.get("assunto", "")
                        })

                    df = pd.DataFrame(linhas)
                    st.success(f"{len(df)} menções/intervenções encontradas!")

                    # Exibição da Tabela Interativa
                    st.dataframe(
                        df,
                        column_config={
                            "Link do Vídeo": st.column_config.LinkColumn("Horário do vídeo", display_text=r"t=(\d+)s")
                        },
                        hide_index=True,
                        use_container_width=True
                    )

                    # Botões de Download
                    col1, col2 = st.columns(2)
                    with col1:
                        csv = df.to_csv(index=False).encode('utf-8')
                        st.download_button("📥 Baixar Planilha (.csv)", data=csv, file_name="falas_michel_saad.csv", mime="text/csv")

                    with col2:
                        output = BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            df.to_excel(writer, index=False, sheet_name='Falas Michel')
                        st.download_button("📥 Baixar Excel (.xlsx)", data=output.getvalue(), file_name="falas_michel_saad.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

                except Exception as e:
                    st.error(f"Erro no processamento da IA: {e}")