"""Modular Agent API implementation.

Domain modules keep the HTTP facade thin while application.py remains the
control-plane boundary for existing Service/Deploy/Volume/Network engines.
"""
from .base import AgentAPIView, AgentPublicAPIView, AgentSecuredAPIView, AgentPage
from .identity import AgentRootView, AgentExchangeView, AgentMeView, AgentCapabilitiesView, AgentManifestView, AgentOpenAPIView
from .services import ServiceListCreateView, ServiceDetailView, ServiceFromPlanView, ServiceActionView, ServiceStatusView, ServiceLogsView, ServiceLogsExportView, ServiceMetricsView
from .plans import PlanListView, PlanDetailView, PlanManagementView, PlanApplyView
from .networks import NetworkListCreateView, NetworkDetailView
from .volumes import VolumeListCreateView, VolumeDetailView
from .deployments import DeploymentListCreateView, DeploymentDetailView, DeploymentUploadView, DeploymentActionView, DeploymentRollbackView, DeploymentLogsView, DeploymentLogsExportView
from .configuration import ConfigurationView, EnvironmentView, SecretsView, EndpointConfigView, NetworkAttachmentsView, RevisionListView, RevisionDetailView, RevisionRollbackView, DatabaseBindingsView
from .shell import ShellInfoView, ShellSessionView, ShellCommandView, ShellCloseView, ShellReplaceView, ShellFileView
from .extended import DeploymentHelpView, DeploymentInspectView, DatabaseCredentialsView

__all__ = [
    name for name in (
        "AgentAPIView", "AgentPublicAPIView", "AgentSecuredAPIView", "AgentPage",
        "AgentRootView", "AgentExchangeView", "AgentMeView", "AgentCapabilitiesView", "AgentManifestView", "AgentOpenAPIView",
        "ServiceListCreateView", "ServiceDetailView", "ServiceFromPlanView", "ServiceActionView", "ServiceStatusView", "ServiceLogsView", "ServiceLogsExportView", "ServiceMetricsView",
        "PlanListView", "PlanDetailView", "PlanManagementView", "PlanApplyView",
        "NetworkListCreateView", "NetworkDetailView", "VolumeListCreateView", "VolumeDetailView",
        "DeploymentListCreateView", "DeploymentDetailView", "DeploymentUploadView", "DeploymentActionView", "DeploymentRollbackView", "DeploymentLogsView", "DeploymentLogsExportView",
        "ConfigurationView", "EnvironmentView", "SecretsView", "EndpointConfigView", "NetworkAttachmentsView", "RevisionListView", "RevisionDetailView", "RevisionRollbackView", "DatabaseBindingsView",
        "ShellInfoView", "ShellSessionView", "ShellCommandView", "ShellCloseView", "ShellReplaceView", "ShellFileView",
        "DeploymentHelpView", "DeploymentInspectView", "DatabaseCredentialsView",
    )
]
