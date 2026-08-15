import os
SECRET_KEY='dev'
DEBUG=True
ROOT_URLCONF='config.urls'
ALLOWED_HOSTS=['*']
INSTALLED_APPS=['django.contrib.contenttypes','django.contrib.staticfiles','backend']
MIDDLEWARE=[]
TEMPLATES=[{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':['templates'],'APP_DIRS':True}]
STATIC_URL='/static/'
STATICFILES_DIRS=['static']
DATABASES={'default':{           #if DB_ENGINE: django.db.backends.mysql ,django uses mysqlclient driver for postgres 
'ENGINE':os.getenv('DB_ENGINE'), #if DB_ENGINE: django.db.backends.postgresql , django uses psycopg driver for postgres 
'NAME':os.getenv('DB_NAME'),     #is the env_name input by the user    
'USER':os.getenv('DB_USER'),     
'PASSWORD':os.getenv('DB_PASSWORD'),
'HOST':os.getenv('DB_HOST'),
'PORT':os.getenv('DB_PORT'),
}}
