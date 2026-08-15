from django.shortcuts import render
from django.http import JsonResponse
from django.db import connection
def home(request): return render(request,'index.html')
def health(request):
    try:
        with connection.cursor() as c:
            c.execute('SELECT 1')
        return JsonResponse({'status':'healthy','database':'connected'})
    except Exception as e:
        return JsonResponse({'status':'unhealthy','database':'not connected','error':str(e)},status=500)
def info(request):
    return JsonResponse({'backend':'Django','cloud':'AWS EC2','version':'1.0'})
