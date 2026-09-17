"""Print the FastAPI OpenAPI schema (used by `make types`)."""

import json

from app.main import create_app

if __name__ == "__main__":
    print(json.dumps(create_app().openapi(), indent=2))
