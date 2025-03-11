# Use an official Python runtime as a parent image.
FROM python:3.9-slim as build

# Set environment variables to prevent Python from writing .pyc files to disk and buffering stdout.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set a working directory in the container.
WORKDIR /app

COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . /app/


# Set the command to run your bot.
CMD ["python", "mix_bot.py"]
