FROM python:3.12-slim

WORKDIR /app

# Copy only the manifest first for dependency layer caching
COPY pyproject.toml ./
# Stub the package directory so the editable install resolves correctly
RUN mkdir -p app && touch app/__init__.py
RUN pip install --no-cache-dir -e ".[dev]"

# Copy the rest of the source (this layer rebuilds on any source change
# but the pip layer above stays cached)
COPY . .
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

CMD ["/app/entrypoint.sh"]
