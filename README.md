# ParkGrid – Smart Parking Management System

## About the Project

ParkGrid is a web-based Smart Parking Management System developed using Django and MySQL. It helps users find and book parking spaces, manage reservations, and make parking payments conveniently.

The system provides separate functionalities for administrators, users, and parking managers to ensure efficient parking space management.

## Features

- User registration and login
- Admin approval of registered users
- Role-based access for Admin, User, and Parking Manager
- Parking location and slot management
- Two-wheeler and four-wheeler parking options
- Nearby parking location search
- Advance and balance payment management
- QR code-based vehicle entry and exit
- Booking history and cancellation management
- Refund calculation for cancelled bookings
- Parking grace period and no-show management

## Modules

### 1. Admin
- Manage users and parking managers
- Approve user registrations
- Manage system activities

### 2. User
- Search nearby parking locations
- View available parking slots
- Book parking spaces
- Make advance and balance payments
- View booking history
- Cancel bookings

### 3. Parking Manager
- Manage assigned parking locations
- Manage parking slots
- Scan QR codes for vehicle entry and exit
- Monitor parking bookings

## Technologies Used

**Frontend:** HTML, CSS, JavaScript  
**Backend:** Python, Django  
**Database:** MySQL  
**Tools:** Visual Studio Code, Git, GitHub

## Installation and Setup

1. Clone the repository:

   `git clone https://github.com/gopikrishnan7306-gif/ParkGrid.git`

2. Navigate to the project directory:

   `cd ParkGrid`

3. Create and activate a virtual environment:

   `python -m venv venv`

4. Install the required dependencies:

   `pip install -r requirements.txt`

5. Create a `.env` file in the project root and configure the following variables:

   - DJANGO_SECRET_KEY
   - DB_NAME
   - DB_USER
   - DB_PASSWORD
   - DB_HOST
   - DB_PORT

6. Configure MySQL and create the database.

7. Apply migrations:

   `python manage.py migrate`

8. Start the development server:

   `python manage.py runserver`

9. Open the application in your browser:

   `http://127.0.0.1:8000/`

## Project Repository

[ParkGrid – GitHub Repository](https://github.com/gopikrishnan7306-gif/ParkGrid)

## Project Team

Developed as an academic MCA project by the project team.

---

**ParkGrid – Making Parking Smarter and Easier.**
