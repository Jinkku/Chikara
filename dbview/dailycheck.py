
from django.shortcuts import redirect
from dbview.models import User
from django.utils.deprecation import MiddlewareMixin
from django.http import HttpResponseForbidden
from Chikara.views import checklogin

class CheckUserAuthMiddleware(MiddlewareMixin):
    def process_request(self, request):
        # Check if the user is authenticated (you could use other conditions here)
        username = request.COOKIES.get('username')
        password = request.COOKIES.get('password')  # Get the session ID (assuming this is how it's stored)

            # Use the checklogin function to verify the credentials
        accept = checklogin(username, password)[0]
            
        # Where in the world they're playing from today (Chikara/countries.py): website cookies, or the game's
        # Username / Password headers (checked at most once a day per player).
        try:
            from Chikara import countries
            if accept and username:
                countries.note(request, username)
            elif request.META.get("HTTP_USERNAME") and countries.pending(request.META.get("HTTP_USERNAME")):
                from moderation import service
                u = service.request_user(request)
                if u is not None:
                    countries.note(request, u.username)
        except Exception:
            import sentry_sdk
            sentry_sdk.capture_exception()

        if not accept and username != None and password != None:
            # If the credentials are invalid, revoke session and cookies
            request.session.flush()  # Clear the session
            response = redirect(request.META.get('HTTP_REFERER', '/'))  # Redirect to the previous URL or homepage
            response.delete_cookie('username')
            response.delete_cookie('password')
            return response  # Return the response (user will be redirected)
