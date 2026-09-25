"""
Production-ready Wagtail bootstrap:

- Ensure a Site + root HomePage exist
- Remove the default "Welcome to your new Wagtail site!" page if present
- Set site hostname from DOMAIN_NAME / localhost

Usage:
    python manage.py setup_wagtail_site
"""
from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Create root HomePage, wire Site, delete Wagtail default welcome page"

    @transaction.atomic
    def handle(self, *args, **options):
        from wagtail.models import Page, Site
        from cms.models import HomePage

        # Delete default welcome page content if it exists (title match / default slug)
        deleted = 0
        for page in Page.objects.filter(depth__gte=2).exclude(content_type__model="homepage"):
            title = (page.title or "").lower()
            if "welcome" in title or page.slug in ("home", "welcome"):
                # Prefer converting rather than cascade-delete site tree carelessly
                self.stdout.write(f"Removing default page: {page.title!r} (id={page.id})")
                page.delete()
                deleted += 1

        root = Page.get_first_root_node()
        if root is None:
            self.stderr.write("No Wagtail root node — run migrations first.")
            return

        home = HomePage.objects.child_of(root).first()
        if home is None:
            home = HomePage(title="Home", slug="home", body="")
            root.add_child(instance=home)
            home.save_revision().publish()
            self.stdout.write(self.style.SUCCESS(f"Created HomePage id={home.id}"))
        else:
            # Ensure published
            if not home.live:
                home.save_revision().publish()
            self.stdout.write(f"HomePage already exists id={home.id}")

        hostname = (
            getattr(settings, "DOMAIN_NAME", None)
            or getattr(settings, "API_DOMAIN_NAME", None)
            or "localhost"
        )
        hostname = str(hostname).split(":")[0] or "localhost"
        port = 80 if not settings.DEBUG else 8000

        site = Site.objects.filter(is_default_site=True).first()
        if site is None:
            site = Site.objects.create(
                hostname=hostname,
                port=port,
                root_page=home,
                is_default_site=True,
                site_name=getattr(settings, "WAGTAIL_SITE_NAME", "Admin"),
            )
            self.stdout.write(self.style.SUCCESS(f"Created Site {site}"))
        else:
            site.hostname = hostname
            site.port = port
            site.root_page = home
            site.site_name = getattr(settings, "WAGTAIL_SITE_NAME", site.site_name or "Admin")
            site.save()
            self.stdout.write(self.style.SUCCESS(f"Updated Site {site}"))

        # Clean any remaining draft "Welcome" pages under root
        for p in Page.objects.child_of(root).exclude(id=home.id):
            if "welcome" in (p.title or "").lower():
                self.stdout.write(f"Deleting leftover page {p.title!r}")
                p.delete()
                deleted += 1

        self.stdout.write(self.style.SUCCESS(f"Done. deleted_default_pages={deleted}"))
