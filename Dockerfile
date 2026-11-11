FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Source is bind-mounted at run time (see README), so edits show up without rebuilding.
COPY . .
EXPOSE 8000
CMD ["python", "run.py"]
