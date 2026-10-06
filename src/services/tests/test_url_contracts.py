from django.urls import resolve


def test_canonical_service_status_api_route_is_exposed():
    match = resolve("/api/services/service_status/")
    assert match.url_name == "api_service_status"


def test_legacy_service_status_route_remains_available():
    match = resolve("/services/service_status/")
    assert match.url_name == "service_status"
