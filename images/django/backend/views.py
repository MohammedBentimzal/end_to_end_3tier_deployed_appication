from django.shortcuts import render
from django.http import JsonResponse
from django.db import connection
from django.db.utils import OperationalError


def home(request):
    return render(request, "index.html")


def health(request):
    """
    Confirms both that the app is serving requests AND that it can
    actually reach and query the configured database (Postgres or MySQL,
    depending on db_engine chosen at deploy time).
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return JsonResponse({
            "status": "healthy",
            "database": "connected",
            "engine": connection.settings_dict.get("ENGINE"),
        })
    except OperationalError as e:
        return JsonResponse({
            "status": "unhealthy",
            "database": "not connected",
            "error": str(e),
        }, status=500)
    except Exception as e:
        return JsonResponse({
            "status": "unhealthy",
            "database": "error",
            "error": str(e),
        }, status=500)


def info(request):
    return JsonResponse({
        "backend": "Django",
        "cloud": "AWS EC2",
        "version": "1.0",
    })
