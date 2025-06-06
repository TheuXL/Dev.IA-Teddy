FROM python:3.10-slim

# Instala dependências do sistema
RUN apt-get update && apt-get install -y \
    poppler-utils \
    libgl1-mesa-glx \
    libxrender1 \
    # Para o PyMuPDF
    mupdf \
    mupdf-tools \
    libmupdf-dev \
    && rm -rf /var/lib/apt/lists/*

# Cria diretório de trabalho
WORKDIR /app

# Copia e instala as dependências primeiro para aproveitar o cache do Docker
COPY requirements.txt .
RUN pip install --upgrade pip
# Instala torch e torchvision específicos para CPU para um build menor e mais estável
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
# Instala o restante das dependências. O Pip irá detectar que torch/torchvision já estão instalados.
RUN pip install --no-cache-dir -r requirements.txt

# Pré-download dos modelos do EasyOCR para evitar download no runtime
RUN mkdir -p /root/.EasyOCR/ && python -c "import easyocr; easyocr.Reader(['pt', 'en'])"

# Copia o resto da aplicação
COPY . .

# Expõe a porta da API
EXPOSE 8000

# Comando padrão
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"] 