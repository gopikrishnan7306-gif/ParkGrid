from datetime import datetime, timedelta
import base64
from io import BytesIO
import uuid
from decimal import Decimal

import qrcode

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.db import transaction
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.db.models import Q
from django.utils import timezone
from django.urls import reverse

from .forms import RegistrationForm, ComplaintForm
from .models import (
    User,
    ParkingLocation,
    ParkingSlot,
    Booking,
    Payment,
    Complaint
)


# =========================================================
# PARKGRID TARIFF HELPER
# =========================================================


def calculate_parking_charge(location, vehicle_type, duration_seconds):
    """
    The base rate covers the first hour.
    Extra parking time is charged proportionally by the second.
    """

    from decimal import Decimal

    if vehicle_type == 'two_wheeler':
        base_rate = Decimal(str(location.two_wheeler_base_rate))
        extra_hour_rate = Decimal(str(location.two_wheeler_extra_hour_rate))
    else:
        base_rate = Decimal(str(location.four_wheeler_base_rate))
        extra_hour_rate = Decimal(str(location.four_wheeler_extra_hour_rate))

    duration_seconds = max(0, duration_seconds)

    if duration_seconds == 0:
        final_amount = Decimal('0.00')
    elif duration_seconds <= 3600:
        final_amount = base_rate
    else:
        extra_seconds = Decimal(str(duration_seconds - 3600))
        extra_charge = extra_hour_rate * extra_seconds / Decimal('3600')
        final_amount = (base_rate + extra_charge).quantize(Decimal('0.01'))

    return final_amount, base_rate, extra_hour_rate

# =========================================================
# DURATION DISPLAY HELPER
# =========================================================

def format_duration(duration_seconds):
    """
    Convert seconds into a simple display such as:

    2 hours
    2 hours 30 minutes
    45 minutes
    """

    total_minutes = int(
        duration_seconds // 60
    )

    hours = total_minutes // 60
    minutes = total_minutes % 60

    if hours > 0 and minutes > 0:
        return f'{hours} hours {minutes} minutes'
    elif hours > 0:
        return f'{hours} hours'
    else:
        return f'{minutes} minutes'


# =========================================================
# HOME
# =========================================================

def home(request):

    return render(
        request,
        'parking/home.html'
    )




def calculate_exit_balance(booking, payment):
    """
    Calculate the final parking charge and pending balance.
    The base rate covers the first hour.
    Extra time beyond reservation expiry is charged proportionally.
    """

    if not booking.actual_entry_time:
        raise ValueError("Entry time is not recorded.")

    # Do not recalculate if exit has already been recorded.
    if booking.actual_exit_time:
        return format_duration(
            (
                booking.actual_exit_time -
                booking.actual_entry_time
            ).total_seconds()
        )

    actual_exit_time = timezone.now()

    actual_duration_seconds = max(
        0,
        (
            actual_exit_time -
            booking.actual_entry_time
        ).total_seconds()
    )

    actual_duration_display = format_duration(
        actual_duration_seconds
    )

    # Calculate the booked duration and its fee.
    booked_duration_seconds = max(
        0,
        (
            booking.reservation_expiry -
            booking.expected_arrival
        ).total_seconds()
    )

    booked_amount, base_rate, extra_hour_rate = (
        calculate_parking_charge(
            booking.location,
            booking.vehicle_type,
            booked_duration_seconds
        )
    )

    # Charge proportionally for time beyond reservation expiry.
    extra_seconds = max(
        0,
        (
            actual_exit_time -
            booking.reservation_expiry
        ).total_seconds()
    )

    extra_charge = (
        Decimal(str(extra_seconds)) *
        Decimal(str(extra_hour_rate)) /
        Decimal('3600')
    ).quantize(Decimal('0.01'))

    final_amount = (
        booked_amount + extra_charge
    ).quantize(Decimal('0.01'))

    advance_amount = payment.advance_amount or Decimal('0.00')

    balance_amount = max(
        Decimal('0.00'),
        final_amount - advance_amount
    ).quantize(Decimal('0.01'))

    # Save the final charge and pending balance.
    booking.actual_exit_time = actual_exit_time

    payment.final_amount = final_amount
    payment.balance_amount = balance_amount
    payment.balance_status = (
        'paid'
        if balance_amount == Decimal('0.00')
        else 'pending'
    )

    payment.save(update_fields=[
        'final_amount',
        'balance_amount',
        'balance_status',
    ])

    # Release the slot only if no balance remains.
    if balance_amount == Decimal('0.00'):
        booking.status = 'completed'
        booking.slot.status = 'available'
    else:
        booking.status = 'active'
        booking.slot.status = 'occupied'

    booking.slot.save(update_fields=['status'])

    booking.save(update_fields=[
        'actual_exit_time',
        'status',
    ])

    return actual_duration_display

# =========================================================
# REGISTRATION
# =========================================================

def register(request):

    if request.method == 'POST':

        form = RegistrationForm(
            request.POST
        )

        if form.is_valid():

            user = form.save(
                commit=False
            )

            user.first_name = (
                form.cleaned_data['full_name']
            )

            email = (
                form.cleaned_data['email']
                .strip()
                .lower()
            )

            user.email = email

            username = email.split('@')[0]
            original_username = username
            counter = 1

            while User.objects.filter(
                username=username
            ).exists():

                username = (
                    f'{original_username}{counter}'
                )

                counter += 1

            user.username = username

            user.set_password(
                form.cleaned_data['password']
            )

            user.role = request.POST.get(
                'role',
                'user'
            )

            user.approval_status = 'pending'
            user.is_active = False

            user.save()

            messages.success(
                request,
                'Registration successful! Your account is waiting for admin approval.'
            )

            return redirect(
                'login'
            )

    else:

        form = RegistrationForm()

    return render(
        request,
        'parking/register.html',
        {
            'form': form
        }
    )


# =========================================================
# LOGIN
# =========================================================

def user_login(request):

    if request.method == 'POST':

        email = request.POST.get(
            'email',
            ''
        ).strip().lower()

        password = request.POST.get(
            'password',
            ''
        )

        try:

            user = User.objects.get(
                email=email
            )

            if user.approval_status == 'pending':

                messages.warning(
                    request,
                    'Your account is waiting for admin approval.'
                )

                return render(
                    request,
                    'parking/login.html'
                )

            if user.approval_status == 'rejected':

                messages.error(
                    request,
                    'Your account registration was rejected by the admin.'
                )

                return render(
                    request,
                    'parking/login.html'
                )

            if not user.is_active:

                messages.error(
                    request,
                    'Your account is inactive. Please contact the admin.'
                )

                return render(
                    request,
                    'parking/login.html'
                )

            authenticated_user = authenticate(
                request,
                username=user.username,
                password=password
            )

            if authenticated_user is not None:

                login(
                    request,
                    authenticated_user
                )

                if authenticated_user.role == 'user':

                    return redirect(
                        'user_dashboard'
                    )

                elif authenticated_user.role == 'manager':

                    return redirect(
                        'manager_dashboard'
                    )

                elif authenticated_user.role == 'admin':

                    return redirect(
                        'admin_dashboard'
                    )

            else:

                messages.error(
                    request,
                    'Invalid email or password.'
                )

        except User.DoesNotExist:

            messages.error(
                request,
                'Invalid email or password.'
            )

    return render(
        request,
        'parking/login.html'
    )


# =========================================================
# LOGOUT
# =========================================================

def user_logout(request):

    logout(request)

    return redirect(
        'login'
    )


# =========================================================
# USER DASHBOARD
# =========================================================

def user_dashboard(request):
    user = request.user

    total_bookings = Booking.objects.filter(
        user=user
    ).count()

    active_bookings = Booking.objects.filter(
        user=user,
        status__in=['reserved', 'active']
    ).count()

    total_complaints = Complaint.objects.filter(
        user=user
    ).count()

    context = {
        'total_bookings': total_bookings,
        'active_bookings': active_bookings,
        'total_complaints': total_complaints,
    }

    return render(
        request,
        'parking/dashboard.html',
        context
    )


# =========================================================
# PARKING LIST
# =========================================================

def parking_list(request):

    locations = ParkingLocation.objects.filter(
        status=True
    ).order_by(
        'name'
    )

    for location in locations:

        location.available_slots = (
            ParkingSlot.objects.filter(
                location=location,
                status='available'
            ).count()
        )

    return render(
        request,
        'parking/parking_list.html',
        {
            'locations': locations,
        }
    )


# =========================================================
# PARKING LAYOUT
# =========================================================

def parking_layout(request, location_id):

    location = ParkingLocation.objects.get(
        id=location_id
    )

    slots = ParkingSlot.objects.filter(
        location=location
    ).order_by(
        'is_extra',
        'slot_number'
    )

    selected_date = request.GET.get(
        'date'
    )

    selected_time = request.GET.get(
        'time'
    )

    duration_value = request.GET.get(
        'duration'
    )

    booked_slot_ids = set()

    extra_two_wheeler_available = False
    extra_four_wheeler_available = False

    duration = None

    if (
        selected_date and
        selected_time and
        duration_value
    ):

        try:

            duration = int(
                duration_value
            )

            if duration > 0:

                start_naive = datetime.strptime(
                    f'{selected_date} {selected_time}',
                    '%Y-%m-%d %H:%M'
                )

                start_time = timezone.make_aware(
                    start_naive
                )

                end_time = (
                    start_time +
                    timedelta(hours=duration)
                )

                conflicting_bookings = (
                    Booking.objects.filter(
                        location=location,
                        status__in=[
                            'reserved',
                            'active'
                        ],
                        expected_arrival__lt=end_time,
                        reservation_expiry__gt=start_time
                    )
                )

                booked_slot_ids = set(
                    conflicting_bookings.values_list(
                        'slot_id',
                        flat=True
                    )
                )

                # -----------------------------------------
                # 2-WHEELER EXTRA SLOT CHECK
                # -----------------------------------------

                regular_two_wheeler = slots.filter(
                    vehicle_type='two_wheeler',
                    is_extra=False
                )

                if regular_two_wheeler.exists():

                    all_two_wheeler_unavailable = all(
                        slot.id in booked_slot_ids
                        or slot.status in [
                            'occupied',
                            'maintenance'
                        ]
                        for slot in regular_two_wheeler
                    )

                    extra_two_wheeler_available = (
                        all_two_wheeler_unavailable
                    )

                # -----------------------------------------
                # 4-WHEELER EXTRA SLOT CHECK
                # -----------------------------------------

                regular_four_wheeler = slots.filter(
                    vehicle_type='four_wheeler',
                    is_extra=False
                )

                if regular_four_wheeler.exists():

                    all_four_wheeler_unavailable = all(
                        slot.id in booked_slot_ids
                        or slot.status in [
                            'occupied',
                            'maintenance'
                        ]
                        for slot in regular_four_wheeler
                    )

                    extra_four_wheeler_available = (
                        all_four_wheeler_unavailable
                    )

        except (
            ValueError,
            TypeError
        ):

            duration = None

    return render(
        request,
        'parking/parking_layout.html',
        {
            'location': location,
            'slots': slots,
            'booked_slot_ids': booked_slot_ids,
            'selected_date': selected_date,
            'selected_time': selected_time,
            'duration': duration,
            'extra_two_wheeler_available':
                extra_two_wheeler_available,
            'extra_four_wheeler_available':
                extra_four_wheeler_available,
        }
    )


# =========================================================
# PARKING SLOT DETAILS
# =========================================================

def parking_slots(request):

    slot_id = request.GET.get(
        'slot_id'
    )

    slot = None

    if slot_id:

        try:

            slot = ParkingSlot.objects.get(
                id=slot_id
            )

        except ParkingSlot.DoesNotExist:

            slot = None

    return render(
        request,
        'parking/parking_slots.html',
        {
            'slot': slot
        }
    )


# =========================================================
# MANAGER SECTION
# =========================================================


# =========================================================
# MANAGER DASHBOARD
# =========================================================

def manager_dashboard(request):

    manager = request.user

    try:

        location = ParkingLocation.objects.get(
            manager=manager
        )

    except ParkingLocation.DoesNotExist:

        location = None

    if location:

        total_slots = ParkingSlot.objects.filter(
            location=location
        ).count()

        available_slots = ParkingSlot.objects.filter(
            location=location,
            status='available'
        ).count()

        occupied_slots = ParkingSlot.objects.filter(
            location=location,
            status='occupied'
        ).count()

        total_bookings = Booking.objects.filter(
            location=location
        ).count()

        active_bookings = Booking.objects.filter(
            location=location,
            status__in=[
                'reserved',
                'active'
            ]
        ).count()

        total_complaints = Complaint.objects.filter(
            location=location
        ).count()

    else:

        total_slots = 0
        available_slots = 0
        occupied_slots = 0
        total_bookings = 0
        active_bookings = 0
        total_complaints = 0

    context = {
        'location': location,
        'total_slots': total_slots,
        'available_slots': available_slots,
        'occupied_slots': occupied_slots,
        'total_bookings': total_bookings,
        'active_bookings': active_bookings,
        'total_complaints': total_complaints,
    }

    return render(
        request,
        'parking/manager_dashboard.html',
        context
    )


# =========================================================
# MANAGER PARKING FACILITY
# =========================================================

def manager_facility(request):

    location = ParkingLocation.objects.filter(
        manager=request.user
    ).first()

    if request.method == 'POST':

        if location:

            messages.error(
                request,
                'You already have a parking facility.'
            )

            return redirect(
                'manager_facility'
            )

        name = request.POST.get(
            'name'
        )

        address = request.POST.get(
            'address'
        )

        city = request.POST.get(
            'city'
        )

        ParkingLocation.objects.create(
            manager=request.user,
            name=name,
            address=address,
            city=city
        )

        messages.success(
            request,
            'Parking facility added successfully!'
        )

        return redirect(
            'manager_facility'
        )

    return render(
        request,
        'parking/manager_facility.html',
        {
            'location': location,
        }
    )


# =========================================================
# MANAGE PARKING SLOTS
# =========================================================

def manager_slots(request):

    location = ParkingLocation.objects.filter(
        manager=request.user
    ).first()

    if not location:

        messages.error(
            request,
            'Please add your parking facility first.'
        )

        return redirect(
            'manager_facility'
        )

    slots = ParkingSlot.objects.filter(
        location=location
    ).order_by(
        'is_extra',
        'slot_number'
    )

    if request.method == 'POST':

        slot_number = request.POST.get(
            'slot_number'
        )

        vehicle_type = request.POST.get(
            'vehicle_type'
        )

        is_ev = request.POST.get(
            'is_ev'
        ) == 'on'

        charging_available = request.POST.get(
            'charging_available'
        ) == 'on'

        is_extra = request.POST.get(
            'is_extra'
        ) == 'on'

        ParkingSlot.objects.create(
            location=location,
            slot_number=slot_number,
            vehicle_type=vehicle_type,
            is_ev=is_ev,
            charging_available=charging_available,
            is_extra=is_extra
        )

        messages.success(
            request,
            f'Slot {slot_number} added successfully!'
        )

        return redirect(
            'manager_slots'
        )

    return render(
        request,
        'parking/manager_slots.html',
        {
            'location': location,
            'slots': slots
        }
    )


# =========================================================
# EDIT PARKING SLOT
# =========================================================

def edit_manager_slot(request, slot_id):

    slot = ParkingSlot.objects.get(
        id=slot_id,
        location__manager=request.user
    )

    if request.method == 'POST':

        slot.slot_number = request.POST.get(
            'slot_number'
        )

        slot.vehicle_type = request.POST.get(
            'vehicle_type'
        )

        slot.is_ev = request.POST.get(
            'is_ev'
        ) == 'on'

        slot.charging_available = request.POST.get(
            'charging_available'
        ) == 'on'

        slot.status = request.POST.get(
            'status'
        )

        slot.save()

        messages.success(
            request,
            f'Slot {slot.slot_number} updated successfully!'
        )

        return redirect(
            'manager_slots'
        )

    return render(
        request,
        'parking/edit_manager_slot.html',
        {
            'slot': slot,
        }
    )


# =========================================================
# DELETE PARKING SLOT
# =========================================================

def delete_manager_slot(request, slot_id):

    slot = ParkingSlot.objects.get(
        id=slot_id,
        location__manager=request.user
    )

    if request.method == 'POST':

        slot_number = slot.slot_number

        slot.delete()

        messages.success(
            request,
            f'Slot {slot_number} deleted successfully!'
        )

    return redirect(
        'manager_slots'
    )


# =========================================================
# MANAGER BOOKINGS
# =========================================================

def manager_bookings(request):

    location = ParkingLocation.objects.filter(
        manager=request.user
    ).first()

    if not location:

        messages.error(
            request,
            'Please add your parking facility first.'
        )

        return redirect(
            'manager_facility'
        )

    bookings = Booking.objects.filter(
        location=location
    ).select_related(
        'user',
        'slot'
    ).order_by(
        '-created_at'
    )

    for booking_obj in bookings:

        duration_seconds = (
            booking_obj.reservation_expiry -
            booking_obj.expected_arrival
        ).total_seconds()

        booking_obj.booked_duration_display = (
            format_duration(
                duration_seconds
            )
        )

        payment = getattr(
            booking_obj,
            'payment',
            None
        )

        booking_obj.payment_obj = payment

    return render(
        request,
        'parking/manager_bookings.html',
        {
            'location': location,
            'bookings': bookings,
        }
    )


# =========================================================
# MANAGER MARK ENTRY
# =========================================================

def manager_mark_entry(request, booking_id):

    location = ParkingLocation.objects.filter(
        manager=request.user
    ).first()

    if not location:

        messages.error(
            request,
            'Parking facility not found.'
        )

        return redirect(
            'manager_dashboard'
        )

    try:

        booking = Booking.objects.select_related(
            'user',
            'slot',
            'location'
        ).get(
            id=booking_id,
            location=location
        )

    except Booking.DoesNotExist:

        messages.error(
            request,
            'Booking not found.'
        )

        return redirect(
            'manager_bookings'
        )

    if booking.status != 'reserved':

        messages.error(
            request,
            'This booking cannot be marked as entry.'
        )

        return redirect(
            'manager_bookings'
        )

    payment = getattr(
        booking,
        'payment',
        None
    )

    if not payment or payment.advance_status != 'paid':

        messages.error(
            request,
            'Advance payment has not been completed.'
        )

        return redirect(
            'manager_bookings'
        )

    booking.actual_entry_time = timezone.now()
    booking.status = 'active'

    booking.slot.status = 'occupied'

    booking.save(
        update_fields=[
            'actual_entry_time',
            'status'
        ]
    )

    booking.slot.save(
        update_fields=[
            'status'
        ]
    )

    messages.success(
        request,
        f'Entry recorded successfully for Booking #{booking.id}.'
    )

    return redirect(
        'manager_bookings'
    )


# =========================================================
# MANAGER MARK EXIT
# =========================================================


def manager_mark_exit(request, booking_id):
    location = ParkingLocation.objects.filter(
        manager=request.user
    ).first()

    if not location:
        messages.error(request, 'Parking facility not found.')
        return redirect('manager_dashboard')

    try:
        booking = Booking.objects.select_related(
            'user', 'slot', 'location'
        ).get(
            id=booking_id,
            location=location
        )
    except Booking.DoesNotExist:
        messages.error(request, 'Booking not found.')
        return redirect('manager_bookings')

    if booking.status != 'active':
        messages.error(
            request,
            'This booking cannot be marked as exit.'
        )
        return redirect('manager_bookings')

    if not booking.actual_entry_time:
        messages.error(
            request,
            'Entry time is not recorded.'
        )
        return redirect('manager_bookings')

    payment = getattr(booking, 'payment', None)

    if not payment or payment.advance_status != 'paid':
        messages.error(
            request,
            'Advance payment has not been completed.'
        )
        return redirect('manager_bookings')

    try:
        if not booking.actual_exit_time:
            actual_duration_display = calculate_exit_balance(
                booking, payment
            )
        else:
            actual_duration_display = format_duration(
                (
                    booking.actual_exit_time
                    - booking.actual_entry_time
                ).total_seconds()
            )
    except ValueError as error:
        messages.error(request, str(error))
        return redirect('manager_bookings')

    # Refresh the latest saved booking and payment details.
    payment.refresh_from_db()
    booking.refresh_from_db()

    # Calculate the booked parking charge.
    booked_duration_seconds = max(
        0,
        (
            booking.reservation_expiry
            - booking.expected_arrival
        ).total_seconds()
    )

    booked_amount, base_rate, extra_hour_rate = (
        calculate_parking_charge(
            booking.location,
            booking.vehicle_type,
            booked_duration_seconds
        )
    )

    # Calculate extra time beyond the reservation expiry.
    extra_seconds = max(
        0,
        (
            booking.actual_exit_time
            - booking.reservation_expiry
        ).total_seconds()
    )

    extra_time_display = format_duration(extra_seconds)

    extra_charge = (
        Decimal(str(extra_seconds))
        * Decimal(str(extra_hour_rate))
        / Decimal('3600')
    ).quantize(Decimal('0.01'))

    advance_amount = (
        payment.advance_amount or Decimal('0.00')
    )

    final_amount = payment.final_amount or Decimal('0.00')
    balance_amount = payment.balance_amount or Decimal('0.00')

    # Show the complete payment breakdown to the manager.
    breakdown = (
        f'Actual duration: {actual_duration_display} | '
        f'Booked charge: ₹{booked_amount} | '
        f'Extra time: {extra_time_display} | '
        f'Extra-time charge: ₹{extra_charge} | '
        f'Final amount: ₹{final_amount} | '
        f'Advance paid: ₹{advance_amount} | '
        f'Balance due: ₹{balance_amount}'
    )

    if balance_amount > Decimal('0.00'):
        messages.warning(
            request,
            f'Exit recorded. {breakdown}'
        )
    else:
        messages.success(
            request,
            f'Parking completed. {breakdown}'
        )

    return redirect('manager_bookings')


# =========================================================
# SCAN QR
# =========================================================


def scan_qr(request, booking_id):
    if not request.user.is_authenticated:
        messages.error(request, 'Please log in to scan your booking QR code.')
        return redirect('login')

    try:
        booking = Booking.objects.select_related(
            'user', 'slot', 'location'
        ).get(id=booking_id)
    except Booking.DoesNotExist:
        messages.error(request, 'Booking not found.')
        return redirect('booking_history')

    # Only the booking owner or the assigned parking manager can view the QR.
    is_customer = booking.user_id == request.user.id
    is_manager = ParkingLocation.objects.filter(
        manager=request.user,
        id=booking.location_id
    ).exists()

    if not is_customer and not is_manager:
        messages.error(
            request,
            'You are not authorized to view this booking.'
        )
        return redirect('user_dashboard')

    # Customers can view their booking QR, but cannot record vehicle exit.
    if is_customer and not is_manager and booking.status == 'active':
        messages.error(
            request,
            'Please ask the parking manager to confirm your vehicle exit.'
        )
        return redirect('booking_history')

    payment = getattr(booking, 'payment', None)

    booked_duration_seconds = max(
        0,
        (
            booking.reservation_expiry
            - booking.expected_arrival
        ).total_seconds()
    )
    booked_duration_display = format_duration(
        booked_duration_seconds
    )

    actual_duration_display = None
    action = None

    # Record entry only once, after advance payment.
    if booking.status == 'reserved':
        if not payment or payment.advance_status != 'paid':
            action = 'payment_required'
            messages.error(
                request,
                'Please complete the advance payment before entry.'
            )
        else:
            booking.actual_entry_time = timezone.now()
            booking.status = 'active'
            booking.slot.status = 'occupied'

            booking.save(update_fields=[
                'actual_entry_time',
                'status'
            ])
            booking.slot.save(update_fields=['status'])

            action = 'entry'
            messages.success(
                request,
                f'Entry recorded for Booking #{booking.id}.'
            )

    # Record exit once, then show any balance due.
    elif booking.status == 'active':
        if not booking.actual_entry_time:
            action = 'error'
            messages.error(request, 'Entry time has not been recorded.')

        elif not payment or payment.advance_status != 'paid':
            action = 'payment_required'
            messages.error(request, 'Advance payment is not completed.')

        elif booking.actual_exit_time:
            actual_duration_display = format_duration(
                (
                    booking.actual_exit_time
                    - booking.actual_entry_time
                ).total_seconds()
            )

            if payment.balance_status == 'paid':
                booking.status = 'completed'
                booking.slot.status = 'available'
                booking.save(update_fields=['status'])
                booking.slot.save(update_fields=['status'])
                action = 'completed'
            else:
                action = 'balance_pending'

        else:
            try:
                actual_duration_display = calculate_exit_balance(
                    booking, payment
                )
            except ValueError as error:
                action = 'error'
                messages.error(request, str(error))
            else:
                booking.refresh_from_db()
                payment.refresh_from_db()

                if payment.balance_status == 'paid':
                    action = 'completed'
                    messages.success(
                        request,
                        f'Exit recorded. Final amount: ₹{payment.final_amount}.'
                    )
                else:
                    action = 'balance_pending'
                    messages.warning(
                        request,
                        f'Exit recorded. Balance due: ₹{payment.balance_amount}.'
                    )

    elif booking.status == 'completed':
        if booking.actual_entry_time and booking.actual_exit_time:
            actual_duration_display = format_duration(
                (
                    booking.actual_exit_time
                    - booking.actual_entry_time
                ).total_seconds()
            )
        action = 'completed'

    else:
        action = 'invalid'

    return render(
        request,
        'parking/qr_scan_result.html',
        {
            'booking': booking,
            'payment': payment,
            'booked_duration_display': booked_duration_display,
            'actual_duration_display': actual_duration_display,
            'action': action,
            'is_customer': is_customer,
        }
    )



# =========================================================
# MANAGER COMPLAINTS
# =========================================================

def manager_complaints(request):

    location = ParkingLocation.objects.filter(
        manager=request.user
    ).first()

    if not location:

        messages.error(
            request,
            'Please add your parking facility first.'
        )

        return redirect(
            'manager_facility'
        )

    complaints = Complaint.objects.filter(
        location=location
    ).select_related(
        'user',
        'booking'
    ).order_by(
        '-created_at'
    )

    return render(
        request,
        'parking/manager_complaints.html',
        {
            'location': location,
            'complaints': complaints,
        }
    )


# =========================================================
# ADMIN SECTION
# =========================================================


# =========================================================
# ADMIN DASHBOARD
# =========================================================

def admin_dashboard(request):

    total_users = User.objects.filter(
        role='user'
    ).count()

    total_managers = User.objects.filter(
        role='manager'
    ).count()

    total_locations = ParkingLocation.objects.count()

    total_slots = ParkingSlot.objects.count()

    active_bookings = Booking.objects.filter(
        status__in=[
            'reserved',
            'active'
        ]
    ).count()

    total_complaints = Complaint.objects.count()

    context = {
        'total_users': total_users,
        'total_managers': total_managers,
        'total_locations': total_locations,
        'total_slots': total_slots,
        'active_bookings': active_bookings,
        'total_complaints': total_complaints,
    }

    return render(
        request,
        'parking/admin_dashboard.html',
        context
    )


# =========================================================
# ADMIN USERS
# =========================================================

def admin_users(request):

    users = User.objects.filter(
        role='user'
    ).order_by(
        '-date_joined'
    )

    search = request.GET.get(
        'search',
        ''
    ).strip()

    if search:

        users = users.filter(
            Q(first_name__icontains=search) |
            Q(email__icontains=search) |
            Q(phone__icontains=search) |
            Q(username__icontains=search)
        )

    return render(
        request,
        'parking/admin_users.html',
        {
            'users': users,
            'search': search,
        }
    )


# =========================================================
# APPROVE USER
# =========================================================

def approve_user(request, user_id):

    user = User.objects.get(
        id=user_id,
        role='user'
    )

    user.approval_status = 'approved'
    user.is_active = True

    user.save()

    messages.success(
        request,
        f'{user.first_name} has been approved successfully.'
    )

    return redirect(
        'admin_users'
    )


# =========================================================
# REJECT USER
# =========================================================

def reject_user(request, user_id):

    user = User.objects.get(
        id=user_id,
        role='user'
    )

    user.approval_status = 'rejected'
    user.is_active = False

    user.save()

    messages.warning(
        request,
        f'{user.first_name} has been rejected.'
    )

    return redirect(
        'admin_users'
    )


# =========================================================
# DEACTIVATE USER
# =========================================================

def deactivate_user(request, user_id):

    user = User.objects.get(
        id=user_id,
        role='user'
    )

    user.is_active = False

    user.save()

    messages.warning(
        request,
        f'{user.first_name} has been deactivated.'
    )

    return redirect(
        'admin_users'
    )


# =========================================================
# ACTIVATE USER
# =========================================================

def activate_user(request, user_id):

    user = User.objects.get(
        id=user_id,
        role='user'
    )

    user.is_active = True
    user.approval_status = 'approved'

    user.save()

    messages.success(
        request,
        f'{user.first_name} has been activated.'
    )

    return redirect(
        'admin_users'
    )


# =========================================================
# ADMIN MANAGERS
# =========================================================

def admin_managers(request):

    managers = User.objects.filter(
        role='manager'
    ).order_by(
        '-date_joined'
    )

    search = request.GET.get(
        'search',
        ''
    ).strip()

    if search:

        managers = managers.filter(
            Q(first_name__icontains=search) |
            Q(email__icontains=search) |
            Q(phone__icontains=search) |
            Q(username__icontains=search)
        )

    return render(
        request,
        'parking/admin_managers.html',
        {
            'managers': managers,
            'search': search,
        }
    )


# =========================================================
# APPROVE MANAGER
# =========================================================

def approve_manager(request, user_id):

    manager = User.objects.get(
        id=user_id,
        role='manager'
    )

    manager.approval_status = 'approved'
    manager.is_active = True

    manager.save()

    messages.success(
        request,
        f'{manager.first_name} has been approved as a Parking Manager.'
    )

    return redirect(
        'admin_managers'
    )


# =========================================================
# REJECT MANAGER
# =========================================================

def reject_manager(request, user_id):

    manager = User.objects.get(
        id=user_id,
        role='manager'
    )

    manager.approval_status = 'rejected'
    manager.is_active = False

    manager.save()

    messages.warning(
        request,
        f'{manager.first_name} has been rejected.'
    )

    return redirect(
        'admin_managers'
    )


# =========================================================
# ADMIN PARKING LOCATIONS
# =========================================================

def admin_parking_locations(request):

    locations = ParkingLocation.objects.select_related(
        'manager'
    ).order_by(
        '-created_at'
    )

    search = request.GET.get(
        'search',
        ''
    ).strip()

    if search:

        locations = locations.filter(
            Q(name__icontains=search) |
            Q(city__icontains=search) |
            Q(address__icontains=search) |
            Q(manager__first_name__icontains=search) |
            Q(manager__email__icontains=search)
        )

    return render(
        request,
        'parking/admin_parking_locations.html',
        {
            'locations': locations,
            'search': search,
        }
    )


# =========================================================
# ADMIN BOOKINGS
# =========================================================

def admin_bookings(request):

    bookings = Booking.objects.select_related(
        'user',
        'location',
        'slot'
    ).order_by(
        '-created_at'
    )

    search = request.GET.get(
        'search',
        ''
    ).strip()

    if search:

        bookings = bookings.filter(
            Q(vehicle_number__icontains=search) |
            Q(user__first_name__icontains=search) |
            Q(user__email__icontains=search) |
            Q(location__name__icontains=search) |
            Q(slot__slot_number__icontains=search)
        )

    return render(
        request,
        'parking/admin_bookings.html',
        {
            'bookings': bookings,
            'search': search,
        }
    )


# =========================================================
# ADMIN COMPLAINTS
# =========================================================

def admin_complaints(request):

    complaints = Complaint.objects.select_related(
        'user',
        'location',
        'booking'
    ).order_by(
        '-created_at'
    )

    search = request.GET.get(
        'search',
        ''
    ).strip()

    if search:

        complaints = complaints.filter(
            Q(subject__icontains=search) |
            Q(description__icontains=search) |
            Q(user__first_name__icontains=search) |
            Q(user__email__icontains=search) |
            Q(location__name__icontains=search)
        )

    return render(
        request,
        'parking/admin_complaints.html',
        {
            'complaints': complaints,
            'search': search,
        }
    )


# =========================================================
# ADMIN REPORTS
# =========================================================

def admin_reports(request):

    total_users = User.objects.filter(
        role='user'
    ).count()

    total_managers = User.objects.filter(
        role='manager'
    ).count()

    total_locations = ParkingLocation.objects.count()

    total_slots = ParkingSlot.objects.count()

    total_bookings = Booking.objects.count()

    completed_bookings = Booking.objects.filter(
        status='completed'
    ).count()

    cancelled_bookings = Booking.objects.filter(
        status='cancelled'
    ).count()

    expired_bookings = Booking.objects.filter(
        status='expired'
    ).count()

    total_complaints = Complaint.objects.count()

    resolved_complaints = Complaint.objects.filter(
        status='resolved'
    ).count()

    pending_complaints = Complaint.objects.filter(
        status='pending'
    ).count()

    context = {
        'total_users': total_users,
        'total_managers': total_managers,
        'total_locations': total_locations,
        'total_slots': total_slots,
        'total_bookings': total_bookings,
        'completed_bookings': completed_bookings,
        'cancelled_bookings': cancelled_bookings,
        'expired_bookings': expired_bookings,
        'total_complaints': total_complaints,
        'resolved_complaints': resolved_complaints,
        'pending_complaints': pending_complaints,
    }

    return render(
        request,
        'parking/admin_reports.html',
        context
    )


# =========================================================
# BOOKING SECTION
# =========================================================


# =========================================================
# BOOKING
# =========================================================

def booking(request):

    if request.method == 'POST':

        slot_id = request.POST.get(
            'slot_id'
        )

        selected_date = request.POST.get(
            'date'
        )

        selected_time = request.POST.get(
            'time'
        )

        duration_value = request.POST.get(
            'duration'
        )

        vehicle_type = request.POST.get(
            'vehicle_type'
        )

        vehicle_number = request.POST.get(
            'vehicle_number'
        )

    else:

        slot_id = request.GET.get(
            'slot_id'
        )

        selected_date = request.GET.get(
            'date'
        )

        selected_time = request.GET.get(
            'time'
        )

        duration_value = request.GET.get(
            'duration'
        )

        vehicle_type = request.GET.get(
            'vehicle_type'
        )

        vehicle_number = request.GET.get(
            'vehicle_number'
        )

    try:

        slot = ParkingSlot.objects.get(
            id=slot_id
        )

    except (
        ParkingSlot.DoesNotExist,
        TypeError,
        ValueError
    ):

        messages.error(
            request,
            'Selected parking slot was not found.'
        )

        return redirect(
            'parking_list'
        )

    try:

        duration = int(
            duration_value
        )

    except (
        ValueError,
        TypeError
    ):

        duration = None

    if (
        not selected_date or
        not selected_time or
        not duration
    ):

        messages.error(
            request,
            'Please select date, time and duration.'
        )

        return redirect(
            'parking_layout',
            location_id=slot.location.id
        )

    try:

        start_naive = datetime.strptime(
            f'{selected_date} {selected_time}',
            '%Y-%m-%d %H:%M'
        )

        expected_arrival = timezone.make_aware(
            start_naive
        )

        reservation_expiry = (
            expected_arrival +
            timedelta(hours=duration)
        )

    except (
        ValueError,
        TypeError
    ):

        messages.error(
            request,
            'Invalid booking date or time.'
        )

        return redirect(
            'parking_layout',
            location_id=slot.location.id
        )

    conflicting_booking = Booking.objects.filter(
        slot=slot,
        status__in=[
            'reserved',
            'active'
        ],
        expected_arrival__lt=reservation_expiry,
        reservation_expiry__gt=expected_arrival
    ).exists()

    if conflicting_booking:

        messages.error(
            request,
            'Sorry, this slot has already been booked for the selected time.'
        )

        return redirect(
            'parking_layout',
            location_id=slot.location.id
        )

    # -----------------------------------------------------
    # CREATE BOOKING
    # -----------------------------------------------------

    if request.method == 'POST':

        if (
            not vehicle_type or
            not vehicle_number
        ):

            messages.error(
                request,
                'Please enter all vehicle details.'
            )

            return redirect(
                'parking_layout',
                location_id=slot.location.id
            )

        booking_obj = Booking.objects.create(
            user=request.user,
            location=slot.location,
            slot=slot,
            vehicle_type=vehicle_type,
            vehicle_number=vehicle_number,
            booking_date=expected_arrival.date(),
            expected_arrival=expected_arrival,
            reservation_expiry=reservation_expiry,
            qr_code=str(uuid.uuid4()),
            status='reserved'
        )

        return redirect(
            'booking_confirmation',
            booking_id=booking_obj.id
        )

    return render(
        request,
        'parking/booking.html',
        {
            'slot': slot,
            'selected_date': selected_date,
            'selected_time': selected_time,
            'duration': duration,
            'vehicle_type': vehicle_type,
            'vehicle_number': vehicle_number,
            'expected_arrival': expected_arrival,
            'reservation_expiry': reservation_expiry,
        }
    )


# =========================================================
# BOOKING CONFIRMATION
# =========================================================

def booking_confirmation(request, booking_id):
    try:
        booking = Booking.objects.select_related(
            'location',
            'slot'
        ).get(
            id=booking_id,
            user=request.user
        )

    except Booking.DoesNotExist:
        messages.error(
            request,
            'Booking not found.'
        )
        return redirect('booking_history')

    booked_duration_seconds = max(
        0,
        (
            booking.reservation_expiry -
            booking.expected_arrival
        ).total_seconds()
    )

    booked_duration_display = format_duration(
        booked_duration_seconds
    )

    full_amount, base_rate, extra_hour_rate = (
        calculate_parking_charge(
            booking.location,
            booking.vehicle_type,
            booked_duration_seconds
        )
    )

    advance_amount = min(
        Decimal('20.00'),
        full_amount
    )

    remaining_amount = max(
        Decimal('0.00'),
        full_amount - advance_amount
    )

    return render(
        request,
        'parking/booking_confirmation.html',
        {
            'booking': booking,
            'booked_duration_display': booked_duration_display,
            'full_amount': full_amount,
            'advance_amount': advance_amount,
            'remaining_amount': remaining_amount,
            'base_rate': base_rate,
            'extra_hour_rate': extra_hour_rate,
        }
    )



# =========================================================
# ADVANCE PAYMENT
# =========================================================




def advance_payment(request, booking_id):
    try:
        booking = Booking.objects.select_related(
            'location', 'slot', 'user'
        ).get(id=booking_id, user=request.user)
    except Booking.DoesNotExist:
        messages.error(request, 'Booking not found.')
        return redirect('booking_history')

    duration_seconds = max(
        0,
        (booking.reservation_expiry - booking.expected_arrival).total_seconds()
    )

    booked_duration_display = format_duration(duration_seconds)

    full_amount, base_rate, extra_hour_rate = calculate_parking_charge(
        booking.location,
        booking.vehicle_type,
        duration_seconds
    )

    advance_amount = min(Decimal('20.00'), full_amount)

    if request.method == 'POST':
        payment_method = request.POST.get('payment_method', '').strip()
        stage = request.POST.get('stage', '')

        if payment_method not in ['gpay', 'phonepe', 'upi']:
            messages.error(request, 'Please select a valid payment method.')
            return redirect('advance_payment', booking_id=booking.id)

        if stage == 'confirm_payment':
            demo_pin = request.POST.get('demo_pin', '').strip()

            if not demo_pin.isdigit() or len(demo_pin) != 4:
                return render(request, 'parking/demo_payment_pin.html', {
                    'booking': booking,
                    'advance_amount': advance_amount,
                    'full_amount': full_amount,
                    'payment_method': payment_method,
                    'error': 'Please enter a valid 4-digit PIN.',
                })

            payment, created = Payment.objects.get_or_create(booking=booking)

            if payment.advance_status == 'paid':
                messages.info(request, 'Advance payment is already completed.')
                return redirect('booking_history')

            payment.advance_amount = advance_amount
            payment.advance_payment_method = payment_method
            payment.advance_status = 'paid'
            payment.advance_payment_time = timezone.now()
            payment.save()

            return render(request, 'parking/payment_success.html', {
                'booking': booking,
                'advance_amount': advance_amount,
                'full_amount': full_amount,
                'payment_method': payment_method,
                'transaction_reference': (
                    f'PG-DEMO-{booking.id}-{int(timezone.now().timestamp())}'
                ),
            })

        return render(request, 'parking/demo_payment_pin.html', {
            'booking': booking,
            'advance_amount': advance_amount,
            'full_amount': full_amount,
            'payment_method': payment_method,
        })

    return render(request, 'parking/advance_payment.html', {
        'booking': booking,
        'advance_amount': advance_amount,
        'full_amount': full_amount,
        'duration_hours': int(duration_seconds // 3600),
        'duration_minutes': int((duration_seconds % 3600) // 60),
        'booked_duration_display': booked_duration_display,
        'base_rate': base_rate,
        'extra_hour_rate': extra_hour_rate,
    })


# =========================================================
# BALANCE PAYMENT
# =========================================================




from django.db import transaction


def balance_payment(request, booking_id):
    if request.method not in ['GET', 'POST']:
        return redirect('booking_history')

    try:
        booking = Booking.objects.select_related(
            'user', 'slot', 'location'
        ).get(
            id=booking_id,
            user=request.user
        )
    except Booking.DoesNotExist:
        messages.error(request, 'Booking not found.')
        return redirect('booking_history')

    payment = getattr(booking, 'payment', None)

    if not payment or payment.advance_status != 'paid':
        messages.error(request, 'Advance payment is not completed.')
        return redirect('booking_history')

    if booking.status != 'active' or not booking.actual_exit_time:
        messages.error(
            request,
            'The parking exit must be recorded before balance payment.'
        )
        return redirect('booking_history')

    if payment.balance_status == 'paid':
        messages.info(request, 'Balance payment is already completed.')
        return redirect('booking_history')

    if (
        payment.balance_amount is None
        or payment.balance_amount <= Decimal('0.00')
    ):
        messages.error(request, 'There is no pending balance.')
        return redirect('booking_history')

    if request.method == 'GET':
        return render(
            request,
            'parking/advance_payment.html',
            {
                'booking': booking,
                'balance_amount': payment.balance_amount,
                'is_balance_payment': True,
            }
        )

    valid_methods = ['gpay', 'phonepe', 'upi']
    payment_method = request.POST.get(
        'payment_method', ''
    ).strip().lower()
    stage = request.POST.get('stage', '')

    if payment_method not in valid_methods:
        messages.error(request, 'Please select a valid payment method.')
        return redirect('balance_payment', booking_id=booking.id)

    if stage != 'confirm_payment':
        return render(
            request,
            'parking/demo_balance_payment_pin.html',
            {
                'booking': booking,
                'balance_amount': payment.balance_amount,
                'payment_method': payment_method,
            }
        )

    demo_pin = request.POST.get('demo_pin', '').strip()

    if not demo_pin.isdigit() or len(demo_pin) != 4:
        return render(
            request,
            'parking/demo_balance_payment_pin.html',
            {
                'booking': booking,
                'balance_amount': payment.balance_amount,
                'payment_method': payment_method,
                'error': 'Please enter a valid 4-digit PIN.',
            }
        )

    # Lock and recheck the records before recording payment.
    with transaction.atomic():
        locked_booking = Booking.objects.select_for_update().get(
            id=booking.id,
            user=request.user
        )
        locked_payment = Payment.objects.select_for_update().get(
            booking=locked_booking
        )
        locked_slot = ParkingSlot.objects.select_for_update().get(
            id=locked_booking.slot_id
        )

        if (
            locked_booking.status != 'active'
            or not locked_booking.actual_exit_time
        ):
            messages.error(
                request,
                'This booking is no longer awaiting balance payment.'
            )
            return redirect('booking_history')

        if locked_payment.balance_status == 'paid':
            messages.info(
                request,
                'Balance payment is already completed.'
            )
            return redirect('booking_history')

        if (
            locked_payment.balance_amount is None
            or locked_payment.balance_amount <= Decimal('0.00')
        ):
            messages.error(request, 'There is no pending balance.')
            return redirect('booking_history')

        balance_paid = locked_payment.balance_amount

        locked_payment.balance_payment_method = payment_method
        locked_payment.balance_payment_time = timezone.now()
        locked_payment.balance_status = 'paid'
        locked_payment.save(update_fields=[
            'balance_payment_method',
            'balance_payment_time',
            'balance_status',
        ])

        locked_booking.status = 'completed'
        locked_booking.save(update_fields=['status'])

        locked_slot.status = 'available'
        locked_slot.save(update_fields=['status'])

    messages.success(
        request,
        f'Balance payment of ₹{balance_paid} completed successfully.'
    )

    return redirect('booking_history')


# =========================================================
# BOOKING DETAILS
# =========================================================

def booking_details(request):

    try:

        booking = Booking.objects.filter(
            user=request.user
        ).select_related(
            'location',
            'slot'
        ).latest(
            'created_at'
        )

    except Booking.DoesNotExist:

        messages.error(
            request,
            'No booking found.'
        )

        return redirect(
            'booking_history'
        )

    payment = getattr(
        booking,
        'payment',
        None
    )

    booked_duration_seconds = (
        booking.reservation_expiry -
        booking.expected_arrival
    ).total_seconds()

    booked_duration_display = (
        format_duration(
            booked_duration_seconds
        )
    )

    actual_duration_display = None

    if (
        booking.actual_entry_time and
        booking.actual_exit_time
    ):

        actual_duration_seconds = (
            booking.actual_exit_time -
            booking.actual_entry_time
        ).total_seconds()

        actual_duration_display = (
            format_duration(
                actual_duration_seconds
            )
        )

    return render(
        request,
        'parking/booking_details.html',
        {
            'booking': booking,
            'payment': payment,
            'booked_duration_display':
                booked_duration_display,
            'actual_duration_display':
                actual_duration_display,
        }
    )


# =========================================================
# QR CODE
# =========================================================

def qr_code(request, booking_id):

    try:

        booking = Booking.objects.select_related(
            'location',
            'slot',
            'user'
        ).get(
            id=booking_id,
            user=request.user
        )

    except Booking.DoesNotExist:

        messages.error(
            request,
            'Booking not found.'
        )

        return redirect(
            'booking_history'
        )

    # -----------------------------------------------------
    # CHECK ADVANCE PAYMENT
    # -----------------------------------------------------

    payment = getattr(
        booking,
        'payment',
        None
    )

    if (
        not payment or
        payment.advance_status != 'paid'
    ):

        messages.error(
            request,
            'Please complete the advance payment before generating the QR code.'
        )

        return redirect(
            'advance_payment',
            booking_id=booking.id
        )

    # -----------------------------------------------------
    # QR SCAN URL
    # -----------------------------------------------------

    scan_url = request.build_absolute_uri(
        reverse(
            'scan_qr',
            kwargs={
                'booking_id': booking.id
            }
        )
    )

    # -----------------------------------------------------
    # GENERATE QR CODE
    # -----------------------------------------------------

    qr = qrcode.QRCode(
        version=1,
        box_size=8,
        border=4
    )

    qr.add_data(
        scan_url
    )

    qr.make(
        fit=True
    )

    qr_image = qr.make_image(
        fill_color='black',
        back_color='white'
    )

    buffer = BytesIO()

    qr_image.save(
        buffer,
        format='PNG'
    )

    qr_image_base64 = base64.b64encode(
        buffer.getvalue()
    ).decode(
        'utf-8'
    )

    return render(
        request,
        'parking/qr_code.html',
        {
            'booking': booking,
            'payment': payment,
            'qr_image': qr_image_base64,
            'scan_url': scan_url,
        }
    )


# =========================================================
# MY BOOKINGS - ACTIVE AND UPCOMING BOOKINGS
# =========================================================

@login_required
def my_bookings(request):
    print("MY BOOKINGS USER:", request.user.username)

    # Show only reserved and active bookings.
    bookings = Booking.objects.filter(
        user=request.user,
        status__in=['reserved', 'active']
    ).select_related(
        'location',
        'slot',
        'payment'
    ).order_by('-created_at')

    print("MY BOOKINGS COUNT:", bookings.count())

    for booking in bookings:
        booked_duration_seconds = (
            booking.reservation_expiry -
            booking.expected_arrival
        ).total_seconds()

        booking.booked_duration_display = format_duration(
            booked_duration_seconds
        )

        if booking.actual_entry_time and booking.actual_exit_time:
            actual_duration_seconds = (
                booking.actual_exit_time -
                booking.actual_entry_time
            ).total_seconds()

            booking.actual_duration_display = format_duration(
                actual_duration_seconds
            )
        else:
            booking.actual_duration_display = None

        # Safely get the payment record.
        booking.payment_obj = getattr(
            booking, 'payment', None
        )

        payment = booking.payment_obj

        # Allow cancellation of reserved bookings before parking starts.
        # Payment does not prevent cancellation.
        booking.can_cancel = (
            booking.status == 'reserved'
            and not booking.actual_entry_time
            and not booking.actual_exit_time
        )

    return render(
        request,
        'parking/my_bookings.html',
        {'bookings': bookings}
    )



# =========================================================
# BOOKING HISTORY
# =========================================================

@login_required
def booking_history(request):

    # Show only completed and cancelled bookings.
    bookings = Booking.objects.filter(
        user=request.user,
        status__in=['completed', 'cancelled']
    ).select_related(
        'location',
        'slot'
    ).order_by('-created_at')

    for booking_obj in bookings:

        booked_duration_seconds = (
            booking_obj.reservation_expiry -
            booking_obj.expected_arrival
        ).total_seconds()

        booking_obj.booked_duration_display = format_duration(
            booked_duration_seconds
        )

        if (
            booking_obj.actual_entry_time
            and booking_obj.actual_exit_time
        ):
            actual_duration_seconds = (
                booking_obj.actual_exit_time -
                booking_obj.actual_entry_time
            ).total_seconds()

            booking_obj.actual_duration_display = format_duration(
                actual_duration_seconds
            )
        else:
            booking_obj.actual_duration_display = None

        # Safely get the payment record.
        booking_obj.payment_obj = getattr(
            booking_obj, 'payment', None
        )

    return render(
        request,
        'parking/booking_history.html',
        {'bookings': bookings}
    )


# =========================================================
# CANCEL BOOKING
# =========================================================

@login_required
@require_POST
def cancel_booking(request, booking_id):

    with transaction.atomic():
        booking_obj = get_object_or_404(
            Booking.objects.select_for_update(),
            id=booking_id,
            user=request.user
        )

        # Only reserved bookings can be cancelled.
        if booking_obj.status != 'reserved':
            messages.error(
                request,
                'Only reserved bookings can be cancelled.'
            )
            return redirect('booking_history')

        # Do not allow cancellation after parking has started.
        if booking_obj.actual_entry_time or booking_obj.actual_exit_time:
            messages.error(
                request,
                'This booking cannot be cancelled because the parking process has started.'
            )
            return redirect('booking_history')

        payment = Payment.objects.filter(
            booking=booking_obj
        ).first()

        # Calculate the refund only from an advance payment
        # that was actually recorded as paid.
        if payment:
            if payment.refund_status == 'refunded':
                messages.error(
                    request,
                    'A refund has already been recorded for this booking.'
                )
                return redirect('booking_history')

            if payment.advance_status == 'paid':
                advance_paid = payment.advance_amount or Decimal('0.00')

                refund_amount = (
                    advance_paid * Decimal('0.25')
                ).quantize(Decimal('0.01'))

                cancellation_charge = advance_paid - refund_amount

                payment.refund_amount = refund_amount
                payment.cancellation_charge = cancellation_charge
                payment.refund_status = (
                    'refunded'
                    if refund_amount > Decimal('0.00')
                    else 'not_applicable'
                )

            else:
                payment.refund_amount = Decimal('0.00')
                payment.cancellation_charge = Decimal('0.00')
                payment.refund_status = 'not_applicable'

            payment.save(update_fields=[
                'refund_amount',
                'cancellation_charge',
                'refund_status',
            ])

        # Cancel the booking.
        booking_obj.status = 'cancelled'
        booking_obj.save(update_fields=['status'])

    messages.success(
        request,
        'Booking cancelled successfully. The 25% advance refund has been recorded.'
        if payment and payment.refund_status == 'refunded'
        else f'Booking #{booking_obj.id} cancelled successfully.'
    )

    return redirect('booking_history')

# =========================================================
# COMPLAINT SECTION
# =========================================================


# =========================================================
# COMPLAINTS
# =========================================================

def complaint(request):

    if request.method == 'POST':

        form = ComplaintForm(
            request.POST,
            request.FILES
        )

        if form.is_valid():

            complaint_obj = form.save(
                commit=False
            )

            complaint_obj.user = request.user

            complaint_obj.save()

            messages.success(
                request,
                'Complaint submitted successfully.'
            )

            return redirect(
                'complaint'
            )

    else:

        form = ComplaintForm()

    return render(
        request,
        'parking/complaints.html',
        {
            'form': form
        }
    )


# =========================================================
# COMPLAINT STATUS
# =========================================================

def complaint_status(request):

    complaints = Complaint.objects.filter(
        user=request.user
    ).select_related(
        'location'
    ).order_by(
        '-created_at'
    )

    return render(
        request,
        'parking/complaint_status.html',
        {
            'complaints': complaints
        }
    )