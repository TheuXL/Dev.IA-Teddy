from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field

class ResumeFile(BaseModel):
    """Modelo para armazenar informações de um arquivo de currículo processado."""
    filename: str = Field(..., description="Nome do arquivo original.")
    content_type: str = Field(..., description="MIME type do arquivo.")
    text: Optional[str] = Field(None, description="Texto extraído do arquivo via OCR.")

class ResumeSummary(BaseModel):
    """Modelo para o resumo estruturado de um currículo."""
    file_name: str = Field(..., description="Nome do arquivo original.")
    summary: str = Field(..., description="Resumo textual do currículo.")
    name: Optional[str] = Field(None, description="Nome do candidato.")
    title: Optional[str] = Field(None, description="Cargo ou título profissional.")
    technologies: Optional[List[str]] = Field(None, description="Lista de tecnologias mencionadas.")
    experiences: Optional[List[str]] = Field(None, description="Lista de experiências profissionais.")
    education: Optional[List[str]] = Field(None, description="Lista de formações acadêmicas.")

class QueryMatch(BaseModel):
    """Modelo para o resultado da avaliação de um currículo em relação a uma consulta."""
    file_name: str = Field(..., description="Nome do arquivo original.")
    score: float = Field(..., description="Pontuação de compatibilidade (0.0 a 1.0).")
    justification: str = Field(..., description="Justificativa textual para a pontuação.")
    name: Optional[str] = Field(None, description="Nome do candidato, se disponível.")
    title: Optional[str] = Field(None, description="Cargo ou título profissional, se disponível.")

class SummariesResponse(BaseModel):
    """Modelo para a resposta da API no modo de sumarização (sem consulta)."""
    request_id: str = Field(..., description="ID único da requisição.")
    user_id: str = Field(..., description="ID do usuário que fez a requisição.")
    summaries: List[ResumeSummary] = Field(..., description="Lista de resumos dos currículos.")

class RankingResponse(BaseModel):
    """Modelo para a resposta da API no modo de ranking (com consulta)."""
    request_id: str = Field(..., description="ID único da requisição.")
    user_id: str = Field(..., description="ID do usuário que fez a requisição.")
    query: str = Field(..., description="Consulta original fornecida pelo usuário.")
    ranking: List[QueryMatch] = Field(..., description="Lista de currículos classificados por compatibilidade.")

class LogEntry(BaseModel):
    """Modelo para o registro de log de auditoria salvo no MongoDB."""
    request_id: str = Field(..., description="ID único da requisição.")
    user_id: str = Field(..., description="ID do usuário que fez a requisição.")
    timestamp: datetime = Field(..., description="Timestamp de quando a requisição foi recebida.")
    query: Optional[str] = Field(None, description="Consulta fornecida, se houver.")
    files_processed: List[str] = Field(..., description="Lista dos nomes dos arquivos processados.")
    result: Any = Field(None, description="O resultado completo da análise (sumários ou ranking).")
    error_message: Optional[str] = Field(None, description="Mensagem de erro, se alguma falha ocorreu.")

class AnalyzeRequest(BaseModel):
    """Modelo para os dados do formulário da requisição de análise."""
    request_id: Optional[str] = None
    user_id: Optional[str] = None
    query: Optional[str] = None 