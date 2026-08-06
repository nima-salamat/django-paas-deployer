from pathlib import Path

from django.http import FileResponse, Http404
from rest_framework.views import APIView
from rest_framework.authentication import TokenAuthentication, SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, NotFound

from deploy.models import Deploy


class DeploymentDownloadAPIView(APIView):

    authentication_classes = [
        SessionAuthentication,  
        TokenAuthentication,   
    ]
    permission_classes = [
        IsAuthenticated,
    ]

    def get(self, request, pk):
        deploy = (
            Deploy.objects
            .select_related("service", "service__user")
            .filter(pk=pk)
            .first()
        )

        if not deploy:
            raise Http404("Deployment not found.")

        user = request.user

        is_admin = user.is_staff or user.is_superuser
        is_owner = (
            deploy.service_id
            and getattr(deploy.service, "user_id", None) == user.id
        )

        if not (is_admin or is_owner):
            raise Http404("Deployment not found.")

        if not deploy.zip_file:
            raise Http404("No ZIP file available for this deployment.")

        try:
            file_path = Path(deploy.zip_file.path)
            if not file_path.exists():
                raise Http404("ZIP file not found on disk.")
        except (ValueError, OSError):
            raise Http404("ZIP file not accessible.")

        file_handle = deploy.zip_file.open("rb")

        filename = Path(deploy.zip_file.name).name

        response = FileResponse(
            file_handle,
            as_attachment=True,
            filename=filename,
            content_type="application/zip",
        )

        response["Content-Length"] = deploy.zip_file.size
        response["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response["Pragma"] = "no-cache"
        response["Expires"] = "0"

        return response