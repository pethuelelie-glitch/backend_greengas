import os
import yaml
from pathlib import Path
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.views import View

# Chargement du schéma OpenAPI en mémoire
_OPENAPI_DATA = None

def get_openapi_spec():
    global _OPENAPI_DATA
    if _OPENAPI_DATA is None:
        schema_path = settings.BASE_DIR / 'openapi.yaml'
        if not schema_path.exists():
            # Fallback vers le dossier parent si nécessaire
            schema_path = settings.BASE_DIR.parent / 'openapi.yaml'
        with open(schema_path, 'r', encoding='utf-8') as f:
            _OPENAPI_DATA = yaml.safe_load(f)
    return _OPENAPI_DATA


class OpenAPISchemaView(View):
    """Renvoie le schéma OpenAPI au format JSON"""
    def get(self, request):
        spec = get_openapi_spec()
        return JsonResponse(spec, json_dumps_params={'ensure_ascii': False, 'indent': 2})


class SwaggerUIView(View):
    """Interface interactive Swagger UI pour explorer et tester les 49 endpoints de l'API"""
    def get(self, request):
        html = """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>GREENGAS API — Documentation Swagger UI</title>
    <link rel="stylesheet" type="text/css" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css" >
    <link rel="icon" type="image/png" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/favicon-32x32.png" sizes="32x32" />
    <style>
        html { box-sizing: border-box; overflow: -moz-scrollbars-vertical; overflow-y: scroll; }
        *, *:before, *:after { box-sizing: inherit; }
        body { margin: 0; background: #fafafa; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
        .topbar { background-color: #1e4620 !important; border-bottom: 3px solid #2e7d32; }
        .topbar-wrapper a span { color: #ffffff !important; font-weight: bold; font-size: 1.2rem; }
        .swagger-ui .info .title { color: #1e4620; }
        .swagger-ui .scheme-container { background: #f1f8e9; border-bottom: 1px solid #c8e6c9; }
        .swagger-ui .btn.authorize { background-color: #2e7d32; color: #fff; border-color: #2e7d32; }
        .swagger-ui .btn.authorize svg { fill: #fff; }
    </style>
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"> </script>
    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-standalone-preset.js"> </script>
    <script>
    window.onload = function() {
      const ui = SwaggerUIBundle({
        url: "/api/schema/",
        dom_id: '#swagger-ui',
        deepLinking: true,
        presets: [
          SwaggerUIBundle.presets.apis,
          SwaggerUIStandalonePreset
        ],
        plugins: [
          SwaggerUIBundle.plugins.DownloadUrl
        ],
        layout: "StandaloneLayout",
        persistAuthorization: true,
        displayRequestDuration: true,
        filter: true,
        docExpansion: "list"
      });
      window.ui = ui;
    };
    </script>
</body>
</html>"""
        return HttpResponse(html, content_type='text/html; charset=utf-8')


class RedocView(View):
    """Interface de lecture documentaire ReDoc"""
    def get(self, request):
        html = """<!DOCTYPE html>
<html>
  <head>
    <title>GREENGAS API — Documentation ReDoc</title>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://fonts.googleapis.com/css?family=Montserrat:300,400,700|Roboto:300,400,700" rel="stylesheet">
    <style>
      body { margin: 0; padding: 0; }
    </style>
  </head>
  <body>
    <redoc spec-url='/api/schema/'></redoc>
    <script src="https://cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js"> </script>
  </body>
</html>"""
        return HttpResponse(html, content_type='text/html; charset=utf-8')
