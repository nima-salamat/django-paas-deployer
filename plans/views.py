from django.shortcuts import render
from .models import Plan

def plan_list(request):
    plans = Plan.objects.all()
    return render(request, 'plans/plan_list.html', {'plans': plans})
