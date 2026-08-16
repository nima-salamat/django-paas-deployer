"""Ticket REST API."""
from __future__ import annotations
import logging
from django.db.models import Count, Prefetch, Q
from django.http import FileResponse, Http404
from django.utils import timezone
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination
from .models import Department, DepartmentMembership, Ticket, TicketMessage, TicketAttachment
from .permissions import IsTicketOwnerOrStaff, IsStaffOrSuperuser, CanManageTicket
from .serializers import (
    DepartmentSerializer, TicketListSerializer, TicketDetailSerializer,
    TicketCreateSerializer, TicketMessageCreateSerializer, TicketMessageSerializer,
    TicketStatusSerializer, TicketPrioritySerializer, TicketAssignDepartmentSerializer,
)
from .utils import check_rate_limit, get_ticket_setting, validate_upload_file, safe_filename, validate_ticket_quota

logger = logging.getLogger("tickets.apis")

def ok(message="success", data=None, http_status=status.HTTP_200_OK):
    body = {"success": True, "message": message}
    if data is not None:
        body["data"] = data
    return Response(body, status=http_status)

def err(message, http_status=status.HTTP_400_BAD_REQUEST, extra=None):
    body = {"success": False, "message": message}
    if extra:
        body.update(extra)
    return Response(body, status=http_status)

class TicketPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 50

