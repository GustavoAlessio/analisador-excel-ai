import os
import json
import pandas as pd
from flask import Flask, request, render_template, jsonify, send_file
import requests
from werkzeug.utils import secure_filename
import tempfile
import uuid
import io
from fpdf import FPDF
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)

# Configurações
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv'}
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Criar pasta de uploads se não existir
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def analyze_excel_file(file_path):
    """Lê um arquivo Excel/CSV e retorna registros para análise de estoque."""
    results = []

    try:
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
            if not df.empty:
                df = df.copy()
                df['__planilha__'] = 'CSV'
                results.extend(df.to_dict(orient='records'))
        else:
            xls = pd.ExcelFile(file_path)
            for sheet_name in xls.sheet_names:
                df = pd.read_excel(file_path, sheet_name=sheet_name)
                if df.empty:
                    continue
                df = df.copy()
                df['__planilha__'] = sheet_name
                results.extend(df.to_dict(orient='records'))
    except Exception as e:
        print(f"Erro ao analisar arquivo: {str(e)}")

    return results


def build_fallback_analysis(file_data):
    """Gera uma análise simples quando a API da OpenAI não está disponível."""
    if not file_data:
        return {
            "analysis": "Nenhum dado válido foi encontrado no arquivo enviado."
        }

    df = pd.DataFrame(file_data)
    columns = [str(col) for col in df.columns]
    normalized_columns = [col.lower() for col in columns]

    required_fields = {
        "sku": ["sku"],
        "mlb": ["mlb", "id anuncio", "id anúncio"],
        "titulo": ["titulo", "título"],
        "estoque": ["estoque", "quantidade", "qtd"],
        "estoque_minimo": ["estoque minimo", "mínimo", "min"],
        "status": ["status", "ativo", "pausado"],
    }

    missing = []
    for field, keywords in required_fields.items():
        if not any(any(keyword in col for keyword in keywords) for col in normalized_columns):
            missing.append(field)

    analysis_lines = [
        "Resumo rápido (modo offline):",
        f"- Registros carregados: {len(df)}",
        f"- Colunas detectadas: {', '.join(columns)}",
    ]

    if missing:
        analysis_lines.append("\n⚠️ Dados faltando para análise completa:")
        analysis_lines.extend([f"- {field}" for field in missing])
        analysis_lines.append("\nEnvie um arquivo com esses campos ou informe-os manualmente.")

    return {"analysis": "\n".join(analysis_lines)}

def analyze_with_openai(file_data):
    """Usa a API da OpenAI para analisar dados de estoque para Mercado Livre."""
    try:
        prompt = f"""
Você é um assistente especialista em gestão de estoque para e-commerce no Mercado Livre.

Objetivo: analisar dados de estoque e anúncios, apontar riscos de ruptura/pausa, tratar kits,
priorizar reposições e sugerir ações para maximizar vendas.

Regras:
- Nunca sugerir venda sem estoque.
- Priorizar anúncios ativos, premium, alta rotatividade e melhor conversão.
- Sempre destacar alertas críticos com ícones: ⚠️, 🔴, 🟡, 🟢.
- Se algum dado não estiver disponível, liste perguntas objetivas em "Perguntas Pendentes".

Dados de entrada (amostra):
{json.dumps(file_data[:200], ensure_ascii=False, indent=2)}

Retorne um JSON estritamente neste formato:
{{
  "analysis": "Texto em português com seções: Alertas Críticos, Prioridades, Reposição Recomendada, Kits/Combos, Observações. Use listas e tabelas em texto quando fizer sentido.",
  "questions": ["Pergunta objetiva 1", "Pergunta objetiva 2"]
}}
"""

        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o",
                "messages": [
                    {
                        "role": "system",
                        "content": "Você é um assistente especialista em gestão de estoque para Mercado Livre."
                    },
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3
            }
        )

        if response.status_code == 200:
            result = response.json()
            ai_response = result['choices'][0]['message']['content']

            try:
                import re
                json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group(0))
                return json.loads(ai_response)
            except Exception as e:
                print(f"Erro ao processar resposta da IA: {str(e)}")
                return {"analysis": ai_response.strip(), "questions": []}

        print(f"Erro na API da OpenAI: {response.status_code} - {response.text}")
        return build_fallback_analysis(file_data)
    except Exception as e:
        print(f"Erro ao analisar com OpenAI: {str(e)}")
        return build_fallback_analysis(file_data)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'Nenhum arquivo enviado'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'Nenhum arquivo selecionado'}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        # Analisar o arquivo
        records = analyze_excel_file(file_path)

        if OPENAI_API_KEY:
            analysis_result = analyze_with_openai(records)
        else:
            analysis_result = build_fallback_analysis(records)

        temp_file = os.path.join(app.config['UPLOAD_FOLDER'], f"resultados_{uuid.uuid4()}.json")
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(analysis_result, f, ensure_ascii=False, indent=4)

        return jsonify({
            'success': True,
            'message': f'Arquivo {filename} analisado com sucesso',
            'analysis': analysis_result.get('analysis', ''),
            'questions': analysis_result.get('questions', []),
            'record_count': len(records),
            'download_url': f'/download/{os.path.basename(temp_file)}'
        })
    
    return jsonify({'error': 'Tipo de arquivo não permitido'}), 400

@app.route('/download/<filename>')
def download_file(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    if not os.path.exists(file_path):
        return jsonify({'error': 'Arquivo não encontrado'}), 404

    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="Relatório de Gestão de Estoque (Mercado Livre)", ln=True, align='C')
    pdf.ln(10)

    analysis_text = data.get('analysis', 'Sem análise disponível.')
    for line in analysis_text.splitlines():
        pdf.multi_cell(0, 8, txt=line)

    questions = data.get('questions', [])
    if questions:
        pdf.ln(4)
        pdf.multi_cell(0, 8, txt="Perguntas Pendentes:")
        for question in questions:
            pdf.multi_cell(0, 8, txt=f"- {question}")

    # ✅ Corrigido: gerar PDF como string e converter para BytesIO
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    pdf_output = io.BytesIO(pdf_bytes)

    return send_file(
        pdf_output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name='relatorio_clientes.pdf'
    )
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
