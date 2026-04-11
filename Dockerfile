FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Download the spaCy model used in ParsingAgent
RUN python -m spacy download en_core_web_sm

COPY . .

# Run as non-root user for security
RUN useradd -m talentos
USER talentos

# Render needs the app to bind to the $PORT env variable
ENV PORT=8000
EXPOSE 8000

CMD uvicorn api.main:app --host 0.0.0.0 --port $PORT
