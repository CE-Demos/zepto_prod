# 1. Use an official Python runtime as a parent image
# Using Python 3.10 or 3.11 is generally a good choice.
# -slim variant is smaller than the full one.
FROM python:3.10-slim

# 2. Set the working directory in the container
WORKDIR /app


# # Install build dependencies AND GEOS development files
# RUN apk update && \
#     apk add --no-cache build-base python3-dev gcc g++ linux-headers musl-dev geos-dev

# # Install GEOS system package
# RUN apk add geos

# 3. Copy the requirements file into the container at /app
# This is done first to leverage Docker's build cache. If requirements.txt
# doesn't change, this layer (and the pip install) won't be rebuilt.
COPY requirements.txt .

# 4. Install any needed packages specified in requirements.txt
# --no-cache-dir reduces image size by not storing the pip download cache
# --upgrade pip ensures you have a recent version of pip
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 5. Copy the rest of your application code (app.py, video_gen.py) into the container at /app
COPY app.py .
COPY video_gen.py .
# If you have other local modules or files your app needs, copy them too.
# e.g., COPY ./my_utils /app/my_utils

# 6. Make port 7860 available to the world outside this container
# Gradio typically runs on port 7860 by default
EXPOSE 8080

# 7. Define environment variables (optional, but good practice for configuration)
# These can be overridden at runtime (e.g., by Cloud Run)
# Example (ensure your code reads from environment variables if you use this):
# ENV GCS_BUCKET_NAME="your-default-bucket-if-not-set-at-runtime"
# ENV VERTEX_AI_PROJECT_ID="your-default-project-if-not-set-at-runtime"
# ENV GOOGLE_APPLICATION_CREDENTIALS="/app/path/to/your/service-account-key.json"
# Note: For Cloud Run, it's better to assign a service account to the Cloud Run instance
# itself rather than bundling a key file in the image. So, GOOGLE_APPLICATION_CREDENTIALS
# might not be needed in the Dockerfile if deploying to Cloud Run with an assigned service account.

# 8. Run app.py when the container launches
# This command assumes your Gradio app (app.py) will listen on 0.0.0.0
# which Gradio does by default when share=False.
CMD ["python", "app.py"]