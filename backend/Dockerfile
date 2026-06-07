FROM python:3.12-slim

WORKDIR /app

COPY . .
RUN pip install --no-cache-dir -e ".[dev]"
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

# The entrypoint runs `alembic upgrade head` before launching the server so
# schema migrations are applied automatically on every deploy.
CMD ["/app/entrypoint.sh"]
