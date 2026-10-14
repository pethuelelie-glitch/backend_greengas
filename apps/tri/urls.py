from django.urls import path
from apps.tri.views import TourneeTriView, LotListView

urlpatterns = [
    path('tournees/<uuid:id>/tri/', TourneeTriView.as_view(), name='tournee_tri'),
    path('lots/', LotListView.as_view(), name='lots_lister'),
]
