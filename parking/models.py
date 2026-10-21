from django.db import models
from django.contrib.auth.models import AbstractUser


# ---------------------------------------------------------
# USER
# ---------------------------------------------------------

class User(AbstractUser):
    ROLE_CHOICES = (
        ('user', 'User'),
        ('manager', 'Parking Manager'),
        ('admin', 'Admin'),
    )

    APPROVAL_STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='user'
    )

    phone = models.CharField(
        max_length=15,
        blank=True
    )

    approval_status = models.CharField(
        max_length=20,
        choices=APPROVAL_STATUS_CHOICES,
        default='pending'
    )

    def __str__(self):
        return self.username



# ---------------------------------------------------------
# PARKING LOCATION
# ---------------------------------------------------------


class ParkingLocation(models.Model):

    manager = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='parking_location',
        limit_choices_to={'role': 'manager'}
    )

    name = models.CharField(max_length=150)

    address = models.TextField()

    city = models.CharField(max_length=100)

    status = models.BooleanField(default=True)
    # Manager-configured grace period before marking a no-show
    grace_period_minutes = models.PositiveIntegerField(default=30)

    # Two-wheeler parking rates
    two_wheeler_base_rate = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=30.00
    )

    two_wheeler_extra_hour_rate = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=10.00
    )

    # Four-wheeler parking rates
    four_wheeler_base_rate = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=60.00
    )

    four_wheeler_extra_hour_rate = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=20.00
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    


# ---------------------------------------------------------
# PARKING SLOT
# ---------------------------------------------------------

class ParkingSlot(models.Model):

    VEHICLE_TYPE_CHOICES = (
        ('two_wheeler', 'Two Wheeler'),
        ('four_wheeler', 'Four Wheeler'),
    )

    SLOT_STATUS_CHOICES = (
        ('available', 'Available'),
        ('occupied', 'Occupied'),
        ('maintenance', 'Maintenance'),
    )

    location = models.ForeignKey(
        ParkingLocation,
        on_delete=models.CASCADE,
        related_name='slots'
    )

    slot_number = models.CharField(max_length=20)

    vehicle_type = models.CharField(
        max_length=20,
        choices=VEHICLE_TYPE_CHOICES
    )

    is_ev = models.BooleanField(default=False)

    charging_available = models.BooleanField(default=False)

    # NEW
    is_extra = models.BooleanField(default=False)

    status = models.CharField(
        max_length=20,
        choices=SLOT_STATUS_CHOICES,
        default='available'
    )

    def __str__(self):
        return f"{self.location.name} - {self.slot_number}"
# ---------------------------------------------------------
# BOOKING
# ---------------------------------------------------------

class Booking(models.Model):

    STATUS_CHOICES = (
        ('reserved', 'Reserved'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='bookings',
        limit_choices_to={'role': 'user'}
    )

    location = models.ForeignKey(
        ParkingLocation,
        on_delete=models.CASCADE,
        related_name='bookings'
    )

    slot = models.ForeignKey(
        ParkingSlot,
        on_delete=models.CASCADE,
        related_name='bookings'
    )

    vehicle_type = models.CharField(
        max_length=20,
        choices=ParkingSlot.VEHICLE_TYPE_CHOICES
    )

    vehicle_number = models.CharField(max_length=20)

    booking_date = models.DateField()

    expected_arrival = models.DateTimeField()

    reservation_expiry = models.DateTimeField()

    actual_entry_time = models.DateTimeField(
        null=True,
        blank=True
    )

    actual_exit_time = models.DateTimeField(
        null=True,
        blank=True
    )

    qr_code = models.CharField(
        max_length=255,
        unique=True
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='reserved'
    )
        # Grace period captured when the booking is created
    applied_grace_minutes = models.PositiveIntegerField(
        default=0
    )

    expiry_reminder_sent = models.BooleanField(
        default=False
    )

    no_show_processed = models.BooleanField(
        default=False
    )
    no_show = models.BooleanField(
        default=False
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f"Booking #{self.id} - {self.vehicle_number}"


class Payment(models.Model):

    PAYMENT_STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('failed', 'Failed'),
    )

    PAYMENT_METHOD_CHOICES = (
        ('cash', 'Cash'),
        ('online', 'Online'),
        ('gpay', 'GPay'),
        ('phonepe', 'PhonePe'),
        ('upi', 'UPI'),
    )

    REFUND_STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('refunded', 'Refunded'),
        ('not_applicable', 'Not Applicable'),
    )

    booking = models.OneToOneField(
        Booking,
        on_delete=models.CASCADE,
        related_name='payment'
    )

    # Advance payment made during booking
    advance_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    advance_payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        default='online'
    )

    advance_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default='pending'
    )

    advance_payment_time = models.DateTimeField(
        null=True,
        blank=True
    )

    # Balance payment calculated at exit
    balance_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    balance_payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHOD_CHOICES,
        default='cash'
    )

    balance_payment_time = models.DateTimeField(
        null=True,
        blank=True
    )

    balance_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default='pending'
    )

    # Final parking charge based on actual duration
    final_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    # Cancellation refund and charge
    refund_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    cancellation_charge = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    refund_status = models.CharField(
        max_length=20,
        choices=REFUND_STATUS_CHOICES,
        default='not_applicable'
    )

    def __str__(self):
        return f"Payment for Booking #{self.booking.id}"

# ---------------------------------------------------------
# COMPLAINT
# ---------------------------------------------------------

class Complaint(models.Model):

    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='complaints',
        limit_choices_to={'role': 'user'}
    )

    location = models.ForeignKey(
        ParkingLocation,
        on_delete=models.CASCADE,
        related_name='complaints'
    )

    booking = models.ForeignKey(
        Booking,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='complaints'
    )

    subject = models.CharField(max_length=200)

    description = models.TextField()

    photo = models.ImageField(
        upload_to='complaints/',
        null=True,
        blank=True
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )
    is_valid = models.BooleanField(
        default=False
    )

    verified_at = models.DateTimeField(
        null=True,
        blank=True
    )

    response = models.TextField(
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return self.subject

    
# ---------------------------------------------------------
# WARNING RECORD
# ---------------------------------------------------------

class WarningRecord(models.Model):

    WARNING_TYPE_CHOICES = (
        ('customer_no_show', 'Customer No-Show'),
        ('manager_complaints', 'Manager Complaints'),
    )

    LEVEL_CHOICES = (
        ('warning', 'Warning'),
        ('final_warning', 'Final Warning'),
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='warning_records'
    )

    location = models.ForeignKey(
        ParkingLocation,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='warning_records'
    )

    warning_type = models.CharField(
        max_length=30,
        choices=WARNING_TYPE_CHOICES
    )

    level = models.CharField(
        max_length=20,
        choices=LEVEL_CHOICES
    )

    occurrence_count = models.PositiveIntegerField()

    message = models.TextField()

    requires_admin_review = models.BooleanField(
        default=False
    )
    ADMIN_DECISION_CHOICES = (
        ('warning_upheld', 'Warning Upheld'),
        ('warning_dismissed', 'Warning Dismissed'),
        ('further_action', 'Further Action Required'),
    )

    admin_decision = models.CharField(
        max_length=30,
        choices=ADMIN_DECISION_CHOICES,
        blank=True,
        default=''
    )

    admin_review_reason = models.TextField(
        blank=True,
        default=''
    )

    admin_reviewed_at = models.DateTimeField(
        null=True,
        blank=True
    )
    ADMIN_ACTION_STATUS_CHOICES = (
        ('pending', 'Action Pending'),
        ('completed', 'Action Completed'),
    )

    admin_action_status = models.CharField(
        max_length=20,
        choices=ADMIN_ACTION_STATUS_CHOICES,
        blank=True,
        default=''
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    'user',
                    'location',
                    'warning_type',
                    'level'
                ],
                name='unique_warning_per_user_location_type_level'
            )
        ]

    def __str__(self):
        return f"{self.get_level_display()} - {self.user.username}"
