from django.shortcuts import render, HttpResponse
from Chikara.views import checklogin
from django.http import JsonResponse
from Chikara.views import header,BASE_DIR,STATIC_ROOT
def usersettings(request):
    if checklogin(request.COOKIES.get('username'),request.COOKIES.get('password'))[0]:
        html = header(request) + open(str(BASE_DIR) + "/" + STATIC_ROOT + "/html/usersettings.html").read()
        return HttpResponse(html)
    else:
        return HttpResponse("Please login...")