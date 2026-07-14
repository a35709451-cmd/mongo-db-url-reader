# Use the official lightweight Python image.
FROM python:3.10-slim

# Prevent Python from writing .pyc files and enable buffering for logs
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set standard working directory
WORKDIR /app

# Install system dependencies (optional but good for stability)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install python packages
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the bot application files
COPY . /app/

# Run the telegram bot script
CMD ["python", "bot.py"]
