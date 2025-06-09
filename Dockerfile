# Start with a standard Python base image
FROM python:3.9-slim

# Set the working directory inside the container
WORKDIR /app

# Install the FFmpeg program using the system package manager
RUN apt-get update && apt-get install -y ffmpeg

# Copy the requirements file into the container
COPY requirements.txt .

# Install the Python packages listed in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code into the container
COPY . .

# Tell Render what port the application will be listening on
EXPOSE 10000

# The command to start your Flask application using Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "app:app"]
