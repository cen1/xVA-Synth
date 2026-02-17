FROM python:3.11-slim-trixie

RUN apt-get update && \
    apt-get install -y --no-install-recommends espeak-ng ffmpeg git build-essential && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir numpy && \
    pip install --no-cache-dir -r requirements.txt

# Clone xva-trainer and copy dev libs into site-packages
RUN git clone --depth 1 https://github.com/DanRuta/xva-trainer /tmp/xva-trainer && \
    cp -r /tmp/xva-trainer/lib/_dev/* /usr/local/lib/python3.11/site-packages/ && \
    rm -rf /tmp/xva-trainer

COPY . .

# Download NLTK data
RUN python download_nltk.py

EXPOSE 8008

CMD ["python", "server.py"]
