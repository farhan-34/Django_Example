from django.urls import path

from example.views import VisitView

urlpatterns = [
    path("visit/", VisitView.as_view(), name='visit'),
]