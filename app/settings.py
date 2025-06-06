import os
from dotenv import load_dotenv

# Carrega as variáveis de ambiente de um arquivo .env, se ele existir.
load_dotenv()

class Settings:
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY")
    GEMINI_API_URL: str = os.getenv(
        "GEMINI_API_URL",
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent"
    )
    MONGODB_URL: str = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    MONGODB_DB: str = os.getenv("MONGODB_DB", "ia_teddy")
    
    # Valores padrão para identificação de auditoria.
    DEFAULT_REQUEST_ID: str = "default-request-id"
    DEFAULT_USER_ID: str = "default-user-id"

settings = Settings() 