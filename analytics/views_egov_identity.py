# analytics/views_egov_identity.py
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .services import get_person_by_pinpp, birth_date_from_pinpp, EgovApiError


class EgovPinppLookupView(APIView):
    """
    POST /api/egov/pinpp/
    body: {"pinpp": "...", "birth_date": "YYYY-MM-DD", "langId": 1}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        pinpp = (request.data.get("pinpp") or "").strip()
        birth_date = (request.data.get("birth_date") or "").strip()

        if not pinpp:
            return Response(
                {"detail": "pinpp is required"},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        if not birth_date:
            try:
                birth_date = birth_date_from_pinpp(pinpp)
            except EgovApiError:
                # мягкий фейл: просто просим дату рождения
                return Response(
                    {"detail": "birth_date is required (could not derive from pinpp)"},
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )

        try:
            person = get_person_by_pinpp(pinpp=pinpp, birth_date=birth_date)
        except EgovApiError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response({"detail": "EGOV service error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        full_name = person.get("full_name") or person.get("fio") or ""
        first_name = person.get("first_name") or ""
        last_name = person.get("sur_name") or person.get("last_name") or ""
        middle_name = person.get("mid_name") or person.get("middle_name") or ""

        return Response(
            {
                "pinpp": pinpp,
                "birth_date": birth_date,
                "full_name": full_name,
                "first_name": first_name,
                "last_name": last_name,
                "middle_name": middle_name,
                "raw": person,
            },
            status=status.HTTP_200_OK,
        )
