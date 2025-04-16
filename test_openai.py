import os
import json
import requests
from dotenv import load_dotenv
load_dotenv()

# Configuração da API 
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

def test_openai_integration():
    """
    Testa a integração com a API da OpenAI
    """
    print("Testando integração com a API da OpenAI...")
    
    try:
        # Dados de teste
        test_data = [
            {
                "nome": "João Silva",
                "cpf": "123.456.789-00",
                "quantidade": 3,
                "produto": "Notebook Dell"
            },
            {
                "nome": "Maria Oliveira",
                "cpf": "987.654.321-00",
                "quantidade": 1,
                "produto": "Smartphone Samsung"
            },
            {
                "nome": "Carlos Santos",
                "cpf": "111.222.333-44",
                "quantidade": 5,
                "produto": "Monitor LG"
            }
        ]
        
        # Preparar prompt para a API
        prompt = f"""
        Analise os seguintes dados de um arquivo Excel e identifique clientes com quantidade maior que 2.
        Para cada cliente identificado, extraia o nome e CPF (se disponível).
        
        Dados:
        {json.dumps(test_data, ensure_ascii=False, indent=2)}
        
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
            
            print("\nResposta da API OpenAI:")
            print(ai_response)
            
            # Tentar extrair o JSON da resposta
            try:
                # Tentar encontrar o JSON na resposta
                import re
                json_match = re.search(r'\[.*\]', ai_response, re.DOTALL)
                if json_match:
                    ai_data = json.loads(json_match.group(0))
                    print("\nDados extraídos:")
                    print(json.dumps(ai_data, ensure_ascii=False, indent=2))
                else:
                    ai_data = json.loads(ai_response)
                    print("\nDados extraídos:")
                    print(json.dumps(ai_data, ensure_ascii=False, indent=2))
                
                print("\nTeste concluído com sucesso!")
                return True
            except Exception as e:
                print(f"\nErro ao processar resposta da IA: {str(e)}")
                print("Resposta original:", ai_response)
                return False
        else:
            print(f"\nErro na API da OpenAI: {response.status_code}")
            print(response.text)
            return False
    
    except Exception as e:
        print(f"\nErro ao testar integração com OpenAI: {str(e)}")
        return False

if __name__ == "__main__":
    test_openai_integration()
