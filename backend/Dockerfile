FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

# libgl/libglib: OpenCV runtime for the optional OCR engine.
# fonts-dejavu-core: bounding-box labels on annotated previews.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-ocr.txt ./

ARG WITH_OCR=true
RUN pip install -r requirements.txt \
    && if [ "$WITH_OCR" = "true" ]; then pip install -r requirements-ocr.txt; fi

COPY app ./app
COPY data ./data

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
