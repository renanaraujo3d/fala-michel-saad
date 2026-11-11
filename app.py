import streamlit as st
import pandas as pd
import re
import json
import os
import yt_dlp
from google import genai
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

def obter_transcricao_ytdlp(url_video):
    """Extrai legendas/transcrição usando yt-dlp para contornar bloqueios de IP na nuvem"""
    ydl_opts = {
        'skip_download': True,
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitleslangs': ['pt', 'pt-BR'],
        'outtmpl': 'temp_sub',
    }
    
    transcript_text = ""
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url_video, download=False)
            
        # Tenta extrair legendas automáticas ou manuais disponíveis no infodict
        subtitles = info.get('requested_subtitles') or info.get('automatic_captions', {}).get('pt')
        if not subtitles:
            # Tenta buscar por chaves em português
            for lang in ['pt', 'pt-BR', 'pt-en']:
                if lang in info.get('automatic_captions', {}):
                    subtitles = info['automatic_captions'][lang]
                    break
                    
        # Se encontrou dados de legendas estruturadas (json3 ou vtt)
        if subtitles:
            # Vamos baixar o arquivo de legenda real para processar
            ydl_opts_download = {
                'skip_download': True,
                'writesubtitles': True,
                'writeautomaticsub': True,
                'subtitleslangs': ['pt', 'pt-BR'],
                'subtitlesformat': 'vtt',
                'outtmpl': 'temp_sub',
            }
            with yt_dlp.YoutubeDL(ydl_opts_download) as ydl:
                ydl.download([url_video])
                
            # Procurar pelo arquivo .vtt baixado
            for arquivo in os.listdir('.'):
                if arquivo.startswith('temp_sub') and arquivo.endswith('.vtt'):
                    with open(arquivo, 'r', encoding='utf-8') as f:
                        transcript_text = f.read()
                    os.remove(arquivo) # Limpa o arquivo temporário
                    break
        
        if not transcript_text:
            # Fallback: Se não conseguiu o arquivo vtt, usa a descrição do vídeo ou metadados combinados
            description = info.get('description', '')
            title = info.get('title', '')
            transcript_text = f"Título: {title}\nDescrição:\n{description}"
            
        return transcript_text
    except Exception as e:
        raise Exception(f"Erro no yt-dlp: {str(e)}")

url_video = st.text_input("URL do Vídeo do YouTube:", placeholder="https://www.youtube.com/watch?v=haWDPmx5Kkw")

if st.button("Analisar Sessão", type="primary"):
    if not url_video:
        st.warning("Por favor, informe a URL do vídeo.")
    elif not gemini_api_key:
        st.error("Chave da API do Gemini não configurada.")
    else:
        video_id = extrair_video_id(url_url := url_video)
        if not video_id:
            st.error("URL do YouTube inválida.")
        else:
            with st.spinner("Extraindo transcrição e metadados com yt-dlp..."):
                try:
                    texto_com_tempo = obter_transcricao_ytdlp(url_video)
                except Exception as e:
                    st.error(f"Erro ao extrair transcrição: {e}")
                    st.stop()

            with st.spinner("Analisando intervenções e menções com IA..."):
                try:
                    client = genai.Client(api_key=gemini_api_key)
                    prompt = f"""
                    Você é um analista legislativo especialista em monitoramento político.
                    Analise o texto/transcrição da sessão plenária abaixo.
                    Identifique todas as intervenções, discursos, apartes ou menções referentes ao vereador Michel Saad (ou falas dele).
                    Retorne estritamente um array JSON de objetos, onde cada objeto tem:
                    - "data": Data da sessão (infira pelo contexto/transcrição se houver, ou use formato DD/MM/AAAA)
                    - "quem_falou": Nome do orador ou quem fez a menção (ex: 'Michel Saad', 'Daniel Marques', 'Douglas Gomes')
                    - "tempo_segundos": número inteiro com o segundo inicial aproximado ou exato do vídeo (se houver marcação, caso contrário estime com base no texto)
                    - "tempo_hhmmss": texto no formato 'HH:MM:SS'
                    - "assunto": resumo claro, conciso e objetivo da fala ou menção

                    Texto/Transcrição:
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
