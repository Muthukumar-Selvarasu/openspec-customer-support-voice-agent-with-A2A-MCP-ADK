FROM docker.io/library/python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=8000

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY mcp_toolbox ./mcp_toolbox

EXPOSE 8000

CMD ["python", "-m", "src.api.web"]
