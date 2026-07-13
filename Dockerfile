FROM python:3.10-slim

# Install the required Linux system binaries
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    poppler-utils \
    libmagic-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /code

COPY ./requirements.txt /code/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

COPY . .

# Run the Flask app on port 7860 (Hugging Face default)
CMD ["python", "api/index.py"]
