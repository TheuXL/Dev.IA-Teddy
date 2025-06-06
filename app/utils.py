import re
from datetime import datetime, timezone
from PIL import Image # For potential image utilities
import io

def clean_text(text: str) -> str:
    """Limpa o texto extraído, removendo excesso de quebras de linha e espaços."""
    text = re.sub(r'\n+', '\n', text)  # Replace multiple newlines with a single one
    text = re.sub(r'\s{2,}', ' ', text)   # Replace multiple spaces with a single one
    text = text.strip()
    return text

def generate_timestamp() -> datetime:
    """Gera um timestamp UTC padronizado."""
    return datetime.now(timezone.utc)

# Example utility - might be expanded or used by ocr.py
def convert_image_to_bytes(image: Image.Image, format: str = "PNG") -> bytes:
    """Converte um objeto de imagem (PIL) para bytes."""
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format=format)
    return img_byte_arr.getvalue()

def get_file_extension(filename: str) -> str:
    """Extrai a extensão de um nome de arquivo."""
    return filename.split('.')[-1].lower() if '.' in filename else "" 