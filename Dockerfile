FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (better layer caching).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code.
COPY . .

# Streamlit listens on 8501 by default; hosts that set $PORT are handled by the CMD below.
EXPOSE 8501

# Use $PORT when the platform provides one (Render/Railway/Fly), else default to 8501.
CMD streamlit run app.py --server.port=${PORT:-8501} --server.address=0.0.0.0
