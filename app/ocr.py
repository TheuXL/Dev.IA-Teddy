import io
import os
import tempfile
import logging
from typing import Tuple, Optional
import asyncio

# Importa bibliotecas para OCR e processamento de imagens
import easyocr
import fitz  # PyMuPDF
import numpy as np
from PIL import Image

# Importação do módulo utils para manter compatibilidade
from .utils import clean_text

logger = logging.getLogger(__name__)

# Inicializa o leitor EasyOCR. Este processo pode ser lento na primeira vez.
reader = None
try:
    # Adicionado suporte para português e inglês.
    reader = easyocr.Reader(['pt', 'en'])
    logger.info("Leitor OCR (EasyOCR) inicializado com sucesso.")
except Exception as e:
    logger.error(f"Erro ao inicializar o leitor OCR: {e}", exc_info=True)

def is_pdf(filename: str) -> bool:
    """Verifica, pela extensão, se o arquivo é um PDF."""
    return filename.lower().endswith('.pdf')

def is_image(filename: str) -> bool:
    """Verifica, pela extensão, se o arquivo é uma imagem."""
    image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.gif']
    return any(filename.lower().endswith(ext) for ext in image_extensions)

async def process_file(file_content: bytes, filename: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Processa um arquivo (PDF ou imagem) para extrair seu conteúdo textual.
    
    Args:
        file_content: O conteúdo do arquivo em bytes.
        filename: O nome do arquivo para determinar o tipo de processamento.
    
    Returns:
        Uma tupla contendo o texto extraído e uma mensagem de erro (se houver).
    """
    if not reader:
        return None, "Leitor OCR não inicializado corretamente."
    
    logger.info(f"Iniciando processamento OCR para o arquivo: {filename}")
    
    try:
        if is_pdf(filename):
            logger.info(f"Arquivo PDF detectado: {filename}")
            return await process_pdf(file_content)
        elif is_image(filename):
            logger.info(f"Arquivo de imagem detectado: {filename}")
            return await process_image(file_content)
        else:
            error_msg = f"Formato de arquivo não suportado: {filename}"
            logger.warning(error_msg)
            return None, error_msg
    except Exception as e:
        error_msg = f"Erro no processamento do arquivo {filename}: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return None, error_msg

async def process_pdf(file_content: bytes) -> Tuple[Optional[str], Optional[str]]:
    """
    Extrai texto de um arquivo PDF, combinando extração direta e OCR.
    
    Primeiro, tenta extrair o texto incorporado no PDF, que é mais rápido e preciso.
    Se o texto extraído for insuficiente, o método recorre ao OCR, tratando cada
    página como uma imagem.
    """
    all_text = ""
    try:
        # Utiliza o PyMuPDF para abrir o conteúdo do PDF em memória.
        doc = fitz.open(stream=file_content, filetype="pdf")
        
        # Tenta a extração de texto direta de todas as páginas.
        for page in doc:
            all_text += page.get_text()
        
        # Limpa o texto extraído.
        all_text = clean_text(all_text)

        # Se o texto direto for suficiente, retorna para evitar o OCR, que é mais lento.
        if len(all_text) > 100:  # Limiar arbitrário para considerar o texto suficiente.
            logger.info(f"Texto extraído diretamente do PDF ({len(all_text)} caracteres).")
            return all_text, None

        logger.info(f"Texto incorporado insuficiente ({len(all_text)}). Recorrendo ao OCR...")
        
        # Se a extração direta falhou, parte para o OCR página por página.
        all_text_ocr = ""
        for page_num, page in enumerate(doc):
            logger.info(f"Processando página {page_num + 1}/{len(doc)} com OCR.")
            
            # Renderiza a página como uma imagem de alta resolução.
            pix = page.get_pixmap(dpi=300)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            
            # Converte a imagem para um array numpy, que é o formato esperado pelo EasyOCR.
            img_np = np.array(img)
            
            # Executa o OCR na imagem da página.
            result = reader.readtext(img_np, detail=0, paragraph=True)
            all_text_ocr += ' '.join(result)
        
        full_text = clean_text(all_text_ocr)
        logger.info(f"OCR do PDF concluído. Total: {len(full_text)} caracteres.")
        return full_text, None
    
    except Exception as e:
        error_msg = f"Erro ao processar PDF: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return None, error_msg

async def process_image(file_content: bytes) -> Tuple[Optional[str], Optional[str]]:
    """Extrai texto de uma imagem usando EasyOCR."""
    try:
        # Carrega a imagem a partir dos bytes e a converte para o formato do EasyOCR.
        img_np = np.array(Image.open(io.BytesIO(file_content)))
        
        # Executa o OCR em uma thread separada para não bloquear a thread principal do asyncio.
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: reader.readtext(img_np, detail=0, paragraph=True))
        
        text = clean_text(' '.join(result))
        logger.info(f"OCR da imagem concluído. Total: {len(text)} caracteres.")
        return text, None
    
    except Exception as e:
        error_msg = f"Erro ao processar imagem: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return None, error_msg 