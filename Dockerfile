FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# System deps for lxml / psycopg2 build wheels are already provided by slim +
# manylinux wheels; no extra apt packages needed for the default stack.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default: run a full ETL update. Override the command as needed, e.g.:
#   docker compose run --rm app python -m bvb_scraper.main company TLV
ENTRYPOINT ["python", "-m", "bvb_scraper.main"]
CMD ["update-all", "--export", "storage/bvb_dataset.json"]
