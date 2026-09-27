# Image de Rédigo. À construire depuis la racine du dépôt :
#   docker build -f redigo/Dockerfile -t redigo .
#   docker run -p 8060:8060 -v redigo-donnees:/donnees -e REDIGO_URL=https://redigo.exemple.fr redigo
FROM python:3.12-slim

# Polices libres aux mêmes dimensions que Times New Roman, Arial, Calibri et Cambria (pour l'export PDF).
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-liberation fonts-crosextra-carlito fonts-crosextra-caladea \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "reportlab>=4"

WORKDIR /app
COPY memoire ./memoire
COPY redigo ./redigo

ENV REDIGO_BASE=/donnees/redigo.db \
    REDIGO_DEMO=0 \
    REDIGO_DERRIERE_PROXY=1 \
    PYTHONUNBUFFERED=1
RUN mkdir -p /donnees && chown nobody /donnees
VOLUME /donnees
EXPOSE 8060
USER nobody
CMD ["python", "-m", "redigo", "lancer", "--hote", "0.0.0.0", "--port", "8060"]
