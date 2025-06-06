import os
import requests
import pymongo
from time import sleep
import uuid
from dotenv import load_dotenv

# Carrega as variáveis de ambiente do arquivo .env para os testes.
load_dotenv()

# ==============================================================================
# CONFIGURAÇÕES DE TESTE
# ==============================================================================
API_URL = "http://localhost:8000/analyze"
DOCS_URL = "http://localhost:8000/docs"
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MONGO_DB = "ia_teddy"
COLLECTION_NAME = "logs"
CV_DIR = os.path.join(os.path.dirname(__file__), "recursos")
# Timeout elevado para requisições que dependem de uma API externa (Gemini).
LLM_REQUEST_TIMEOUT = 180  # 3 minutos

# ==============================================================================
# FUNÇÕES DE TESTE DE PRÉ-REQUISITOS
# ==============================================================================

def test_verificar_variaveis_ambiente():
    """Verifica se a variável de ambiente essencial (GEMINI_API_KEY) está configurada."""
    print("\n🔑 Verificando variáveis de ambiente...")
    assert GEMINI_API_KEY, "A variável de ambiente GEMINI_API_KEY não está configurada."
    print("✅ GEMINI_API_KEY encontrada.")

def test_verificar_cvs():
    """Verifica se os arquivos de currículo para os testes existem no diretório de recursos."""
    print("\n📋 Verificando arquivos de CV...")
    global cv_files_to_test
    cv_files_to_test = [os.path.join(CV_DIR, f) for f in os.listdir(CV_DIR) if f.endswith(".pdf")]
    
    assert cv_files_to_test, "Nenhum arquivo de CV (.pdf) encontrado para teste."
    
    for cv in cv_files_to_test:
        assert os.path.exists(cv), f"Arquivo de CV não encontrado: {cv}"
        print(f"  - ✅ {os.path.basename(cv)} encontrado ({os.path.getsize(cv)} bytes)")
        
    print(f"✅ {len(cv_files_to_test)} CVs disponíveis para testes.")

def test_fastapi_online():
    """Verifica se a API FastAPI está respondendo."""
    print("\n🌐 Verificando se a API FastAPI está online...")
    try:
        response = requests.get(DOCS_URL, timeout=10)
        response.raise_for_status()
        print("✅ FastAPI está online.")
    except requests.RequestException as e:
        print(f"❌ FALHA: Não foi possível conectar à API em {DOCS_URL}. Verifique se os contêineres Docker estão em execução. Erro: {e}")
        exit(1)

def test_conexao_mongodb():
    """Testa a conexão com o MongoDB inserindo e deletando um documento."""
    print("\n💾 Verificando conexão com o MongoDB...")
    try:
        client = pymongo.MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
        db = client[MONGO_DB]
        collection = db[COLLECTION_NAME]
        
        client.admin.command('ping')
        
        test_doc = {"_id": "test_conexao", "status": "ok"}
        collection.insert_one(test_doc)
        collection.delete_one({"_id": "test_conexao"})
        
        print("✅ MongoDB conectado e operando corretamente.")
        client.close()
    except Exception as e:
        print(f"❌ FALHA na conexão com o MongoDB: {e}")
        exit(1)

# ==============================================================================
# TESTES DE FLUXO PRINCIPAL (E2E)
# ==============================================================================

def test_fluxo_completo_cv_sumario():
    """
    Testa o fluxo completo de análise de múltiplos CVs sem uma query (modo sumário).
    Verifica se a API retorna um resumo para cada CV.
    """
    print("\n📄 TESTE MODO SUMÁRIO: Testando fluxo sem query...")
    
    files_to_send = [("files", (os.path.basename(p), open(p, "rb"), "application/pdf")) for p in cv_files_to_test]

    payload = {"request_id": str(uuid.uuid4()), "user_id": "test_user_summary"}

    print(f"🔍 Enviando {len(files_to_send)} CVs para a API (Timeout: {LLM_REQUEST_TIMEOUT}s)...")
    
    try:
        response = requests.post(API_URL, files=files_to_send, data=payload, timeout=LLM_REQUEST_TIMEOUT)

        for _, f_tuple in files_to_send:
            f_tuple[1].close()

        assert response.status_code == 200, f"API retornou status {response.status_code}. Resposta: {response.text}"
        response_json = response.json()
        
        assert "request_id" in response_json
        assert "summaries" in response_json
        assert isinstance(response_json["summaries"], list)
        assert len(response_json["summaries"]) == len(cv_files_to_test), "A API não retornou um resultado para cada CV enviado."
        
        print("✅ Resposta da API recebida com sucesso.")
        
        for result in response_json["summaries"]:
            assert "file_name" in result
            assert "summary" in result and isinstance(result["summary"], str) and len(result["summary"]) > 10
            print(f"  - Sumário para '{result['file_name']}' validado.")

        print("✅ Teste MODO SUMÁRIO concluído com sucesso!")

    except requests.RequestException as e:
        print(f"❌ FALHA NO TESTE MODO SUMÁRIO: {e}")
        assert False, "O teste de sumário falhou devido a um erro de requisição."


def test_fluxo_completo_cv_ranking():
    """
    Testa o fluxo completo de análise de múltiplos CVs com uma query (modo ranking).
    Verifica se a API retorna um ranking de CVs com pontuação e justificativa.
    """
    print("\n🏆 TESTE MODO RANKING: Testando fluxo com query...")

    files_to_send = [("files", (os.path.basename(p), open(p, "rb"), "application/pdf")) for p in cv_files_to_test]
    
    payload = {
        "query": "Qual candidato tem mais experiência com Python e projetos de dados?",
        "request_id": str(uuid.uuid4()),
        "user_id": "test_user_ranking"
    }

    print(f"🔍 Enviando {len(files_to_send)} CVs com query para a API (Timeout: {LLM_REQUEST_TIMEOUT}s)...")

    try:
        response = requests.post(API_URL, files=files_to_send, data=payload, timeout=LLM_REQUEST_TIMEOUT)

        for _, f_tuple in files_to_send:
            f_tuple[1].close()

        assert response.status_code == 200, f"API retornou status {response.status_code}. Resposta: {response.text}"
        response_json = response.json()
        
        assert "request_id" in response_json
        assert "ranking" in response_json
        assert isinstance(response_json["ranking"], list)
        assert len(response_json["ranking"]) == len(cv_files_to_test), "A API não retornou um resultado para cada CV enviado."
        
        print("✅ Resposta da API recebida com sucesso.")
        
        for result in response_json["ranking"]:
            assert "file_name" in result
            assert "score" in result and isinstance(result["score"], (int, float))
            assert "justification" in result and isinstance(result["justification"], str) and len(result["justification"]) > 10
            print(f"  - Ranking para '{result['file_name']}' (Score: {result['score']}) validado.")

        print("✅ Teste MODO RANKING concluído com sucesso!")

    except requests.RequestException as e:
        print(f"❌ FALHA NO TESTE MODO RANKING: {e}")
        assert False, "O teste de ranking falhou devido a um erro de requisição."

# ==============================================================================
# EXECUTOR PRINCIPAL DOS TESTES
# ==============================================================================

def run_all_tests():
    """Executa todos os testes de integração em sequência."""
    print("\n🚀 INICIANDO TESTES DE INTEGRAÇÃO")
    print("==================================================")
    
    try:
        # Testes de pré-requisitos
        test_verificar_variaveis_ambiente()
        test_verificar_cvs()
        test_fastapi_online()
        test_conexao_mongodb()
        
        # Testes de fluxo principal da API
        test_fluxo_completo_cv_sumario()
        test_fluxo_completo_cv_ranking()

        print("\n==================================================")
        print("🎉 SUCESSO! Todos os testes de integração passaram.")
        print("==================================================")

    except AssertionError as e:
        print(f"\n❌ FALHA NOS TESTES: {e}")
        print("==================================================")
        exit(1)
    except Exception as e:
        print(f"\n❌ ERRO INESPERADO DURANTE OS TESTES: {e}")
        print("==================================================")
        exit(1)


if __name__ == "__main__":
    print("Aguardando 10 segundos para garantir que os serviços estejam prontos...")
    sleep(10)
    run_all_tests()
