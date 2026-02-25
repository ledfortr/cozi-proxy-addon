FROM python:3.11-slim

WORKDIR /cozi_proxy

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python3", "/cozi_proxy/server.py"]

