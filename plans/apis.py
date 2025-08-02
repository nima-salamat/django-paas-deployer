from .models import Plan
from .serializers import PlanSerializer, UnauthorizedPlanSerializer
from rest_framework.viewsets import ViewSet
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from core.global_settings import config

class PlanAdminViewSet(ViewSet):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsAdminUser]

    # def get_permissions(self):
    #     if self.request.method in ['POST', 'PUT', 'PATCH', 'DELETE']:
    #         # Only admin users can create, update, delete
    #         return [IsAuthenticated(), IsAdminUser()]
    #     return [IsAuthenticated()]
    
    def list(self, request):
        plan = Plan.objects.all()
        serializer = PlanSerializer(plan, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def retrieve(self, request, pk=None):
        try:
            plan = Plan.objects.get(pk=pk)
        except Plan.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = PlanSerializer(plan)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def create(self, request):
        serializer = PlanSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, pk=None):
        try:
            plan = Plan.objects.get(pk=pk)
        except Plan.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = PlanSerializer(plan, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk=None):
        try:
            plan = Plan.objects.get(pk=pk)
        except Plan.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        plan.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    
class PlatformPlansAPIView(APIView):
    def get(self, request):
        return Response(data=config.PLATFORM_CHOICES, status=status.HTTP_200_OK)

    def post(self, request):
        data = request.data
        platform = data["platform"]
        query_argument = ""
        if platform:
            for i,j in config.PLATFORM_CHOICES:
                if platform in (i,j):
                    query_argument = i
                    
        if not query_argument:
            return Response(data={"error":"Incorrect platform."}, status=status.HTTP_400_BAD_REQUEST)
            
        plans = Plan.objects.filter(platform=query_argument)
        if not plans.exists():
            return Response(data={"error":"There is not such plans."}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = UnauthorizedPlanSerializer(plans, many=True)
        
        return Response(data=serializer.data, status=status.HTTP_200_OK)


class PlansApiView(APIView):
    def get(self, request):
        ids = request.query_params.get("id", "")
        if not ids:
            data = Plan.objects.all()
            serializer = UnauthorizedPlanSerializer(data, many=True)
        else:
            if "," in ids:
                all_ids = []
                for i in ids.split(","):
                    if i.isdigit():
                        all_ids.append(i)
                        
                if not all_ids:
                    return Response({"error": "Invalid IDs provided."}, status=status.HTTP_400_BAD_REQUEST)

                data = Plan.objects.filter(pk__in=all_ids)
                if not data.exists():
                    return Response(data={"error":"There is not such plans."}, status=status.HTTP_404_NOT_FOUND)

                serializer = UnauthorizedPlanSerializer(data, many=True)
                
            else:
                if ids.isdigit():
                    try:
                        data = Plan.objects.get(pk=ids)
                    except Plan.DoesNotExist:
                        return Response(data={"error":"There is not such plans."}, status=status.HTTP_404_NOT_FOUND)
            
                    serializer = UnauthorizedPlanSerializer(data)
                else:
                    return Response({"error": "Invalid ID format."}, status=status.HTTP_400_BAD_REQUEST)
    
            return Response(data=serializer.data, status=status.HTTP_200_OK)
