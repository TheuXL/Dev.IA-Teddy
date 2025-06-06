from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Depends
from fastapi.responses import JSONResponse, RedirectResponse
from typing import List, Optional, Any, Dict, Union
import logging
import uuid
from datetime import datetime
from contextlib import asynccontextmanager
import asyncio
import json

from . import ocr, llm, storage
from .settings import settings
from .models import (
    ResumeSummary, QueryMatch, LogEntry, 
    SummariesResponse, RankingResponse, ResumeFile
)

# Configuração centralizada do logging.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gerencia o ciclo de vida da aplicação.
    Executa a lógica de inicialização (startup) e finalização (shutdown).
    """
    # Lógica de Startup
    logger.info("Iniciando a aplicação...")
    storage.connect_to_mongo()
    if not settings.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY não está configurada. As funcionalidades de IA podem não operar.")
    else:
        logger.info("Chave da API do Gemini configurada com sucesso.")
    if ocr.reader is None:
        logger.warning("Leitor OCR não inicializado. A extração de texto pode falhar.")
    else:
        logger.info("Leitor OCR inicializado com sucesso.")
    
    yield
    
    # Lógica de Shutdown
    logger.info("Finalizando a aplicação...")
    storage.close_mongo_connection()

app = FastAPI(
    title="IA-Teddy Resume Analyzer",
    description="API para análise inteligente de currículos usando OCR e Gemini.",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/", include_in_schema=False)
async def root():
    """Redireciona para a documentação da API em /docs."""
    return RedirectResponse(url="/docs")

@app.post(
    "/analyze", 
    response_model=Union[SummariesResponse, RankingResponse],
    summary="Analisa e classifica currículos",
    tags=["Resume Analysis"],
    responses={
        200: {
            "description": "Análise concluída com sucesso. O formato da resposta depende da presença do campo 'query'.",
            "content": {
                "application/json": {
                    "examples": {
                        "Ranking (com query)": {
                            "summary": "Resposta quando uma 'query' é fornecida.",
                            "value": {
                                "request_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
                                "user_id": "recruiter_fabio",
                                "query": "Qual candidato tem mais experiência com Python e projetos de dados?",
                                "ranking": [
                                    {
                                        "file_name": "cv_data_scientist.pdf",
                                        "score": 0.9,
                                        "justification": "O candidato possui vasta experiência com Python em projetos de análise de dados e machine learning, atendendo perfeitamente aos requisitos.",
                                        "name": "Maria Oliveira",
                                        "title": "Cientista de Dados Sênior"
                                    },
                                    {
                                        "file_name": "cv_backend_dev.pdf",
                                        "score": 0.7,
                                        "justification": "O candidato tem forte experiência em Python para desenvolvimento backend, mas menos foco em análise de dados.",
                                        "name": "João da Silva",
                                        "title": "Desenvolvedor Backend"
                                    }
                                ]
                            }
                        },
                        "Sumarização (sem query)": {
                            "summary": "Resposta quando nenhuma 'query' é fornecida.",
                            "value": {
                                "request_id": "f0e9d8c7-b6a5-4321-fedc-ba9876543210",
                                "user_id": "recruiter_fabio",
                                "summaries": [
                                    {
                                        "file_name": "cv_data_scientist.pdf",
                                        "summary": "Maria Oliveira é uma Cientista de Dados Sênior com 8 anos de experiência em Python, SQL, e plataformas de nuvem como AWS e GCP.",
                                        "name": "Maria Oliveira",
                                        "title": "Cientista de Dados Sênior",
                                        "technologies": ["Python", "SQL", "Pandas", "Scikit-learn", "AWS", "GCP"],
                                        "experiences": ["Cientista de Dados na Empresa X (2018-Presente)", "Analista de Dados na Empresa Y (2015-2018)"],
                                        "education": ["Mestrado em Ciência da Computação - Unicamp (2015)"]
                                    }
                                ]
                            }
                        }
                    }
                }
            }
        },
        400: {
            "description": "Erro na requisição do cliente, como a falta de arquivos.",
            "content": {"application/json": {"example": {"detail": "Nenhum arquivo foi enviado. Por favor, faça upload de pelo menos um currículo."}}}
        },
        422: {
            "description": "Erro de validação de entidade, um campo obrigatório está faltando.",
            "content": {"application/json": {"example": {"detail": [{"loc": ["body", "files"], "msg": "field required", "type": "value_error.missing"}]}}}
        },
        500: {
            "description": "Erro interno do servidor durante o processamento.",
            "content": {"application/json": {"example": {"detail": "Ocorreu um erro ao processar a requisição."}}}
        }
    }
)
async def analyze_resumes(
    files: List[UploadFile] = File(..., description="Um ou mais arquivos de currículo (PDF, JPG, PNG)."),
    query: Optional[str] = Form(None, description="Consulta para classificar os currículos (ativa o **Modo Ranking**). Ex: 'Desenvolvedor Python com experiência em AWS'"),
    request_id: Optional[str] = Form(None, description="ID opcional para rastrear a solicitação (UUID). Se omitido, será gerado automaticamente."),
    user_id: Optional[str] = Form("anonymous", description="ID do usuário para fins de auditoria.")
):
    """
    Este endpoint é o coração da aplicação e opera em dois modos distintos:

    ---

    ### 1. Modo Ranking (com `query`)
    Quando você fornece uma **query** (uma pergunta ou descrição de vaga), a API avalia cada currículo em relação a ela, retornando uma lista ordenada por pontuação (`score`).
    - **Use para**: Encontrar os melhores candidatos para uma vaga específica.
    - **Exemplo de Query**: "Qual candidato tem mais experiência com Python e projetos de dados?"

    ---

    ### 2. Modo Sumarização (sem `query`)
    Se você **não** fornecer uma `query`, a API simplesmente extrairá as informações mais importantes de cada currículo e retornará um resumo detalhado para cada um.
    - **Use para**: Obter uma visão geral e estruturada de um lote de currículos.

    ---

    **Formatos Suportados**: PDF (recomendado), JPG, PNG.

    **Auditoria**: Todas as requisições são registradas no banco de dados com `request_id` e `user_id` para rastreamento.
    """
    try:
        # Verifica se arquivos foram enviados
        if not files:
            raise HTTPException(status_code=400, detail="Nenhum arquivo foi enviado. Por favor, faça upload de pelo menos um currículo.")
        
        # Define um request_id se não fornecido
        if not request_id:
            request_id = str(uuid.uuid4())
        
        # Define um user_id padrão se não fornecido
        if not user_id:
            user_id = settings.DEFAULT_USER_ID
        
        # Inicializa variáveis para rastreamento
        start_time = datetime.utcnow()
        processed_files_info: List[ResumeFile] = []
        log_file_names: List[str] = []
        error_messages_for_log: List[str] = []
        
        # Log da requisição
        logger.info(f"[{request_id}] Iniciando processamento: {len(files)} arquivo(s) de usuário {user_id}")
        if query:
            logger.info(f"[{request_id}] Query: '{query}'")
        
        # Lê os conteúdos dos arquivos
        file_contents = []
        for file in files:
            try:
                logger.info(f"[{request_id}] Lendo arquivo: {file.filename} ({file.content_type})")
                content = await file.read()
                file_contents.append({
                    "filename": file.filename,
                    "content_type": file.content_type,
                    "content": content
                })
                log_file_names.append(file.filename)
            except Exception as e:
                logger.error(f"[{request_id}] Erro ao ler arquivo {file.filename}: {e}", exc_info=True)
                raise HTTPException(status_code=400, detail=f"Erro ao ler arquivo {file.filename}: {str(e)}")
        
        # Processa cada arquivo enviado
        logger.info(f"[{request_id}] Iniciando extração de texto via OCR para {len(file_contents)} arquivo(s)")
        for i, file_data in enumerate(file_contents):
            filename = file_data["filename"]
            content_type = file_data["content_type"]
            contents = file_data["content"]
            
            logger.info(f"[{request_id}] Processando arquivo {i+1}/{len(file_contents)}: {filename}")
            
            try:
                # Extrai texto via OCR
                logger.info(f"[{request_id}] Aplicando OCR ao arquivo: {filename}")
                text, ocr_error = await ocr.process_file(contents, filename)
                if ocr_error:
                    logger.error(f"[{request_id}] Erro OCR para {filename}: {ocr_error}")
                    processed_files_info.append(ResumeFile(filename=filename, content_type=content_type, text=f"OCR Error: {ocr_error}"))
                    error_messages_for_log.append(f"{filename}: OCR Error - {ocr_error}")
                    continue # Skip to next file
                
                if not text:
                    logger.warning(f"[{request_id}] Nenhum texto extraído de {filename}. Pulando processamento LLM para este arquivo.")
                    processed_files_info.append(ResumeFile(filename=filename, content_type=content_type, text="No text extracted."))
                    error_messages_for_log.append(f"{filename}: No text extracted after OCR.")
                    continue
                
                logger.info(f"[{request_id}] Texto extraído com sucesso de {filename}. Tamanho: {len(text)} caracteres")
                processed_files_info.append(ResumeFile(filename=filename, content_type=content_type, text=text))
                
            except Exception as e:
                logger.error(f"[{request_id}] Falha ao processar arquivo {filename}: {e}", exc_info=True)
                processed_files_info.append(ResumeFile(filename=filename, content_type=content_type, text=f"Processing Error: {str(e)}"))
                error_messages_for_log.append(f"{filename}: Processing Error - {str(e)}")
                continue
        
        # Filter out files where text extraction failed completely for LLM processing
        valid_resumes_for_llm = [p_file for p_file in processed_files_info if p_file.text and not p_file.text.startswith("OCR Error:") and not p_file.text.startswith("Processing Error:") and p_file.text != "No text extracted."]
        
        if not valid_resumes_for_llm:
            logger.error(f"[{request_id}] Nenhum texto válido extraído dos arquivos. Não é possível prosseguir com análise LLM.")
            raise HTTPException(status_code=400, detail="Não foi possível extrair texto de nenhum dos arquivos enviados. Verifique se os formatos são suportados e se os arquivos contêm texto legível.")
        
        logger.info(f"[{request_id}] {len(valid_resumes_for_llm)}/{len(file_contents)} arquivo(s) com texto válido para análise LLM")
        
        # Processa o texto extraído com o LLM
        final_result = None
        
        if query:
            # Modo Ranking - Avalia currículos contra a consulta
            logger.info(f"[{request_id}] Iniciando modo RANKING para {len(valid_resumes_for_llm)} currículos")
            ranking_results: List[QueryMatch] = []
            
            for i, resume_file in enumerate(valid_resumes_for_llm):
                logger.info(f"[{request_id}] Avaliando currículo {i+1}/{len(valid_resumes_for_llm)}: {resume_file.filename}")
                
                if resume_file.text:
                    # Adiciona timeout para evitar travamento
                    try:
                        # Timeout de 60 segundos para a avaliação
                        logger.info(f"[{request_id}] Avaliando compatibilidade de {resume_file.filename} com a consulta")
                        _, justification, score = await asyncio.wait_for(
                            llm.evaluate_resume(
                                resume_text=resume_file.text, 
                                query=query, 
                                file_name=resume_file.filename
                            ), 
                            timeout=60.0
                        )
                        
                        # Timeout de 30 segundos para o resumo
                        logger.info(f"[{request_id}] Extraindo detalhes adicionais do currículo {resume_file.filename}")
                        summary_for_details = await asyncio.wait_for(
                            llm.summarize_resume(resume_file.text, resume_file.filename),
                            timeout=30.0
                        )
                        
                        logger.info(f"[{request_id}] Currículo {resume_file.filename} recebeu score: {score}")
                        ranking_results.append(QueryMatch(
                            file_name=resume_file.filename,
                            score=score if score is not None else 0.0,
                            justification=justification if justification is not None else "No justification provided.",
                            name=summary_for_details.name if summary_for_details else None,
                            title=summary_for_details.title if summary_for_details else None
                        ))
                    except asyncio.TimeoutError:
                        logger.error(f"[{request_id}] Timeout ao processar {resume_file.filename}")
                        ranking_results.append(QueryMatch(
                            file_name=resume_file.filename,
                            score=0.0,
                            justification="Timeout durante o processamento LLM. O arquivo pode ser muito grande ou complexo.",
                        ))
                else:
                    ranking_results.append(QueryMatch(
                        file_name=resume_file.filename,
                        score=0.0,
                        justification="Ignorado devido à falha na extração de texto via OCR.",
                    ))
            
            # Sort by score, descending
            ranking_results.sort(key=lambda x: x.score, reverse=True)
            logger.info(f"[{request_id}] Ranking concluído. Resultados ordenados por pontuação.")
            
            response_data = RankingResponse(
                request_id=request_id,
                user_id=user_id,
                query=query,
                ranking=ranking_results
            )
            final_result = ranking_results
        else:
            # Modo Sumarização - Gera resumos
            logger.info(f"[{request_id}] Iniciando modo SUMARIZAÇÃO para {len(valid_resumes_for_llm)} currículos")
            summaries: List[ResumeSummary] = []
            
            for i, resume_file in enumerate(valid_resumes_for_llm):
                logger.info(f"[{request_id}] Resumindo currículo {i+1}/{len(valid_resumes_for_llm)}: {resume_file.filename}")
                
                if resume_file.text:
                    try:
                        # Timeout de 30 segundos para resumo
                        summary = await asyncio.wait_for(
                            llm.summarize_resume(resume_text=resume_file.text, file_name=resume_file.filename),
                            timeout=30.0
                        )
                        if summary:
                            logger.info(f"[{request_id}] Resumo gerado com sucesso para {resume_file.filename}")
                            summaries.append(summary)
                        else:
                            logger.warning(f"[{request_id}] Falha ao gerar resumo para {resume_file.filename}")
                            summaries.append(ResumeSummary(file_name=resume_file.filename, summary="Falha ao gerar resumo. O modelo LLM não retornou resultados."))
                    except asyncio.TimeoutError:
                        logger.error(f"[{request_id}] Timeout ao resumir {resume_file.filename}")
                        summaries.append(ResumeSummary(file_name=resume_file.filename, summary="Timeout durante a geração do resumo. O arquivo pode ser muito grande ou complexo."))
                else:
                    summaries.append(ResumeSummary(file_name=resume_file.filename, summary="Ignorado devido à falha na extração de texto via OCR."))
            
            logger.info(f"[{request_id}] Sumarização concluída. Gerados {len(summaries)} resumos.")
            
            response_data = SummariesResponse(
                request_id=request_id,
                user_id=user_id,
                summaries=summaries
            )
            final_result = summaries
        
        # Log da requisição para auditoria interna
        logger.info(f"[{request_id}] Salvando log de auditoria")
        log_entry = LogEntry(
            request_id=request_id,
            user_id=user_id,
            timestamp=start_time,
            query=query,
            files_processed=log_file_names,
            result=final_result,
            error_message="; ".join(error_messages_for_log) if error_messages_for_log else None
        )
        
        try:
            await storage.save_log(log_entry)
            logger.info(f"[{request_id}] Log salvo com sucesso")
        except Exception as e:
            logger.error(f"[{request_id}] Erro ao salvar log: {e}", exc_info=True)
        
        logger.info(f"[{request_id}] Processamento concluído em {(datetime.utcnow() - start_time).total_seconds():.2f} segundos")
        
        return response_data
        
    except HTTPException:
        # Re-throw HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Erro inesperado: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro inesperado durante o processamento: {str(e)}")

# To run the app (if this file is executed directly):
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8000) 