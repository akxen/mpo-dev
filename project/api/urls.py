from django.urls import path
from .views import RunModel

urlpatterns = [
    path('run', RunModel.as_view()),
]
