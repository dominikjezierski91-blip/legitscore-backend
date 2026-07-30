FROM python:3.13-slim

# WeasyPrint (v53+) only needs Pango for text shaping — no more cairo/gdk-pixbuf.
# fonts-dejavu-core/fonts-liberation cover Polish diacritics in generated PDFs.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz-subset0 \
    fontconfig \
    fonts-dejavu-core \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY prompt_a.txt prompt_a_backup_v3.txt prompt_a_v4_candidate.txt ./

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
