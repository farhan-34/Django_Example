from django.db import models
from django.contrib.auth.models import AbstractUser, Group, Permission
from datetime import date
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.core.validators import MaxValueValidator, MinValueValidator
from django.utils import timezone
from typing import Optional


class CustomUser(AbstractUser):
    REQUIRED_FIELDS = ["username"]
    USERNAME_FIELD = "email"
    email = models.EmailField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        pass

    groups = models.ManyToManyField(
        Group,
        verbose_name='groups',
        blank=True,
        related_name='custom_user_set',  # Choose a unique related_name
        help_text=(
            'The groups this user belongs to. A user will get all permissions '
            'granted to each of their groups.'
        ),
        related_query_name='custom_user',
    )

    user_permissions = models.ManyToManyField(
        Permission,
        verbose_name='user permissions',
        blank=True,
        related_name='custom_user_set',  # Choose a unique related_name
        help_text=(
            'Specific permissions for this user.'
        ),
        related_query_name='custom_user',
    )

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        if not self.is_superuser:
            self.set_password(self.password)
        return super().save(*args, **kwargs)


class Procedure(models.Model):
    code = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    def __str__(self) -> str:
        return self.code


class ProcedureHistory(models.Model):
    procedure = models.ForeignKey(Procedure, on_delete=models.CASCADE)
    price = models.DecimalField(decimal_places=2, max_digits=10)
    currency = models.CharField(max_length=10, default="€")
    start_date = models.DateField()
    end_date = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Practitioner(models.Model):
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class Source(models.Model):
    name = models.CharField(max_length=255)
    location = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField()

    def __str__(self) -> str:
        return self.name


class AbstractedVisit(models.Model):
    STATUS_CHOICES = [("Valid", "Valid"), ("New", "New"), ("Fixed", "Fixed")]
    visit_index = models.BigIntegerField()
    visit_date = models.DateField()
    name = models.CharField(max_length=255)
    patient_id = models.UUIDField(unique=True)
    patient_name = models.CharField(max_length=255)
    birthday = models.DateField(null=True, blank=True)
    passage_iep = models.BigIntegerField(null=True, blank=True)
    visit_start = models.DateTimeField()
    visit_end = models.DateTimeField()
    source = models.ForeignKey(Source, on_delete=models.DO_NOTHING, null=True)
    moyen_arrive = models.CharField(max_length=255, blank=True)
    status = models.CharField(choices=STATUS_CHOICES, max_length=20)
    visit_number = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    practitioner_raw = models.TextField(blank=True, null=True)
    import_file = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        abstract = True


class Visit(AbstractedVisit):
    performing_practitioner = models.ForeignKey(
        Practitioner,
        on_delete=models.DO_NOTHING,
        related_name="sub_practitioner",
        blank=True,
        null=True,
    )
    practitioner_on_file = models.ForeignKey(
        Practitioner,
        on_delete=models.DO_NOTHING,
        related_name="practitioner",
        blank=True,
        null=True,
    )


class VisitProcedure(models.Model):
    OPTION_CHOICES = [
        ("P", "P"),
        ("Q", "Q"),
        ("S", "S"),
    ]
    STATUS_CHOICES = [
        ("Paid", "Paid"),
        ("Unpaid", "Unpaid"),
        ("Partial", "Partial"),
        ("Negative", "Negative"),
    ]
    procedure = models.ForeignKey(Procedure, on_delete=models.CASCADE)
    procedure_price = models.ForeignKey(ProcedureHistory, on_delete=models.CASCADE)
    visit = models.ForeignKey(Visit, on_delete=models.CASCADE)
    imported_price = models.DecimalField(decimal_places=2, max_digits=5)
    currency = models.CharField(max_length=15, default="€")
    option = models.CharField(max_length=50, blank=True, choices=OPTION_CHOICES)
    status = models.CharField(max_length=150, default="Unpaid", choices=STATUS_CHOICES)
    order_index = models.IntegerField(blank=True, null=True, default=0)
    payment_balance = models.DecimalField(decimal_places=2, max_digits=10, default=0)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now=True)
    def __str__(self) -> str:
        return f"code: {self.procedure.code} - visit: {self.visit.visit_number}"
    
    def save(self, *args, **kwargs):
        # Set the status based on the payment_balance
        if self.payment_balance < 0:
            self.status = "Negative"
        elif self.payment_balance == 0:
            self.status = "Unpaid"
        elif self.payment_balance < self.procedure_price.price:
            self.status = "Partial"
        else:
            self.status = "Paid"
        
        super().save(*args, **kwargs)
