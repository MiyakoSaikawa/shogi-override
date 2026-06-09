from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("Boys_be_ambitious_like_this_miyako/", admin.site.urls),
    path("", include("shogi.urls")),
]
