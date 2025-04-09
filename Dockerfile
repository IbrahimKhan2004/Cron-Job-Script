FROM python:3.11-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8080

#Ensure the start script is executable
RUN chmod +x start.sh

# Command to run when starting the container
CMD ["./start.sh"]
# --- END OF UPDATED FILE Dockerfile ---
