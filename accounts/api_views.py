from django.contrib.auth import authenticate, login as django_login, logout as django_logout
from django.db import transaction
from django.middleware.csrf import get_token

from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from .api_serializers import UserProfileReadSerializer, UserProfileUpdateSerializer
from .forms import RegisterForm
from .models import UserProfile


class SessionCSRFAPIView(APIView):
    """Require CSRF for session-based unsafe requests, including anonymous ones."""

    authentication_classes = (SessionAuthentication,)

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)

        # SessionAuthentication checks CSRF after identifying a logged-in user.
        # Login/register/logout also need a check when the request is anonymous.
        if request.method not in ('GET', 'HEAD', 'OPTIONS', 'TRACE') and not request.user.is_authenticated:
            SessionAuthentication().enforce_csrf(request)


class CsrfTokenAPIView(APIView):
    """Issue a CSRF cookie and a masked token for Flutter clients."""

    authentication_classes = ()
    permission_classes = (AllowAny,)
    renderer_classes = (JSONRenderer,)

    def get(self, request):
        token = get_token(request._request)
        return Response({'csrf_token': token})


class RegisterAPIView(SessionCSRFAPIView):
    permission_classes = (AllowAny,)
    renderer_classes = (JSONRenderer,)

    def post(self, request):
        if not hasattr(request.data, 'get'):
            return Response(
                {'detail': 'Body request harus berupa object.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        form = RegisterForm(data=request.data)
        if not form.is_valid():
            return Response(
                {'errors': form.errors.get_json_data()},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            user = form.save()
            user.userprofile.role = form.cleaned_data['role']
            user.userprofile.save(update_fields=['role'])
            form.save_role_profile(user)

        # Match website behavior: a new account starts an authenticated session.
        django_login(request._request, user)
        profile_data = UserProfileReadSerializer(user.userprofile).data
        return Response(
            {
                'detail': 'Registrasi berhasil.',
                'profile': profile_data,
                # login() rotates the CSRF secret; return a token for the new session.
                'csrf_token': get_token(request._request),
            },
            status=status.HTTP_201_CREATED,
        )


class LoginAPIView(SessionCSRFAPIView):
    permission_classes = (AllowAny,)
    renderer_classes = (JSONRenderer,)

    def post(self, request):
        if not hasattr(request.data, 'get'):
            return Response(
                {'detail': 'Body request harus berupa object.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        username = request.data.get('username')
        password = request.data.get('password')
        user = authenticate(
            request=request._request,
            username=username,
            password=password,
        )
        if user is None:
            return Response(
                {'detail': 'Username atau password salah.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        profile = getattr(user, 'userprofile', None)
        if profile is None:
            # Do not create or guess a profile during login; the profile API
            # uses the same safe missing-profile behavior.
            return Response(
                {'detail': 'Profil pengguna tidak tersedia.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        django_login(request._request, user)
        return Response(
            {
                'detail': 'Login berhasil.',
                'profile': UserProfileReadSerializer(profile).data,
                'csrf_token': get_token(request._request),
            },
            status=status.HTTP_200_OK,
        )


class LogoutAPIView(SessionCSRFAPIView):
    permission_classes = (AllowAny,)
    renderer_classes = (JSONRenderer,)

    def post(self, request):
        django_logout(request._request)
        return Response(
            {'detail': 'Logout berhasil.'},
            status=status.HTTP_200_OK,
        )


class ReadProfileAPIView(APIView):
    """Return the profile belonging to the session-authenticated user."""

    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsAuthenticated,)
    renderer_classes = (JSONRenderer,)

    def get(self, request):
        try:
            profile = request.user.userprofile
        except UserProfile.DoesNotExist:
            return Response(
                {'detail': 'Profil pengguna tidak tersedia.'},
                status=404,
            )

        serializer = UserProfileReadSerializer(profile)
        return Response(serializer.data)

    def patch(self, request):
        try:
            profile = request.user.userprofile
        except UserProfile.DoesNotExist:
            return Response(
                {'detail': 'Profil pengguna tidak tersedia.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        with transaction.atomic():
            serializer = UserProfileUpdateSerializer(
                profile,
                data=request.data,
                partial=True,
            )
            serializer.is_valid(raise_exception=True)
            updated_profile = serializer.save()

        return Response(UserProfileReadSerializer(updated_profile).data)
