from django.urls import path
from . import apis

urlpatterns = [
    path("departments/", apis.DepartmentListAPIView.as_view(), name="ticket-departments"),
    path("context/", apis.MyTicketContextAPIView.as_view(), name="ticket-context"),
    path("", apis.MyTicketListCreateAPIView.as_view(), name="my-tickets"),
    path("<int:pk>/", apis.TicketDetailAPIView.as_view(), name="ticket-detail"),
    path("<int:pk>/close/", apis.TicketCloseAPIView.as_view(), name="ticket-close"),
    path("<int:pk>/messages/", apis.TicketMessageCreateAPIView.as_view(), name="ticket-messages"),
    path("attachments/<int:pk>/download/", apis.AttachmentDownloadAPIView.as_view(), name="ticket-attachment-download"),
    path("staff/", apis.StaffTicketListAPIView.as_view(), name="staff-tickets"),
    path("staff/<int:pk>/status/", apis.StaffTicketStatusAPIView.as_view(), name="staff-ticket-status"),
    path("staff/<int:pk>/priority/", apis.StaffTicketPriorityAPIView.as_view(), name="staff-ticket-priority"),
    path("staff/<int:pk>/department/", apis.StaffTicketAssignDepartmentAPIView.as_view(), name="staff-ticket-department"),
]
