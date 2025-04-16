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
    """Analisa um arquivo Excel para encontrar clientes com quantidade > 2"""
    results = []
    
    try:
        # Determinar o tipo de arquivo
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
        else:  # xlsx ou xls
            # Obter todas as planilhas
            xls = pd.ExcelFile(file_path)
            
            # Para cada planilha no arquivo
            for sheet_name in xls.sheet_names:
                df = pd.read_excel(file_path, sheet_name=sheet_name)
                
                if df.empty:
                    continue
                
                # Procurar colunas que podem conter informações de quantidade
                quantity_cols = [col for col in df.columns if 
                                any(term in str(col).lower() for term in ['quant', 'qtd', 'unid'])]
                
                # Se não encontrar colunas específicas, procurar por colunas numéricas
                if not quantity_cols:
                    for col in df.columns:
                        if pd.api.types.is_numeric_dtype(df[col].dtype):
                            quantity_cols.append(col)
                
                # Procurar colunas que podem conter informações de cliente
                client_cols = [col for col in df.columns if 
                              any(term in str(col).lower() for term in ['client', 'nome', 'customer', 'comprador', 'destinatário', 'usuário'])]
                
                # Procurar colunas que podem conter CPF
                cpf_cols = [col for col in df.columns if 
                           any(term in str(col).lower() for term in ['cpf', 'documento', 'doc'])]
                
                # Se encontrou colunas de quantidade e cliente
                if quantity_cols and client_cols:
                    for qty_col in quantity_cols:
                        # Filtrar registros com quantidade > 2
                        try:
                            filtered_df = df[pd.to_numeric(df[qty_col], errors='coerce') > 2]
                            
                            if not filtered_df.empty:
                                for _, row in filtered_df.iterrows():
                                    client_info = {}
                                    
                                    # Obter nome do cliente
                                    for client_col in client_cols:
                                        if pd.notna(row.get(client_col)):
                                            client_info['nome'] = str(row[client_col])
                                            break
                                    
                                    # Obter CPF se disponível
                                    for cpf_col in cpf_cols:
                                        if pd.notna(row.get(cpf_col)):
                                            client_info['cpf'] = str(row[cpf_col])
                                            break
                                    
                                    # Adicionar quantidade
                                    client_info['quantidade'] = float(row[qty_col])
                                    
                                    # Adicionar nome da planilha e coluna
                                    client_info['planilha'] = sheet_name
                                    client_info['coluna_quantidade'] = qty_col
                                    
                                    # Adicionar outras informações disponíveis
                                    for col in df.columns:
                                        if col not in client_info and pd.notna(row.get(col)):
                                            client_info[str(col)] = str(row[col])
                                    
                                    results.append(client_info)
                        except Exception as e:
                            print(f"Erro ao processar coluna {qty_col}: {str(e)}")
    
    except Exception as e:
        print(f"Erro ao analisar arquivo: {str(e)}")
    
    return results

def analyze_with_openai(file_data):
    """Usa a API da OpenAI para analisar os dados do arquivo"""
    try:
        # Preparar os dados para envio à API
        prompt = f"""
        Analise os seguintes dados de um arquivo Excel e identifique clientes com quantidade maior que 2.
        Para cada cliente identificado, extraia o nome e CPF (se disponível).
        
        Dados:
        {json.dumps(file_data, ensure_ascii=False, indent=2)}
        
        Retorne apenas os clientes com quantidade maior que 2 no formato JSON:
        [
            {{"nome": "Nome do Cliente", "cpf": "CPF se disponível", "quantidade": valor}}
        ]
        """
        
        # Chamar a API da OpenAI
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o",
                "messages": [
                    {"role": "system", "content": "Você é um assistente especializado em análise de dados de arquivos Excel."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3
            }
        )
        
        # Verificar resposta
        if response.status_code == 200:
            result = response.json()
            ai_response = result['choices'][0]['message']['content']
            
            # Extrair o JSON da resposta
            try:
                # Tentar encontrar o JSON na resposta
                import re
                json_match = re.search(r'\[.*\]', ai_response, re.DOTALL)
                if json_match:
                    ai_data = json.loads(json_match.group(0))
                else:
                    ai_data = json.loads(ai_response)
                return ai_data
            except Exception as e:
                print(f"Erro ao processar resposta da IA: {str(e)}")
                return []
        else:
            print(f"Erro na API da OpenAI: {response.status_code} - {response.text}")
            return []
    
    except Exception as e:
        print(f"Erro ao analisar com OpenAI: {str(e)}")
        return []

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
        results = analyze_excel_file(file_path)
        
        # Se tiver poucos resultados, usar a API da OpenAI para análise adicional
        if len(results) < 5:
            # Converter para formato que pode ser enviado para a API
            sample_data = []
            try:
                if file_path.endswith('.csv'):
                    df = pd.read_csv(file_path)
                    sample_data = df.head(50).to_dict(orient='records')
                else:
                    xls = pd.ExcelFile(file_path)
                    for sheet_name in xls.sheet_names:
                        df = pd.read_excel(file_path, sheet_name=sheet_name)
                        if not df.empty:
                            sample_data.extend(df.head(50).to_dict(orient='records'))
                
                # Analisar com OpenAI
                ai_results = analyze_with_openai(sample_data)
                
                # Mesclar resultados
                for ai_result in ai_results:
                    if ai_result not in results:
                        results.append(ai_result)
            except Exception as e:
                print(f"Erro ao analisar com IA: {str(e)}")
        
        # Salvar resultados em um arquivo temporário para download
        temp_file = os.path.join(app.config['UPLOAD_FOLDER'], f"resultados_{uuid.uuid4()}.json")
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=4)
        
        return jsonify({
            'success': True,
            'message': f'Arquivo {filename} analisado com sucesso',
            'results': results,
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
    pdf.cell(200, 10, txt="Relatório de Clientes com Quantidade > 2", ln=True, align='C')
    pdf.ln(10)

    for cliente in data:
        linha = f"Nome: {cliente.get('nome', 'N/A')} | CPF: {cliente.get('cpf', 'N/A')} | Quantidade: {cliente.get('quantidade', 'N/A')}"
        pdf.multi_cell(0, 10, txt=linha)
        pdf.ln(2)

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
