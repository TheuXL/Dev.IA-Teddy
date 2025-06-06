import logging
from pymongo import MongoClient
from datetime import datetime
from .models import LogEntry
from .settings import settings

logger = logging.getLogger(__name__)

# Variáveis globais para a conexão com o MongoDB.
mongo_client = None
db = None

def connect_to_mongo():
    """Conecta-se ao MongoDB usando as configurações da aplicação."""
    global mongo_client, db
    try:
        mongo_client = MongoClient(settings.MONGODB_URL, serverSelectionTimeoutMS=5000)
        db = mongo_client[settings.MONGODB_DB]
        
        # Testa a conexão para garantir que o servidor está acessível.
        mongo_client.admin.command('ping')
        logger.info(f"Conexão com o MongoDB estabelecida com sucesso: {settings.MONGODB_DB}")
        return True
    except Exception as e:
        logger.error(f"Não foi possível conectar ao MongoDB: {e}", exc_info=True)
        return False

def close_mongo_connection():
    """Fecha a conexão com o MongoDB."""
    global mongo_client
    if mongo_client:
        mongo_client.close()
        logger.info("Conexão com o MongoDB fechada.")

def get_db():
    """Retorna a instância do banco de dados, estabelecendo a conexão se necessário."""
    if db is None or mongo_client is None:
        if not connect_to_mongo():
             raise RuntimeError("Falha crítica ao conectar com o MongoDB.")
    return db

async def save_log(log_entry: LogEntry):
    """
    Salva um registro de log no MongoDB.

    A função é assíncrona para se manter consistente com o restante da API,
    embora a operação de inserção do PyMongo seja bloqueante.
    """
    database = get_db()
    
    try:
        # Converte o objeto Pydantic para um dicionário compatível com o MongoDB.
        log_dict = log_entry.model_dump()
        
        # Garante a serialização de tipos de dados complexos para o formato JSON.
        if isinstance(log_dict.get('timestamp'), datetime):
            log_dict['timestamp'] = log_dict['timestamp'].isoformat()
            
        if log_dict.get('result') is not None:
            if isinstance(log_dict['result'], list) and all(hasattr(item, 'model_dump') for item in log_dict['result']):
                log_dict['result'] = [item.model_dump() for item in log_dict['result']]
        
        # Insere o log na coleção 'logs'.
        database.logs.insert_one(log_dict)
        logger.info(f"Log de auditoria salvo com sucesso: {log_entry.request_id}")
        return True
    except Exception as e:
        logger.error(f"Erro ao salvar log no MongoDB: {e}", exc_info=True)
        return False

# Example of how to ensure connection is established at startup if needed by main app
# connect_to_mongo() # This could be called when the FastAPI app starts up. 