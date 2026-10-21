from django.contrib import admin
from django.urls import path
from parking import views


urlpatterns = [

    # =====================================================
    # DJANGO ADMIN
    # =====================================================

    path(
        'admin/',
        admin.site.urls
    ),


    # =====================================================
    # HOME / AUTH
    # =====================================================

    path(
        '',
        views.home,
        name='home'
    ),

    path(
        'login/',
        views.user_login,
        name='login'
    ),

    path(
        'logout/',
        views.user_logout,
        name='logout'
    ),

    path(
        'register/',
        views.register,
        name='register'
    ),


    # =====================================================
    # USER
    # =====================================================

    path(
        'user/dashboard/',
        views.user_dashboard,
        name='user_dashboard'
    ),

    path(
        'parking-list/',
        views.parking_list,
        name='parking_list'
    ),

    path(
    'nearby-pay-park/',
    views.nearby_pay_park,
    name='nearby_pay_park'
    ),
    
    path(
    'api/nearby-parking/',
    views.nearby_parking_data,
    name='nearby_parking_data'
    ),


    path(
        'parking-layout/<int:location_id>/',
        views.parking_layout,
        name='parking_layout'
    ),

    path(
        'parking-slots/',
        views.parking_slots,
        name='parking_slots'
    ),

    path(
        'booking/',
        views.booking,
        name='booking'
    ),

    # =====================================================
    # BOOKING
    # =====================================================

    path(
        'booking-confirmation/<int:booking_id>/',
        views.booking_confirmation,
        name='booking_confirmation'
    ),

    path(
        'booking-details/',
        views.booking_details,
        name='booking_details'
    ),
    path(
    'advance-payment/<int:booking_id>/',
    views.advance_payment,
    name='advance_payment'
    ),
    
path(
    'balance-payment/<int:booking_id>/',
    views.balance_payment,
    name='balance_payment'
),


    path(
        'qr-code/<int:booking_id>/',
        views.qr_code,
        name='qr_code'
    ),
    path(
        'manager/scan-qr/<int:booking_id>/',
        views.manager_qr_scanner,
        name='manager_qr_scanner'
    ),
    path(
        'manager/process-qr/<int:booking_id>/',
        views.manager_process_qr_scan,
        name='manager_process_qr_scan'
    ),
path(
    'manager/booking/<int:booking_id>/entry/',
    views.manager_mark_entry,
    name='manager_mark_entry'
),
path(
    'manager/booking/<int:booking_id>/exit/',
    views.manager_mark_exit,
    name='manager_mark_exit'
),
    path(
    'scan-qr/<int:booking_id>/',
    views.scan_qr,
    name='scan_qr'
),

    path(
        'booking-history/',
        views.booking_history,
        name='booking_history'
    ),
path('my-bookings/', views.my_bookings, name='my_bookings'),   
 path(
    'booking/<int:booking_id>/cancel/',
    views.cancel_booking,
    name='cancel_booking'
),


    # =====================================================
    # COMPLAINT
    # =====================================================
path(
    'complaints/',
    views.complaint,
    name='complaint'
),

path(
    'complaint-status/',
    views.complaint_status,
    name='complaint_status'
),


    # =====================================================
    # ADMIN DASHBOARD
    # =====================================================

    path(
        'parkgrid-admin/dashboard/',
        views.admin_dashboard,
        name='admin_dashboard'
    ),
        path(
        'parkgrid-admin/warning-review/<int:warning_id>/',
        views.admin_review_warning,
        name='admin_review_warning'
    ),


    # =====================================================
    # ADMIN USERS
    # =====================================================

    path(
        'parkgrid-admin/users/',
        views.admin_users,
        name='admin_users'
    ),

    path(
        'parkgrid-admin/users/<int:user_id>/approve/',
        views.approve_user,
        name='approve_user'
    ),

    path(
        'parkgrid-admin/users/<int:user_id>/reject/',
        views.reject_user,
        name='reject_user'
    ),

    path(
        'parkgrid-admin/users/<int:user_id>/deactivate/',
        views.deactivate_user,
        name='deactivate_user'
    ),

    path(
        'parkgrid-admin/users/<int:user_id>/activate/',
        views.activate_user,
        name='activate_user'
    ),


    # =====================================================
    # ADMIN PARKING MANAGERS
    # =====================================================

    path(
        'parkgrid-admin/managers/',
        views.admin_managers,
        name='admin_managers'
    ),

    path(
        'parkgrid-admin/managers/<int:user_id>/approve/',
        views.approve_manager,
        name='approve_manager'
    ),

    path(
        'parkgrid-admin/managers/<int:user_id>/reject/',
        views.reject_manager,
        name='reject_manager'
    ),


    # =====================================================
    # MANAGER
    # =====================================================

    path(
        'manager/dashboard/',
        views.manager_dashboard,
        name='manager_dashboard'
    ),

    path(
        'manager/facility/',
        views.manager_facility,
        name='manager_facility'
    ),

    path(
        'manager/slots/',
        views.manager_slots,
        name='manager_slots'
    ),

    path(
        'manager/slots/edit/<int:slot_id>/',
        views.edit_manager_slot,
        name='edit_manager_slot'
    ),

    path(
        'manager/slots/delete/<int:slot_id>/',
        views.delete_manager_slot,
        name='delete_manager_slot'
    ),

    path(
        'manager/bookings/',
        views.manager_bookings,
        name='manager_bookings'
    ),

    path(
        'manager/complaints/',
        views.manager_complaints,
        name='manager_complaints'
    ),
    path(
    'manager/complaints/<int:complaint_id>/view/',
    views.manager_complaint_detail,
    name='manager_complaint_detail'
    ),
    path(
    'manager/complaints/<int:complaint_id>/verify/',
    views.manager_verify_complaint,
    name='manager_verify_complaint'
    ),

path(
    'manager/booking/<int:booking_id>/no-show/',
    views.manager_mark_no_show,
    name='manager_mark_no_show'
),


    # =====================================================
    # ADMIN PARKING LOCATIONS
    # =====================================================

    path(
        'parkgrid-admin/parking-locations/',
        views.admin_parking_locations,
        name='admin_parking_locations'
    ),


    # =====================================================
    # ADMIN BOOKINGS
    # =====================================================

    path(
        'parkgrid-admin/bookings/',
        views.admin_bookings,
        name='admin_bookings'
    ),


    # =====================================================
    # ADMIN COMPLAINTS
    # =====================================================

    
path(
    'parkgrid-admin/complaints/',
    views.admin_complaints,
    name='admin_complaints'
),





    # =====================================================
    # ADMIN REPORTS
    # =====================================================

    path(
        'parkgrid-admin/reports/',
        views.admin_reports,
        name='admin_reports'
    ),
]

