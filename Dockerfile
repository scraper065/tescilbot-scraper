FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright browsers
RUN playwright install chromium
RUN playwright install-deps chromium

COPY . .

ENV PORT=8000
EXPOSE 8000

CMD ["python", "main.py"]
