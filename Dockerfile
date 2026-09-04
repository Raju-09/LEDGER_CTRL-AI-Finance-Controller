FROM python:3.12-slim

WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Ensure data directory exists and has correct permissions for SQLite
RUN mkdir -p data && chmod 777 data

# Expose default port
EXPOSE 8000

# Command to run the application with dynamic $PORT support
CMD uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}
