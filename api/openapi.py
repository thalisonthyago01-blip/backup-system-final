from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi


def custom_openapi(app: FastAPI):
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title="Backup System API",
        version="1.0.0",
        description="API do sistema de backup",
        routes=app.routes,
    )

    openapi_schema["openapi"] = "3.0.3"

    schemas = openapi_schema.get("components", {}).get("schemas", {})

    for schema in schemas.values():
        if "properties" in schema:
            files_property = schema["properties"].get("files")

            if files_property and files_property.get("type") == "array":
                files_property["items"] = {
                    "type": "string",
                    "format": "binary"
                }

    app.openapi_schema = openapi_schema

    return app.openapi_schema