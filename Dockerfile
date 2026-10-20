# Wepwawet Veil (the house router). The code itself is mounted from this folder
# (docker-compose.yml), so a git pull plus a restart picks up changes; rebuild the image
# (docker compose up -d --build) only when this file changes.
FROM python:3.12-slim
# the sentence diagramming model: settings.yaml language: spacy_model names it, this installs it
ARG SPACY_MODEL_WHEEL=https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl
WORKDIR /app
# pinned to the versions the tests ran on (Oct 13, 2026), so a rebuild gets what was tested
RUN pip install --no-cache-dir "fastapi==0.143.0" "starlette==1.6.0" "uvicorn==0.53.0" "httpx==0.28.1" \
    "PyYAML==6.0.3" "ruamel.yaml==0.19.1" "cryptography==50.0.1" "spacy==3.8.7" "${SPACY_MODEL_WHEEL}"
# no __pycache__ folders written into your checkout (they would be root's)
ENV PYTHONDONTWRITEBYTECODE=1
# the chat door (LiteLLM calls it) and the pages
EXPOSE 8770 8771
CMD ["python", "-m", "veil.main"]
