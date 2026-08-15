from django.conf import settings
from django.shortcuts import render
from django.http import JsonResponse
from pymongo import MongoClient
from pymongo.errors import PyMongoError


def home(request):
    return render(request, "index.html")


def _get_mongo_client():
    uri = (
        f"mongodb://{settings.MONGO_USER}:{settings.MONGO_PASSWORD}"
        f"@{settings.MONGO_HOST}:{settings.MONGO_PORT}/{settings.MONGO_DB_NAME}"
        f"?authSource=admin"
    )
    return MongoClient(uri, serverSelectionTimeoutMS=5000)


def health(request):
    """
    Bypasses Django's ORM entirely (it doesn't support MongoDB) and talks
    to Mongo directly via pymongo, using the same DB_* env vars every
    other backend/database combination in this project uses.
    """
    try:
        client = _get_mongo_client()
        # ping forces a real round trip to the server, confirming both
        # network reachability and authentication succeeded.
        client.admin.command("ping")
        server_info = client.server_info()
        client.close()
        return JsonResponse({
            "status": "healthy",
            "database": "connected",
            "engine": "mongo",
            "mongo_version": server_info.get("version"),
        })
    except PyMongoError as e:
        return JsonResponse({
            "status": "unhealthy",
            "database": "not connected",
            "engine": "mongo",
            "error": str(e),
        }, status=500)
    except Exception as e:
        return JsonResponse({
            "status": "unhealthy",
            "database": "error",
            "engine": "mongo",
            "error": str(e),
        }, status=500)


def info(request):
    return JsonResponse({
        "backend": "Django",
        "cloud": "AWS EC2",
        "version": "1.0",
    })
