FROM python:3.12-slim

WORKDIR /app

# System deps: Pillow needs a few image libraries to build/run correctly.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Uploaded product/user images live outside the app code so they can be
# bind-mounted independently (same reasoning as the old PHP setup).
RUN mkdir -p /data/uploads/products /data/uploads/users

EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "3", \
     "--access-logfile", "-", "--error-logfile", "-", "--log-level", "info", \
     "wsgi:app"]
