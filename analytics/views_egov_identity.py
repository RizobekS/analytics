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
        lang_id = request.data.get("langId", 1)

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
            person = get_person_by_pinpp(pinpp=pinpp, birth_date=birth_date, lang_id=lang_id)
        except EgovApiError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response({"detail": "EGOV service error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        first_name = (
                person.get("namelat")
                or ""
        )
        last_name = (
                person.get("surnamelat")
                or ""
        )
        middle_name = (
                person.get("patronymlat")
                or ""
        )

        full_name = " ".join([last_name, first_name, middle_name]).strip()

        payload = {
            "pinpp": pinpp,
            "birth_date": birth_date,
            "full_name": full_name,
            "first_name": first_name,
            "last_name": last_name,
            "middle_name": middle_name,
        }

        # raw — только для отладки (иначе это утечки персональных данных)
        debug = request.query_params.get("debug") == "1"
        if debug:
            payload["raw"] = person

        return Response(payload, status=status.HTTP_200_OK)
