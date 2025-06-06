import logging
import json
from typing import Optional, Tuple, Any

import httpx

from .settings import settings
from .models import ResumeSummary

logger = logging.getLogger(__name__)


async def _call_gemini_api(prompt: str) -> Optional[Any]:
    """Envia um prompt para a API do Gemini e retorna a resposta."""
    if not settings.GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY não configurada.")
        return None

    url = f"{settings.GEMINI_API_URL}?key={settings.GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.2,
            "max_output_tokens": 2048,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            logger.debug(f"Enviando prompt para a API do Gemini: {prompt[:200]}...")
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()

            response_data = response.json()
            logger.debug(f"Resposta completa da API Gemini: {response_data}")

            # Valida a estrutura da resposta da API para garantir que o conteúdo esperado está presente.
            if not response_data.get("candidates") or not response_data["candidates"][0].get("content", {}).get("parts"):
                logger.error("Estrutura de resposta inválida da API Gemini: 'parts' não encontrado.")
                logger.error(f"Resposta completa: {response_data}")
                return None
            
            generated_text = response_data["candidates"][0]["content"]["parts"][0]["text"]
            logger.debug(f"Texto bruto da resposta da API Gemini: {generated_text[:200]}...")
            return json.loads(generated_text)

    except httpx.HTTPStatusError as e:
        logger.error(f"Erro HTTP ao chamar a API Gemini: {e.response.status_code} - {e.response.text}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Erro ao decodificar JSON da resposta da API Gemini: {e}")
        logger.debug(f"Resposta que causou erro: {generated_text}")
        return None
    except Exception as e:
        logger.error(f"Erro inesperado ao chamar a API Gemini: {e}", exc_info=True)
        return None


async def summarize_resume(resume_text: str, file_name: str) -> Optional[ResumeSummary]:
    """
    Gera um resumo estruturado de um currículo usando a API do Gemini.

    Args:
        resume_text: O texto extraído do currículo.
        file_name: O nome do arquivo original para referência.

    Returns:
        Um objeto ResumeSummary com os dados extraídos ou None em caso de erro.
    """
    logger.info(f"Iniciando sumarização do currículo: {file_name}")

    if len(resume_text) > 15000:  # Limite de caracteres para o prompt
        logger.warning(f"Texto do currículo ({len(resume_text)} caracteres) excede o limite. Truncando para 15000 caracteres.")
        resume_text = resume_text[:15000]

    prompt = f"""
    Você é um assistente de recrutamento especializado em analisar currículos.
    Analise o seguinte currículo e extraia as informações relevantes no formato JSON.

    Currículo:
    {resume_text}

    Extraia as seguintes informações:
    1. Nome completo do candidato
    2. Cargo atual ou título profissional
    3. Lista de tecnologias/habilidades técnicas mencionadas
    4. Lista das principais experiências profissionais (empresa, cargo, período)
    5. Lista de formações acadêmicas (instituição, curso, ano)
    6. Um resumo textual conciso do perfil profissional.

    Retorne APENAS um objeto JSON válido com os seguintes campos. Não inclua nenhum outro texto ou formatação markdown.
    {{
        "name": "Nome do Candidato",
        "title": "Cargo/Título Profissional",
        "technologies": ["tech1", "tech2", ...],
        "experiences": ["experiência 1", "experiência 2", ...],
        "education": ["formação 1", "formação 2", ...],
        "summary": "Resumo textual do perfil profissional."
    }}
    """

    try:
        logger.info(f"Enviando texto de {len(resume_text)} caracteres para sumarização via API Gemini.")
        result = await _call_gemini_api(prompt)

        if not result:
            logger.error(f"Falha ao obter um sumário válido da API para {file_name}")
            return ResumeSummary(file_name=file_name, summary="Erro ao analisar resposta da IA: formato inválido.")

        logger.info(f"JSON extraído com sucesso para o currículo {file_name}")

        summary = ResumeSummary(
            file_name=file_name,
            name=result.get("name"),
            title=result.get("title"),
            technologies=result.get("technologies", []),
            experiences=result.get("experiences", []),
            education=result.get("education", []),
            summary=result.get("summary", "")
        )

        logger.info(f"Resumo gerado com sucesso para {file_name}: {summary.name} - {summary.title}")
        return summary

    except Exception as e:
        logger.error(f"Erro ao sumarizar o currículo {file_name}: {e}", exc_info=True)
        return None


async def evaluate_resume(resume_text: str, query: str, file_name: str) -> Tuple[Optional[str], Optional[str], Optional[float]]:
    """
    Avalia a compatibilidade de um currículo com uma consulta (query) usando a API do Gemini.

    Args:
        resume_text: O texto extraído do currículo.
        query: A consulta ou descrição da vaga para avaliação.
        file_name: O nome do arquivo original para referência.

    Returns:
        Uma tupla contendo o título, a justificativa e a pontuação, ou (None, "mensagem de erro", 0.0) em caso de falha.
    """
    logger.info(f"Avaliando o currículo {file_name} para a consulta: '{query}'")

    if len(resume_text) > 15000:
        logger.warning(f"Texto do currículo ({len(resume_text)} caracteres) excede o limite. Truncando para 15000 caracteres.")
        resume_text = resume_text[:15000]

    prompt = f"""
    Você é um assistente de recrutamento especializado em analisar currículos.
    Avalie o seguinte currículo em relação à consulta/vaga especificada.

    Consulta: {query}

    Currículo:
    {resume_text}

    Analise o currículo e determine o quão bem ele se adequa à consulta/vaga.

    Retorne APENAS um objeto JSON válido com o seguinte formato. Não inclua nenhum outro texto ou formatação markdown.
    {{
        "title": "Cargo ou título do candidato",
        "justification": "Explicação detalhada sobre por que o currículo é ou não adequado para a vaga.",
        "score": X.X  // Pontuação de 0.0 a 1.0, onde 1.0 representa uma correspondência perfeita.
    }}
    """

    try:
        logger.info(f"Enviando prompt de avaliação com {len(resume_text)} caracteres para a API Gemini.")
        result = await _call_gemini_api(prompt)

        if not result or not all(k in result for k in ["justification", "score"]):
            logger.error(f"Falha ao obter uma avaliação válida da API para {file_name}")
            return None, "Erro ao analisar resposta da IA: formato inválido ou chaves ausentes.", 0.0

        score = float(result.get("score", 0.0))
        # Garante que a pontuação esteja sempre no intervalo de 0.0 a 1.0.
        score = max(0.0, min(1.0, score))

        logger.info(f"Avaliação concluída para {file_name}. Pontuação: {score}")

        return (
            result.get("title"),
            result.get("justification"),
            score
        )

    except Exception as e:
        logger.error(f"Erro ao avaliar o currículo {file_name}: {e}", exc_info=True)
        return None, f"Erro no processamento: {str(e)}", 0.0 