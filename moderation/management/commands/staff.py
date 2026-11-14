"""Manage the Qlute team from the shell (needed once, to make the first admin).

    python manage.py staff list
    python manage.py staff add NAME [--role admin|mod]
    python manage.py staff remove NAME
"""
from django.core.management.base import BaseCommand, CommandError

from dbview.models import User
from moderation.models import StaffMember


class Command(BaseCommand):
    help = "List, add or remove Qlute team members (they get the team medal and the admin panel)."

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["list", "add", "remove"])
        parser.add_argument("username", nargs="?")
        parser.add_argument("--role", choices=[r for r, _ in StaffMember.ROLES], default=StaffMember.ROLE_ADMIN)

    def handle(self, action, username=None, role=None, **kw):
        if action == "list":
            for s in StaffMember.objects.order_by("role", "username"):
                self.stdout.write(f"{s.username}\t{s.role}")
            return
        if not username:
            raise CommandError("Give a username.")
        if not User.objects.filter(username=username).exists():
            raise CommandError(f"There's no player called {username}.")
        if action == "add":
            StaffMember.objects.update_or_create(username=username, defaults={"role": role, "added_by": "(shell)"})
            self.stdout.write(f"{username} is now {role}.")
        else:
            StaffMember.objects.filter(username=username).delete()
            self.stdout.write(f"{username} is no longer on the team.")
