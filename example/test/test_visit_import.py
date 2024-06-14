from django.urls import reverse
import pytest
from django.test import RequestFactory
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.messages.storage.fallback import FallbackStorage
from unittest.mock import patch
from example.views import VisitView
from example.models import CustomUser, Visit, VisitProcedure
from django.contrib import messages

@pytest.fixture
def mock_request():
    """Fixture to create a mock request."""
    return RequestFactory().post('visit')

@pytest.fixture
def valid_csv_file():
    """Fixture to create a valid CSV file."""
    csv_content = (
        "Num dossier; Informations du passage->Numéro IEP; Patient->Numéro de sécurité sociale; "
        "Patient->Nom usuel, ou nom de naissance, ou rien si anonyme; Patient->Prénom; Patient->Age; "
        "Informations du passage->Moyen d'arrivée; Informations du passage->moyen d'arrivée; "
        "Informations du passage->Date et heure de début prise en charge médicale; Informations du passage->date et heure de sortie; "
        "Médecin du dossier->Nom et prénom; Actes->NGAP->Réalisateur; Actes->CCAM->Réalisateur; Actes->NGAP->code; "
        "Actes->CCAM->code; Actes->CCAM->Modificateurs; Actes->NGAP->tarif; Actes->CCAM->tarif; Actes->CCAM->date de réalisation;\n"
        '24511722;24511722;291049201930996;GARRIGOS;ILYHAN;3 ans et 1 mois;MOYEN PERSONNEL;MOYEN PERSONNEL;11/03/2024 à 00:26;11/03/2024 7:21;'
        '("FAUCONNIER Ketty", "FAUCONNIER Ketty", "FAUCONNIER Ketty");();("SUN", "FU1", "FPU");();();(40.00, 30.04, 19.61);();();\n'
    )
    return SimpleUploadedFile("test.csv", csv_content.encode('ISO-8859-1'), content_type="text/csv")

@pytest.mark.django_db
def test_successfully_processes_and_imports_valid_csv_file(mock_request, valid_csv_file):
    """Test case for processing and importing a valid CSV file."""
    mock_request.FILES['files'] = valid_csv_file  # Assigning the valid_csv_file directly without extra brackets

    with patch('example.views.Visit.objects.filter') as mock_visit_filter, \
         patch('example.views.Procedure.objects.all') as mock_procedure_all, \
         patch('example.views.Practitioner.objects.all') as mock_practitioner_all, \
         patch('example.views.Source.objects.all') as mock_source_all, \
         patch('example.views.ProcedureHistory.objects.select_related') as mock_procedure_history_select_related, \
         patch('example.views.Visit.objects.bulk_create') as mock_visit_bulk_create, \
         patch('example.views.VisitProcedure.objects.bulk_create') as mock_visit_procedure_bulk_create:

        # Mock filter to return False for visit exists check
        mock_visit_filter.return_value.exists.return_value = False

        # Mock other database queries
        mock_procedure_all.return_value.values.return_value = []
        mock_practitioner_all.return_value.values.return_value = []
        mock_source_all.return_value.first.return_value = None
        mock_procedure_history_select_related.return_value.all.return_value = []

        # Call the view
        view = VisitView.as_view()
        response = view(mock_request)

        # Assertions
        assert response.status_code == 302
        assert mock_visit_bulk_create.called
        assert mock_visit_procedure_bulk_create.called


@pytest.mark.django_db
def test_successfully_processes_and_imports_valid_csv_file_with_non_ascii_characters(mock_request, valid_csv_file):
    """Test case for processing and importing a valid CSV file with non-ASCII characters."""
    mock_request.FILES['files'] = valid_csv_file  # Assigning the valid_csv_file directly without extra brackets

    with patch('example.views.Visit.objects.filter') as mock_visit_filter, \
         patch('example.views.Procedure.objects.all') as mock_procedure_all, \
         patch('example.views.Practitioner.objects.all') as mock_practitioner_all, \
         patch('example.views.Source.objects.all') as mock_source_all, \
         patch('example.views.ProcedureHistory.objects.select_related') as mock_procedure_history_select_related, \
         patch('example.views.Visit.objects.bulk_create') as mock_visit_bulk_create, \
         patch('example.views.VisitProcedure.objects.bulk_create') as mock_visit_procedure_bulk_create:

        # Mock filter to return False for visit exists check
        mock_visit_filter.return_value.exists.return_value = False

        # Mock other database queries
        mock_procedure_all.return_value.values.return_value = []
        mock_practitioner_all.return_value.values.return_value = []
        mock_source_all.return_value.first.return_value = None
        mock_procedure_history_select_related.return_value.all.return_value = []

        # Call the view
        view = VisitView.as_view()
        response = view(mock_request)

        # Assertions
        assert response.status_code == 302
        assert mock_visit_bulk_create.called
        assert mock_visit_procedure_bulk_create.called


@pytest.mark.django_db
def test_no_files_uploaded(mock_request):
    factory = RequestFactory()
    url = reverse('visit')  # Assuming 'visit_import' is your URL name for the import view
    request = factory.post(url)
    request.FILES.setlist('files', [])  # Set an empty list of files

    with patch('example.views.Visit.objects.filter'), \
         patch('example.views.Procedure.objects.all'), \
         patch('example.views.Practitioner.objects.all'), \
         patch('example.views.Source.objects.all'), \
         patch('example.views.ProcedureHistory.objects.select_related'), \
         patch('example.views.Visit.objects.bulk_create'), \
         patch('example.views.VisitProcedure.objects.bulk_create'):

        response = VisitView.as_view()(request)

        assert response.status_code == 500