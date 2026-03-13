FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (cache layer)
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy application code
COPY . .

# Railway injects PORT env var
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
