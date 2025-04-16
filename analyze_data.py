import pandas as pd
import os
import json
import re

def analyze_data_for_quantity(file_path):
    """
    Função específica para analisar arquivos Excel e identificar clientes com quantidade > 2
    
    Args:
        file_path (str): Caminho para o arquivo Excel ou CSV
        
    Returns:
        list: Lista de dicionários com informações dos clientes que têm quantidade > 2
    """
    results = []
    
    try:
        # Determinar o tipo de arquivo
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
            process_dataframe(df, "CSV", results)
        else:  # xlsx ou xls
            # Obter todas as planilhas
            xls = pd.ExcelFile(file_path)
            
            # Para cada planilha no arquivo
            for sheet_name in xls.sheet_names:
                df = pd.read_excel(file_path, sheet_name=sheet_name)
                
                if df.empty:
                    continue
                
                process_dataframe(df, sheet_name, results)
    
    except Exception as e:
        print(f"Erro ao analisar arquivo: {str(e)}")
    
    return results

def process_dataframe(df, sheet_name, results):
    """
    Processa um DataFrame para encontrar clientes com quantidade > 2
    
    Args:
        df (DataFrame): DataFrame pandas a ser analisado
        sheet_name (str): Nome da planilha ou origem do DataFrame
        results (list): Lista para armazenar os resultados
    """
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
    
    # Se encontrou colunas de quantidade
    for qty_col in quantity_cols:
        # Filtrar registros com quantidade > 2
        try:
            # Converter coluna para numérico, tratando erros como NaN
            df[f'{qty_col}_numeric'] = pd.to_numeric(df[qty_col], errors='coerce')
            
            # Filtrar registros com quantidade > 2
            filtered_df = df[df[f'{qty_col}_numeric'] > 2]
            
            if not filtered_df.empty:
                for _, row in filtered_df.iterrows():
                    client_info = {}
                    
                    # Obter nome do cliente
                    if client_cols:
                        for client_col in client_cols:
                            if pd.notna(row.get(client_col)):
                                client_info['nome'] = str(row[client_col])
                                break
                    else:
                        # Se não encontrou coluna específica de cliente, procurar por padrões em todas as colunas
                        for col in df.columns:
                            if isinstance(row.get(col), str) and len(str(row[col])) > 3:
                                # Verificar se parece um nome (primeira letra maiúscula, sem números)
                                if re.match(r'^[A-Z][a-zA-Z\s]+$', str(row[col])):
                                    client_info['nome'] = str(row[col])
                                    break
                    
                    # Obter CPF se disponível
                    if cpf_cols:
                        for cpf_col in cpf_cols:
                            if pd.notna(row.get(cpf_col)):
                                client_info['cpf'] = str(row[cpf_col])
                                break
                    else:
                        # Se não encontrou coluna específica de CPF, procurar por padrões em todas as colunas
                        for col in df.columns:
                            if isinstance(row.get(col), str):
                                # Verificar se parece um CPF (formato XXX.XXX.XXX-XX ou números)
                                if re.match(r'^\d{3}\.?\d{3}\.?\d{3}-?\d{2}$', str(row[col])):
                                    client_info['cpf'] = str(row[col])
                                    break
                    
                    # Adicionar quantidade
                    client_info['quantidade'] = float(row[f'{qty_col}_numeric'])
                    
                    # Adicionar nome da planilha e coluna
                    client_info['planilha'] = sheet_name
                    client_info['coluna_quantidade'] = qty_col
                    
                    # Adicionar outras informações disponíveis que podem ser úteis
                    for col in df.columns:
                        if col not in client_info and col != f'{qty_col}_numeric' and pd.notna(row.get(col)):
                            # Adicionar apenas se for um valor válido
                            if isinstance(row[col], (str, int, float)) and str(row[col]).strip():
                                client_info[str(col)] = str(row[col])
                    
                    # Só adicionar se tiver pelo menos nome ou CPF
                    if 'nome' in client_info or 'cpf' in client_info:
                        results.append(client_info)
        
        except Exception as e:
            print(f"Erro ao processar coluna {qty_col}: {str(e)}")

# Função para testar a análise com os arquivos de exemplo
def test_analysis():
    upload_dir = '/home/ubuntu/upload'
    all_results = []
    
    for filename in os.listdir(upload_dir):
        file_path = os.path.join(upload_dir, filename)
        if os.path.isfile(file_path) and (filename.endswith('.xlsx') or filename.endswith('.xls') or filename.endswith('.csv')):
            print(f"\nAnalisando arquivo: {filename}")
            results = analyze_data_for_quantity(file_path)
            
            if results:
                print(f"Encontrados {len(results)} clientes com quantidade > 2")
                all_results.extend(results)
            else:
                print("Nenhum cliente com quantidade > 2 encontrado")
    
    # Salvar resultados em um arquivo JSON
    if all_results:
        output_file = '/home/ubuntu/analysis_results.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_results, f, ensure_ascii=False, indent=4)
        
        print(f"\nResultados salvos em: {output_file}")
        print(f"Total de {len(all_results)} clientes encontrados com quantidade > 2")
    else:
        print("\nNenhum cliente com quantidade > 2 encontrado em todos os arquivos")

if __name__ == "__main__":
    test_analysis()
