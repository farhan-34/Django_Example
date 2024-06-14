from datetime import datetime, timedelta
from decimal import Decimal
import io
from django.http import HttpResponse
from django.utils import timezone
import pandas as pd
from django.views import View
from django.contrib import messages
from django.shortcuts import redirect, render
from django.db import models
from django.db.models import Prefetch
from django.core.paginator import Paginator
import uuid

from example.fillters import VisitFilter
from example.models import Practitioner, Procedure, ProcedureHistory, Source, Visit, VisitProcedure


class VisitView(View):
    template_name = "example/visit.html"

    def get(self, request, *args, **kwargs):
        visit_filter = VisitFilter(
            request.GET,
            queryset=Visit.objects.select_related(
                "source", "practitioner_on_file", "practitioner_on_file__user"
            )
            .all()
            .order_by("-created_at")
            .values(
                "visit_date",
                "patient_name",
                "source__name",
                "visit_index",
                "visit_number",
                "status",
                "id",
                "practitioner_on_file__user__username",
                "practitioner_on_file__user__first_name",
                "practitioner_on_file__user__last_name",
                "performing_practitioner__user__first_name",
                "performing_practitioner__user__last_name",
                "import_file"
            ),
        )
        visits = visit_filter.qs

        visits_with_procedures = Visit.objects.prefetch_related(
            Prefetch(
                "visitprocedure_set",
                queryset=VisitProcedure.objects.select_related(
                    "procedure",
                    "procedure_price",
                ),
            )
        )

        visit_procedures_dict = {
            visit.id: {
                "procedure": [vp.procedure for vp in visit.visitprocedure_set.all()],
                "imported_price": sum(
                    vp.imported_price for vp in visit.visitprocedure_set.all()
                ),
                "catalog_price": sum(
                    vp.procedure_price.price for vp in visit.visitprocedure_set.all()
                ),
            }
            for visit in visits_with_procedures
        }
        final_visits = [
            {
                "pk": visit["id"],
                "source": visit["source__name"],
                "visit_date": visit["visit_date"],
                "name": visit["patient_name"],
                "practitioner": visit["practitioner_on_file__user__username"],
                "procedures": visit_procedures_dict.get(visit["id"])["procedure"],
                "catalog_price": Money(
                    visit_procedures_dict.get(visit["id"])["catalog_price"], "EUR"
                ),
                "price_delta": Money(
                    (visit_procedures_dict.get(visit["id"])["catalog_price"] or 0)
                    - (visit_procedures_dict.get(visit["id"])["imported_price"] or 0),
                    "EUR",
                ),
                "visit_index": visit["visit_index"],
                "visit_number": visit["visit_number"],
                "status": visit["status"],
                "practitioner__user__first_name": visit[
                    "practitioner_on_file__user__first_name"
                ],
                "practitioner__user__last_name": visit[
                    "practitioner_on_file__user__last_name"
                ],
                "sub_practitioner__user__first_name": visit[
                    "performing_practitioner__user__first_name"
                ],
                "sub_practitioner__user__last_name": visit[
                    "performing_practitioner__user__last_name"
                ],
                "import_file": visit["import_file"]
            }
            for visit in visits
        ]

        total_amount = sum(visit["catalog_price"].amount for visit in final_visits)
        negative_delta = sum(
            visit["price_delta"].amount
            for visit in final_visits
            if visit["price_delta"].amount < 0
        )
        positive_delta = sum(
            visit["price_delta"].amount
            for visit in final_visits
            if visit["price_delta"].amount > 0
        )
        total_visits = len(visits)

        paginator = Paginator(final_visits, 10)
        page_number = request.GET.get("page")
        page_obj = paginator.get_page(page_number)

        return render(
            request,
            self.template_name,
            {
                "visits": final_visits,
                "page_obj": page_obj,
                "form": visit_filter.form,
                "total_amount": total_amount,
                "negative_delta": negative_delta,
                "positive_delta": positive_delta,
                "total_visits": total_visits,
            },
        )
    
    def post(self, request, *args, **kwargs):
        files = request.FILES.getlist("files")
        if not files:
            return HttpResponse(status=500)
        for file in files:
            # Check if a Visit with the same import_file already exists
            visit_exists = Visit.objects.filter(import_file__endswith=file.name).exists()
            if visit_exists:
                messages.error(request, f"The file '{file.name}' has already been processed.")
                continue

            # Read the file content directly
            file_content = file.read()

            try:
                # Decode content using ISO-8859-1 encoding
                decoded_content = file_content.decode("ISO-8859-1")

                # Create a file-like object from the decoded content
                data = io.StringIO(decoded_content)

                df = pd.read_csv(data, delimiter=";")
                clean_column_names = [col.strip() for col in df.columns]
                df.columns = clean_column_names

                self.insert_visit_in_db(df, file.name)

            except (UnicodeDecodeError, ValueError) as e:
                messages.error(request, f"Error while uploading the file: {e.__cause__}")
                return redirect("visit")  # Redirect to appropriate page upon error

        return redirect("visit")  # Redirect after processing all files

    def _parse_visit_date(self, date):
        if not date:
            return None
        formatted_date = date.replace("à", "")
        naive_datetime = datetime.strptime(formatted_date, "%d/%m/%Y %H:%M")
        return timezone.make_aware(naive_datetime, timezone.get_default_timezone())

    def _create_csv_mapping_buffer(self, row, index, filename):
        birthday = None
        if row["Patient->Age"]:
            if isinstance(row["Patient->Age"], str):
                age_years = int(row["Patient->Age"].split(" ")[0])
            else:
                age_years = int(row["Patient->Age"])  # If it's already an integer
            birthday = datetime.now() - timedelta(days=age_years * 365)
        csv_mapping_buffer = {
            #format this dateime to YYYYMMDD
            "import_file": f"{datetime.now().strftime('%d/%m/%Y')}_{filename}",
            "visit_index": index,
            "visit_number": row["Num dossier"],
            "visit_date": self._parse_visit_date(
                row[
                    "Informations du passage->Date et heure de début prise en charge médicale"
                ]
            ),
            "visit_start": self._parse_visit_date(
                row[
                    "Informations du passage->Date et heure de début prise en charge médicale"
                ]
            ),
            "visit_end": self._parse_visit_date(
                row["Informations du passage->date et heure de sortie"]
            ),
            "patient_name": f"{row['Patient->Prénom']} {row['Patient->Nom usuel, ou nom de naissance, ou rien si anonyme']}",
            "passage_iep": (
                int(row["Informations du passage->Numéro IEP"])
                if pd.notna(row["Informations du passage->Numéro IEP"])
                else None
            ),
            "moyen_arrive": row["Informations du passage->moyen d'arrivée"],
            "patient_id": uuid.uuid4(),
            "birthday": birthday,
        }

        return csv_mapping_buffer

    def _get_practitioners(self, row, practitioner_mapping):
        normalized_main_practitioner_name = row["Médecin du dossier->Nom et prénom"]
        # TODO: Ask if main practitioner not present use ngcap practitioner
        if not normalized_main_practitioner_name:
            normalized_main_practitioner_name = (
                row["Actes->NGAP->Réalisateur"].strip("()").split(",")[0]
            )
        normalized_sub_practitioner_name = (
            row["Actes->NGAP->Réalisateur"].strip("()").split(",")[0]
        )

        main_practitioner = practitioner_mapping.get(
            normalized_main_practitioner_name, None
        )
        sub_practitioner = practitioner_mapping.get(
            normalized_sub_practitioner_name, None
        )
        return main_practitioner, sub_practitioner

    def _clean_procedure_data(self, data, split_expression=",", strip_expression="()"):
        return data.strip(strip_expression).split(split_expression)

    def _create_visit_procedure(
        self,
        index,
        code,
        tarif,
        visit,
        practitioners,
        main_practitioner,
        practitioner_mapping,
        procedure_mapping,
        procedure_price_mapping,
        **kwargs,
    ):
        if not code:
            return None

        imported_price = Decimal(tarif) if tarif else 0
        practitioner = ""
        if index < len(practitioners):
            practitioner = practitioner_mapping.get(practitioners[index].strip(), None)

        formatted_code = code.strip().replace('"', "")
        if formatted_code not in procedure_mapping:
            return None

        price_list = procedure_price_mapping.get(formatted_code, [])
        visit_start = visit.visit_start.date()
        price_id = None
        for ph in price_list:
            if ph["start_date"] <= visit_start and (
                ph["end_date"] is None or ph["end_date"] >= visit_start
            ):
                price_id = ph["id"]
                break
        if not price_id:
            return None

        return VisitProcedure(
            procedure_id=procedure_mapping[formatted_code],
            visit=visit,
            imported_price=imported_price,
            procedure_price_id=price_id,
            practitioner_on_file_id=main_practitioner,
            performing_practitioner_id=practitioner,
            **kwargs,
        )

    def insert_visit_in_db(self, df, filename):
        procedures = Procedure.objects.all().values("id", "code")
        procedure_mapping = {
            procedure["code"]: procedure["id"] for procedure in procedures
        }

        practitioners = Practitioner.objects.all().values("user__username", "id")
        practitioner_mapping = {
            practitioner["user__username"]: practitioner["id"]
            for practitioner in practitioners
        }

        source = Source.objects.first()  # Adjust as per your actual data structure

        procedure_history = (
            ProcedureHistory.objects.select_related("procedure")
            .order_by("-updated_at")
            .values("procedure__code")
            .annotate(
                price=models.F("price"),
                start_date=models.Min("start_date"),
                end_date=models.Max("end_date"),
                id=models.F("id"),
            )
        )
        procedure_price_mapping = {}
        for ph in procedure_history:
            procedure_price_mapping.setdefault(ph["procedure__code"], []).append(ph)

        visits = []
        visit_procedures = []

        for index, row in df.iterrows():
            mapped_visit_fields = self._create_csv_mapping_buffer(row, index, filename)

            main_practitioner, sub_practitioner = self._get_practitioners(
                row, practitioner_mapping
            )

            visit = Visit(
                **mapped_visit_fields,
                status="New",
                practitioner_on_file_id=main_practitioner,
                performing_practitioner_id=sub_practitioner,
                source=source,
            )
            visits.append(visit)

            ngap_codes = self._clean_procedure_data(row["Actes->NGAP->code"])
            ccam_codes = self._clean_procedure_data(row["Actes->CCAM->code"])
            ngap_tarifs = self._clean_procedure_data(row["Actes->NGAP->tarif"])
            ccam_tarifs = self._clean_procedure_data(row["Actes->CCAM->tarif"])
            ccam_modifiers = self._clean_procedure_data(
                row.get("Actes->CCAM->Modificateurs", "")
            )
            ngap_practitioners = self._clean_procedure_data(
                row.get("Actes->NGAP->Réalisateur", "")
            )
            ccam_practitioners = self._clean_procedure_data(
                row.get("Actes->CCAM->Réalisateur", "")
            )

            for i, (ngap_code, ngap_tarif) in enumerate(zip(ngap_codes, ngap_tarifs)):
                ngcap_procedure = self._create_visit_procedure(
                    i,
                    ngap_code,
                    ngap_tarif,
                    visit,
                    ngap_practitioners,
                    main_practitioner,
                    practitioner_mapping,
                    procedure_mapping,
                    procedure_price_mapping,
                )
                if ngcap_procedure:
                    visit_procedures.append(ngcap_procedure)

            for i, (ccam_code, ccam_tarif) in enumerate(zip(ccam_codes, ccam_tarifs)):
                modifier = (
                    ccam_modifiers[i].strip().replace('"', "")
                    if i < len(ccam_modifiers)
                    else ""
                )
                option_dict = {"option": modifier}

                ccam_procedure = self._create_visit_procedure(
                    i,
                    ccam_code,
                    ccam_tarif,
                    visit,
                    ccam_practitioners,
                    main_practitioner,
                    practitioner_mapping,
                    procedure_mapping,
                    procedure_price_mapping,
                    **option_dict,
                )
                if ccam_procedure:
                    visit_procedures.append(ccam_procedure)

        Visit.objects.bulk_create(visits, batch_size=1000)
        VisitProcedure.objects.bulk_create(visit_procedures, batch_size=1000)