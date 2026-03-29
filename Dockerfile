# 内网 Linux / 容器部署示例（生产请配合反向代理与 HTTPS）
FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HR_WEB_HOST=0.0.0.0 \
    HR_WEB_PORT=5001 \
    HR_WEB_DEBUG=0

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p hr_excel_web/uploads hr_excel_web/exports

EXPOSE 5001

CMD ["python", "main.py"]
