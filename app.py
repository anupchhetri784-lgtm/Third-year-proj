import pandas as pd
import numpy as np
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import re
import random
import string
from werkzeug.security import generate_password_hash, check_password_hash
from db import get_db_connection
from auth import login_required, admin_required, guide_required
from datetime import datetime
from sklearn.linear_model import LinearRegression
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from chatbot import chatbot_agent
from recommender import get_content_based_recommendations
from textblob import TextBlob
from flask import send_file
from generate_pdf import generate_ticket_pdf
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'nepal_travel_secret_key_change_this_later')
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'images')

@app.route('/')
def home():
    if session.get('guide_id'):
        return render_template('guide_home.html')
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM destinations LIMIT 4')
    destinations = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('home.html', destinations=destinations)

@app.route('/destinations')
def destinations():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM destinations')
    all_destinations = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('destinations.html', destinations=all_destinations)

@app.route('/destination/<int:dest_id>')
def destination_details(dest_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM destinations WHERE id = %s', (dest_id,))
    destination = cursor.fetchone()
    
    if not destination:
        flash('Destination not found.', 'error')
        cursor.close()
        conn.close()
        return redirect(url_for('destinations'))
        
    cursor.execute('SELECT * FROM packages WHERE destination_id = %s', (dest_id,))
    packages = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('destination_details.html', destination=destination, packages=packages)

@app.route('/packages')
def packages():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute((
            "SELECT packages.*, destinations.name AS destination_name "
            "FROM packages "
            "JOIN destinations ON packages.destination_id = destinations.id "
        ))
    all_packages = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('packages.html', packages=all_packages)

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    if not query:
        return redirect(url_for('home'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Search destinations by name or description
    search_term = f"%{query}%"
    cursor.execute((
            "SELECT * FROM destinations "
            "WHERE name LIKE %s OR description LIKE %s "
        ), (search_term, search_term))
    destinations = cursor.fetchall()
    
    # Search packages by title or description
    cursor.execute((
            "SELECT packages.*, destinations.name AS destination_name "
            "FROM packages "
            "JOIN destinations ON packages.destination_id = destinations.id "
            "WHERE packages.title LIKE %s OR packages.description LIKE %s OR destinations.name LIKE %s "
        ), (search_term, search_term, search_term))
    packages = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('search_results.html', query=query, destinations=destinations, packages=packages)

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        message = request.form.get('message')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO contact_messages (name, email, message) VALUES (%s, %s, %s)', (name, email, message))
        conn.commit()
        cursor.close()
        conn.close()
        
        flash('Thank you for your message! We will get back to you soon.', 'success')
        return redirect(url_for('contact'))
    return render_template('contact.html')

# ---------- REGISTER ----------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form['full_name']
        email = request.form['email']
        phone = request.form['phone']
        password = request.form['password']
       
        email_pattern = r'^[^\s@]+@[^\s@]+\.[^\s@]+$'
        if not re.match(email_pattern, email):
            flash('Please enter a valid email address.', 'error')
            return redirect(url_for('register'))
            
        phone_pattern = r'^(98|97)\d{8}$'
        if not re.match(phone_pattern, phone):
            flash('Phone number must start with 98 or 97 and be exactly 10 digits.', 'error')
            return redirect(url_for('register'))
        
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if email already exists
        cursor.execute('SELECT id FROM users WHERE email = %s', (email,))
        existing_user = cursor.fetchone()

        if existing_user:
            flash('Email already registered. Please login instead.', 'error')
            cursor.close()
            conn.close()
            return redirect(url_for('register'))

        # Hash the password before storing
        hashed_password = generate_password_hash(password)

        cursor.execute(
            'INSERT INTO users (full_name, email, phone, password) VALUES (%s, %s, %s, %s)',
            (full_name, email, phone, hashed_password)
        )
        conn.commit()
        cursor.close()
        conn.close()

        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

# ---------- LOGIN ----------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['user_name'] = user['full_name']
            session['role'] = user['role']
            flash(f"Welcome back, {user['full_name']}!", 'success')

            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('home'))
        else:
            flash('Invalid email or password.', 'error')
            return redirect(url_for('login'))

    return render_template('login.html')

# ---------- LOGOUT ----------
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('home'))


# ---------- BOOK A PACKAGE ----------
@app.route('/book/<int:package_id>', methods=['GET', 'POST'])
@login_required
def book_package(package_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute((
            "SELECT packages.*, destinations.name AS destination_name "
            "FROM packages "
            "JOIN destinations ON packages.destination_id = destinations.id "
            "WHERE packages.id = %s "
        ), (package_id,))
    package = cursor.fetchone()

    if not package:
        flash('Package not found.', 'error')
        cursor.close()
        conn.close()
        return redirect(url_for('packages'))

    if request.method == 'POST':
        num_people = int(request.form['num_people'])
        travel_date = request.form['travel_date']

        if num_people < 1 or num_people > package['max_people']:
            flash(f"Number of people must be between 1 and {package['max_people']}.", 'error')
            cursor.close()
            conn.close()
            return redirect(url_for('book_package', package_id=package_id))

        travel_date_obj = datetime.strptime(travel_date, '%Y-%m-%d').date()
        if travel_date_obj < datetime.now().date():
            flash('Travel date cannot be in the past.', 'error')
            cursor.close()
            conn.close()
            return redirect(url_for('book_package', package_id=package_id))

        cursor.execute((
            "SELECT id FROM bookings "
            "WHERE user_id = %s AND package_id = %s AND travel_date = %s "
            "AND status IN ('Pending', 'Confirmed') "
        ), (session['user_id'], package_id, travel_date))
        existing_booking = cursor.fetchone()

        if existing_booking:
            flash('You already have an active booking for this package on this date.', 'error')
            cursor.close()
            conn.close()
            return redirect(url_for('book_package', package_id=package_id))

        cursor.close()
        conn.close()

        total_price = float(package['price']) * num_people

        # --- CHANGED: instead of inserting now, stash details in session and go to payment ---
        session['pending_booking'] = {
            'package_id': package_id,
            'num_people': num_people,
            'travel_date': travel_date,
            'total_price': total_price,
            'package_title': package['title'],
            'guide_id': request.form.get('guide_id')
        }
        return redirect(url_for('esewa_payment'))
        # --- end change ---

    cursor.execute((
            "SELECT r.*, u.full_name "
            "FROM reviews r "
            "JOIN users u ON r.user_id = u.id "
            "WHERE r.package_id = %s "
            "ORDER BY r.created_at DESC "
        ), (package_id,))
    reviews = cursor.fetchall()
    
    cursor.execute((
            "SELECT * FROM package_itineraries "
            "WHERE package_id = %s "
            "ORDER BY day_number ASC "
        ), (package_id,))
    itineraries = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template('book_package.html', package=package, today=datetime.now().strftime('%Y-%m-%d'), reviews=reviews, itineraries=itineraries)

# ---------- MY BOOKINGS ----------
@app.route('/my-bookings')
@login_required
def my_bookings():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute((
            "SELECT bookings.*, packages.title, packages.duration_days, destinations.name AS destination_name, "
            "guides.full_name AS guide_name, guides.phone AS guide_phone "
            "FROM bookings "
            "JOIN packages ON bookings.package_id = packages.id "
            "JOIN destinations ON packages.destination_id = destinations.id "
            "LEFT JOIN guides ON bookings.guide_id = guides.id "
            "WHERE bookings.user_id = %s "
            "ORDER BY bookings.booked_at DESC "
        ), (session['user_id'],))
    bookings = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('my_bookings.html', bookings=bookings)

# ---------- CANCEL BOOKING ----------
@app.route('/cancel-booking/<int:booking_id>')
@login_required
def cancel_booking(booking_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    # Important: only let users cancel their OWN bookings
    cursor.execute('SELECT * FROM bookings WHERE id = %s AND user_id = %s', (booking_id, session['user_id']))
    booking = cursor.fetchone()

    if not booking:
        flash('Booking not found.', 'error')
    else:
        cursor.execute("UPDATE bookings SET status = 'Cancelled' WHERE id = %s", (booking_id,))
        conn.commit()
        flash('Booking cancelled.', 'success')

    cursor.close()
    conn.close()
    return redirect(url_for('my_bookings'))

# ---------- ADMIN DASHBOARD ----------
@app.route('/admin')
@admin_required
def admin_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT COUNT(*) AS total FROM users WHERE role = "user"')
    total_users = cursor.fetchone()['total']

    cursor.execute('SELECT COUNT(*) AS total FROM destinations')
    total_destinations = cursor.fetchone()['total']

    cursor.execute('SELECT COUNT(*) AS total FROM packages')
    total_packages = cursor.fetchone()['total']

    cursor.execute('SELECT COUNT(*) AS total FROM bookings WHERE status = "Pending"')
    pending_bookings = cursor.fetchone()['total']

    cursor.execute('SELECT COUNT(*) AS total FROM bookings WHERE status = "Confirmed"')
    confirmed_bookings = cursor.fetchone()['total']

    cursor.execute('SELECT * FROM contact_messages ORDER BY created_at DESC')
    contact_messages = cursor.fetchall()

    cursor.execute('SELECT * FROM guides ORDER BY created_at DESC')
    guides = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('admin/dashboard.html',
        total_users=total_users,
        total_destinations=total_destinations,
        total_packages=total_packages,
        pending_bookings=pending_bookings,
        confirmed_bookings=confirmed_bookings,
        contact_messages=contact_messages,
        guides=guides
    )

# ---------- ADMIN: VIEW ALL BOOKINGS ----------
@app.route('/admin/bookings')
@admin_required
def admin_bookings():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute((
            "SELECT bookings.*, users.full_name, users.email, "
            "packages.title, destinations.name AS destination_name "
            "FROM bookings "
            "JOIN users ON bookings.user_id = users.id "
            "JOIN packages ON bookings.package_id = packages.id "
            "JOIN destinations ON packages.destination_id = destinations.id "
            "ORDER BY bookings.travel_date DESC "
        ))
    all_bookings = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('admin/bookings.html', bookings=all_bookings)

# ---------- ADMIN: UPDATE BOOKING STATUS ----------
@app.route('/admin/bookings/update/<int:booking_id>/<status>')
@admin_required
def update_booking_status(booking_id, status):
    if status not in ['Confirmed', 'Cancelled', 'Pending']:
        flash('Invalid status.', 'error')
        return redirect(url_for('admin_bookings'))

    conn = get_db_connection()
    cursor = conn.cursor()
    
    if status == 'Confirmed':
        cursor.execute('SELECT guide_id FROM bookings WHERE id = %s', (booking_id,))
        booking = cursor.fetchone()
        
        cursor.execute('UPDATE bookings SET status = %s WHERE id = %s', (status, booking_id))
        
        if booking and booking.get('guide_id'):
            cursor.execute('INSERT INTO guide_notifications (guide_id, booking_id, message) VALUES (%s, %s, %s)', 
                           (booking['guide_id'], booking_id, f'You have been assigned a new booking (ID: {booking_id})!'))
    else:
        cursor.execute('UPDATE bookings SET status = %s WHERE id = %s', (status, booking_id))
        
    conn.commit()
    cursor.close()
    conn.close()

    flash(f'Booking status updated to {status}.', 'success')
    return redirect(url_for('admin_bookings'))

# ---------- ADMIN: DELETE BOOKING ----------
@app.route('/admin/bookings/delete/<int:booking_id>')
@admin_required
def delete_booking(booking_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM bookings WHERE id = %s', (booking_id,))
    conn.commit()
    cursor.close()
    conn.close()

    flash('Booking completely deleted.', 'success')
    return redirect(url_for('admin_bookings'))

# ---------- ADMIN: DESTINATIONS LIST ----------
@app.route('/admin/destinations')
@admin_required
def admin_destinations():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM destinations ORDER BY id DESC')
    all_destinations = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('admin/destinations.html', destinations=all_destinations)

# ---------- ADMIN: ADD DESTINATION ----------
@app.route('/admin/destinations/add', methods=['GET', 'POST'])
@admin_required
def add_destination():
    if request.method == 'POST':
        name = request.form['name']
        location = request.form['location']
        description = request.form['description']
        category = request.form['category']
        special_features = request.form.get('special_features', '')
        best_time_to_visit = request.form.get('best_time_to_visit', '')
        history = request.form.get('history', '')
        
        latitude = request.form.get('latitude')
        longitude = request.form.get('longitude')
        latitude = float(latitude) if latitude else None
        longitude = float(longitude) if longitude else None

        image = request.form.get('existing_image', '')
        if 'image_file' in request.files:
            file = request.files['image_file']
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image = filename

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute((
            "INSERT INTO destinations (name, location, description, image, category, special_features, best_time_to_visit, history, latitude, longitude) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        ), (name, location, description, image, category, special_features, best_time_to_visit, history, latitude, longitude))
        conn.commit()
        cursor.close()
        conn.close()

        flash('Destination added successfully.', 'success')
        return redirect(url_for('admin_destinations'))

    return render_template('admin/destination_form.html', destination=None)

# ---------- ADMIN: EDIT DESTINATION ----------
@app.route('/admin/destinations/edit/<int:dest_id>', methods=['GET', 'POST'])
@admin_required
def edit_destination(dest_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        name = request.form['name']
        location = request.form['location']
        description = request.form['description']
        category = request.form['category']
        special_features = request.form.get('special_features', '')
        best_time_to_visit = request.form.get('best_time_to_visit', '')
        history = request.form.get('history', '')
        
        latitude = request.form.get('latitude')
        longitude = request.form.get('longitude')
        latitude = float(latitude) if latitude else None
        longitude = float(longitude) if longitude else None

        image = request.form.get('existing_image', '')
        if 'image_file' in request.files:
            file = request.files['image_file']
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image = filename

        cursor.execute((
            "UPDATE destinations SET name=%s, location=%s, description=%s, image=%s, category=%s, "
            "special_features=%s, best_time_to_visit=%s, history=%s, latitude=%s, longitude=%s "
            "WHERE id=%s "
        ), (name, location, description, image, category, special_features, best_time_to_visit, history, latitude, longitude, dest_id))
        conn.commit()
        cursor.close()
        conn.close()

        flash('Destination updated successfully.', 'success')
        return redirect(url_for('admin_destinations'))

    cursor.execute('SELECT * FROM destinations WHERE id = %s', (dest_id,))
    destination = cursor.fetchone()
    cursor.close()
    conn.close()

    if not destination:
        flash('Destination not found.', 'error')
        return redirect(url_for('admin_destinations'))

    return render_template('admin/destination_form.html', destination=destination)

# ---------- ADMIN: DELETE DESTINATION ----------
@app.route('/admin/destinations/delete/<int:dest_id>')
@admin_required
def delete_destination(dest_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM destinations WHERE id = %s', (dest_id,))
    conn.commit()
    cursor.close()
    conn.close()
    flash('Destination deleted.', 'success')
    return redirect(url_for('admin_destinations'))

# ---------- ADMIN: PACKAGES LIST ----------
@app.route('/admin/packages')
@admin_required
def admin_packages():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute((
            "SELECT packages.*, destinations.name AS destination_name "
            "FROM packages "
            "JOIN destinations ON packages.destination_id = destinations.id "
            "ORDER BY packages.id DESC "
        ))
    all_packages = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('admin/packages.html', packages=all_packages)

# ---------- ADMIN: ADD PACKAGE ----------
@app.route('/admin/packages/add', methods=['GET', 'POST'])
@admin_required
def add_package():
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        destination_id = request.form['destination_id']
        title = request.form['title']
        description = request.form['description']
        price = request.form['price']
        duration_days = request.form['duration_days']
        max_people = request.form['max_people']
        
        image = request.form.get('existing_image', '')
        if 'image_file' in request.files:
            file = request.files['image_file']
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image = filename

        cursor.execute((
            "INSERT INTO packages (destination_id, title, description, price, duration_days, max_people, image) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) "
        ), (destination_id, title, description, price, duration_days, max_people, image))
        new_pkg_id = cursor.lastrowid

        itin_days = request.form.getlist('itinerary_day_number[]')
        itin_titles = request.form.getlist('itinerary_title[]')
        itin_descs = request.form.getlist('itinerary_description[]')
        itin_lats = request.form.getlist('itinerary_latitude[]')
        itin_lngs = request.form.getlist('itinerary_longitude[]')

        for i in range(len(itin_days)):
            if itin_titles[i]:
                day_val = itin_days[i]
                title_val = itin_titles[i]
                desc_val = itin_descs[i] if len(itin_descs) > i else ''
                lat_val = itin_lats[i] if len(itin_lats) > i and itin_lats[i] else None
                lng_val = itin_lngs[i] if len(itin_lngs) > i and itin_lngs[i] else None
                
                cursor.execute((
            "INSERT INTO package_itineraries (package_id, day_number, title, description, latitude, longitude) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
        ), (new_pkg_id, day_val, title_val, desc_val, lat_val, lng_val))
        conn.commit()
        cursor.close()
        conn.close()

        flash('Package added successfully.', 'success')
        return redirect(url_for('admin_packages'))

    cursor.execute('SELECT * FROM destinations')
    destinations = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('admin/package_form.html', package=None, destinations=destinations, itineraries=[])

# ---------- ADMIN: EDIT PACKAGE ----------
@app.route('/admin/packages/edit/<int:pkg_id>', methods=['GET', 'POST'])
@admin_required
def edit_package(pkg_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        destination_id = request.form['destination_id']
        title = request.form['title']
        description = request.form['description']
        price = request.form['price']
        duration_days = request.form['duration_days']
        max_people = request.form['max_people']
        
        image = request.form.get('existing_image', '')
        if 'image_file' in request.files:
            file = request.files['image_file']
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image = filename

        cursor.execute((
            "UPDATE packages SET destination_id=%s, title=%s, description=%s, price=%s, "
            "duration_days=%s, max_people=%s, image=%s WHERE id=%s "
        ), (destination_id, title, description, price, duration_days, max_people, image, pkg_id))
        
        cursor.execute('DELETE FROM package_itineraries WHERE package_id = %s', (pkg_id,))
        itin_days = request.form.getlist('itinerary_day_number[]')
        itin_titles = request.form.getlist('itinerary_title[]')
        itin_descs = request.form.getlist('itinerary_description[]')
        itin_lats = request.form.getlist('itinerary_latitude[]')
        itin_lngs = request.form.getlist('itinerary_longitude[]')

        for i in range(len(itin_days)):
            if itin_titles[i]:
                day_val = itin_days[i]
                title_val = itin_titles[i]
                desc_val = itin_descs[i] if len(itin_descs) > i else ''
                lat_val = itin_lats[i] if len(itin_lats) > i and itin_lats[i] else None
                lng_val = itin_lngs[i] if len(itin_lngs) > i and itin_lngs[i] else None
                
                cursor.execute((
            "INSERT INTO package_itineraries (package_id, day_number, title, description, latitude, longitude) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
        ), (pkg_id, day_val, title_val, desc_val, lat_val, lng_val))
        conn.commit()
        cursor.close()
        conn.close()

        flash('Package updated successfully.', 'success')
        return redirect(url_for('admin_packages'))

    cursor.execute('SELECT * FROM packages WHERE id = %s', (pkg_id,))
    package = cursor.fetchone()
    cursor.execute('SELECT * FROM destinations')
    destinations = cursor.fetchall()
    
    cursor.execute('SELECT * FROM package_itineraries WHERE package_id = %s ORDER BY day_number ASC', (pkg_id,))
    itineraries = cursor.fetchall()
    
    cursor.close()
    conn.close()

    if not package:
        flash('Package not found.', 'error')
        return redirect(url_for('admin_packages'))

    return render_template('admin/package_form.html', package=package, destinations=destinations, itineraries=itineraries)

# ---------- ADMIN: DELETE PACKAGE ----------
@app.route('/admin/packages/delete/<int:pkg_id>')
@admin_required
def delete_package(pkg_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM packages WHERE id = %s', (pkg_id,))
    conn.commit()
    cursor.close()
    conn.close()
    flash('Package deleted.', 'success')
    return redirect(url_for('admin_packages'))

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500

import random
import string

# ---------- ESEWA PAYMENT SIMULATION: PAYMENT PAGE ----------
@app.route('/payment/esewa')
@login_required
def esewa_payment():
    pending = session.get('pending_booking')
    if not pending:
        flash('No booking in progress. Please select a package first.', 'error')
        return redirect(url_for('packages'))

    return render_template('esewa_payment.html', booking=pending)

# ---------- ESEWA PAYMENT SIMULATION: PROCESS "PAYMENT" ----------
@app.route('/payment/esewa/process', methods=['POST'])
@login_required
def esewa_process():
    pending = session.get('pending_booking')
    if not pending:
        flash('No booking in progress. Please select a package first.', 'error')
        return redirect(url_for('packages'))

    # Simulate eSewa requiring an ID/MPIN - we don't actually verify these
    esewa_id = request.form.get('esewa_id')
    mpin = request.form.get('mpin')

    if not esewa_id or not mpin:
        flash('Please enter your eSewa ID and MPIN.', 'error')
        return redirect(url_for('esewa_payment'))

    # Generate a fake transaction ID, the way a real gateway would return one
    transaction_id = 'ESW' + ''.join(random.choices(string.digits, k=10))

    # NOW actually create the booking row, marked as paid
    conn = get_db_connection()
    cursor = conn.cursor()
    # Insert the actual booking into the DB now
    cursor.execute('''
        INSERT INTO bookings (user_id, package_id, travel_date, num_people, total_price, status, payment_status, guide_id, transaction_id, paid_at)
        VALUES (%s, %s, %s, %s, %s, 'Pending', 'Paid', %s, %s, NOW())
    ''', (session['user_id'], pending['package_id'], pending['travel_date'], pending['num_people'], pending['total_price'], pending.get('guide_id'), transaction_id))
    new_booking_id = cursor.lastrowid
    conn.commit()
    cursor.close()
    conn.close()

    # Clear the temporary pending booking from session - it's done its job
    session.pop('pending_booking', None)

    # Store transaction info briefly so the success page can show it
    session['last_transaction'] = {
        'transaction_id': transaction_id,
        'amount': pending['total_price'],
        'package_title': pending['package_title'],
        'booking_id': new_booking_id
    }

    return redirect(url_for('esewa_success'))

# ---------- ESEWA PAYMENT SIMULATION: SUCCESS PAGE ----------
@app.route('/payment/esewa/success')
@login_required
def esewa_success():
    transaction = session.get('last_transaction')
    if not transaction:
        return redirect(url_for('my_bookings'))

    session.pop('last_transaction', None)  # one-time view, like a real receipt page
    return render_template('esewa_success.html', transaction=transaction)

# ---------- AI CHATBOT ROUTE ----------
@app.route('/api/chat', methods=['POST'])
def api_chat():
    data = request.get_json() or {}
    message = data.get('message', '')
    if not message:
        return jsonify({"response": "I didn't catch that. Could you please repeat?", "intent": "greeting", "packages": []})
        
    user_id = session.get('user_id')
    result = chatbot_agent.get_response(message, user_id=user_id)
    return jsonify(result)

# ---------- USER TRAVEL ANALYTICS & SMART RECOMMENDATIONS ----------
@app.route('/recommendations')
@login_required
def user_recommendations():
    user_id = session['user_id']
    
    # 1. Fetch similarity recommendations
    recommendations = get_content_based_recommendations(user_id)
    
    # 2. Fetch user's booking statistics for personal insights
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT d.category, COUNT(b.id) AS count, SUM(b.total_price) AS spending
        FROM bookings b
        JOIN packages p ON b.package_id = p.id
        JOIN destinations d ON p.destination_id = d.id
        WHERE b.user_id = %s AND b.status != 'Cancelled'
        GROUP BY d.category
    """, (user_id,))
    category_stats = cursor.fetchall()
    
    # Fetch total travel spending
    cursor.execute("""
        SELECT SUM(total_price) AS total, COUNT(id) AS total_trips
        FROM bookings
        WHERE user_id = %s AND status != 'Cancelled'
    """, (user_id,))
    overview = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    total_spending = float(overview['total']) if overview and overview['total'] else 0.0
    total_trips = overview['total_trips'] if overview and overview['total_trips'] else 0
    
    # Category preferences for chart
    categories = [row['category'] for row in category_stats]
    counts = [int(row['count']) for row in category_stats]
    spendings = [float(row['spending']) for row in category_stats]
    
    top_category = categories[counts.index(max(counts))] if counts else None
    
    return render_template('recommendations.html', 
                           recommendations=recommendations,
                           total_spending=total_spending,
                           total_trips=total_trips,
                           categories=categories,
                           counts=counts,
                           spendings=spendings,
                           top_category=top_category)

# ---------- ADMIN ADVANCED DATA INSIGHTS & FORECASTING ----------
@app.route('/admin/analytics')
@admin_required
def admin_analytics():
    return render_template('admin/analytics.html')

@app.route('/api/admin/analytics/data')
@admin_required
def admin_analytics_data():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Fetch bookings data
    query_bookings = """
        SELECT b.id, b.total_price, b.booked_at, b.status, p.duration_days, p.price AS pkg_price,
               p.title AS pkg_title, d.category AS dest_category
        FROM bookings b
        JOIN packages p ON b.package_id = p.id
        JOIN destinations d ON p.destination_id = d.id
    """
    cursor.execute(query_bookings)
    data_bookings = cursor.fetchall()
    df_bookings = pd.DataFrame(data_bookings) if data_bookings else pd.DataFrame()
    
    # 2. Fetch all packages (for clustering & regression models)
    query_packages = """
        SELECT p.id, p.title, p.price, p.duration_days, d.category
        FROM packages p
        JOIN destinations d ON p.destination_id = d.id
    """
    cursor.execute(query_packages)
    data_packages = cursor.fetchall()
    df_packages = pd.DataFrame(data_packages) if data_packages else pd.DataFrame()
    
    cursor.close()
    
    if df_bookings.empty or df_packages.empty:
        conn.close()
        return jsonify({"error": "Insufficient data in tables to perform analysis"}), 400
        
    # Convert dates
    df_bookings['booked_at'] = pd.to_datetime(df_bookings['booked_at'])
    df_bookings['year_month'] = df_bookings['booked_at'].dt.to_period('M').astype(str)
    
    # --- TIME SERIES: BOOKING & REVENUE BY MONTH ---
    monthly_data = df_bookings[df_bookings['status'] != 'Cancelled'].groupby('year_month').agg(
        bookings_count=('id', 'count'),
        total_revenue=('total_price', 'sum')
    ).reset_index()
    monthly_data = monthly_data.sort_values('year_month')
    
    # --- CATEGORY POPULARITY ---
    cat_popularity = df_bookings[df_bookings['status'] != 'Cancelled'].groupby('dest_category').size().reset_index(name='count')
    
    # --- DATA SCIENCE: LINEAR REGRESSION (Price vs Duration) ---
    X_reg = df_packages[['duration_days']].values
    y_reg = df_packages['price'].values
    
    reg_model = LinearRegression()
    reg_model.fit(X_reg, y_reg)
    r_squared = reg_model.score(X_reg, y_reg)
    slope = reg_model.coef_[0]
    intercept = reg_model.intercept_
    
    # Generate regression line points spanning min to max duration
    min_dur, max_dur = int(df_packages['duration_days'].min()), int(df_packages['duration_days'].max())
    dur_range = np.linspace(min_dur, max_dur, 2).reshape(-1, 1)
    pred_prices = reg_model.predict(dur_range)
    regression_line = [
        {"duration": float(dur_range[0][0]), "price": float(pred_prices[0])},
        {"duration": float(dur_range[1][0]), "price": float(pred_prices[1])}
    ]
    
    # --- DATA SCIENCE: K-MEANS CLUSTERING (Packages) ---
    X_clus = df_packages[['duration_days', 'price']].values
    scaler = StandardScaler()
    X_clus_scaled = scaler.fit_transform(X_clus)
    
    kmeans = KMeans(n_clusters=min(3, len(df_packages)), random_state=42, n_init=10)
    clusters = kmeans.fit_predict(X_clus_scaled)
    
    # Centroids (inverse transform to original scale)
    centroids_scaled = kmeans.cluster_centers_
    centroids = scaler.inverse_transform(centroids_scaled)
    
    # Sort clusters by price (centroid[1]) so that 0=Budget, 1=Standard, 2=Premium
    sorted_idx = np.argsort(centroids[:, 1])
    mapping = {old_idx: new_idx for new_idx, old_idx in enumerate(sorted_idx)}
    
    df_packages['cluster'] = [mapping[c] for c in clusters]
    centroids = centroids[sorted_idx]
    
    packages_clustered = []
    for _, row in df_packages.iterrows():
        packages_clustered.append({
            "title": row['title'],
            "duration": int(row['duration_days']),
            "price": float(row['price']),
            "category": row['category'],
            "cluster": int(row['cluster'])
        })
        
    centroids_list = []
    for idx, c in enumerate(centroids):
        centroids_list.append({
            "cluster": idx,
            "duration": float(c[0]),
            "price": float(c[1])
        })
        
    # --- DATA SCIENCE: TIME-SERIES DEMAND FORECASTING ---
    # Count bookings by month
    monthly_bookings = df_bookings.groupby('year_month').size().reset_index(name='bookings')
    monthly_bookings = monthly_bookings.sort_values('year_month')
    
    # We fit a regression line over time index to project future bookings (Linear Trend Projection)
    monthly_bookings['time_idx'] = np.arange(len(monthly_bookings))
    
    X_trend = monthly_bookings[['time_idx']].values
    y_trend = monthly_bookings['bookings'].values
    
    trend_model = LinearRegression()
    trend_model.fit(X_trend, y_trend)
    
    # Project next 3 months
    last_idx = monthly_bookings['time_idx'].max()
    future_indices = np.array([last_idx + 1, last_idx + 2, last_idx + 3]).reshape(-1, 1)
    future_preds = trend_model.predict(future_indices)
    future_preds = np.clip(future_preds, 0, None)
    
    # Generate future month labels
    last_month_str = monthly_bookings['year_month'].iloc[-1]
    last_month_dt = datetime.strptime(last_month_str, '%Y-%m')
    
    future_months = []
    for i in range(1, 4):
        month_offset = last_month_dt.month + i - 1
        year_offset = last_month_dt.year + (month_offset // 12)
        month_num = (month_offset % 12) + 1
        future_months.append(f"{year_offset}-{month_num:02d}")
        
    historical_series = [
        {"month": row['year_month'], "bookings": int(row['bookings'])} 
        for _, row in monthly_bookings.iterrows()
    ]
    
    forecast_series = [
        {"month": future_months[i], "bookings": float(future_preds[i])}
        for i in range(3)
    ]
    
    conn.close()
    
    return jsonify({
        "time_series": {
            "months": monthly_data['year_month'].tolist(),
            "bookings": monthly_data['bookings_count'].tolist(),
            "revenue": [float(r) for r in monthly_data['total_revenue'].tolist()]
        },
        "categories": {
            "names": cat_popularity['dest_category'].tolist(),
            "counts": cat_popularity['count'].tolist()
        },
        "regression": {
            "r_squared": float(r_squared),
            "slope": float(slope),
            "intercept": float(intercept),
            "line": regression_line,
            "packages": [
                {"duration": int(row['duration_days']), "price": float(row['price']), "title": row['title']}
                for _, row in df_packages.iterrows()
            ]
        },
        "clustering": {
            "packages": packages_clustered,
            "centroids": centroids_list
        },
        "forecast": {
            "history": historical_series,
            "prediction": forecast_series
        }
    })

# ---------- NEW FEATURE: REVIEWS ----------
@app.route('/submit_review/<int:package_id>', methods=['POST'])
@login_required
def submit_review(package_id):
    rating = request.form.get('rating', type=int)
    review_text = request.form.get('review_text', '')
    
    if not rating:
        flash("Please provide a rating.", "danger")
        return redirect(request.referrer or url_for('destinations'))
        
    # Analyze sentiment
    blob = TextBlob(review_text)
    polarity = blob.sentiment.polarity
    if polarity > 0.1:
        sentiment = 'Positive'
    elif polarity < -0.1:
        sentiment = 'Negative'
    else:
        sentiment = 'Neutral'
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute((
            "INSERT INTO reviews (user_id, package_id, rating, review_text, sentiment) "
            "VALUES (%s, %s, %s, %s, %s) "
        ), (session['user_id'], package_id, rating, review_text, sentiment))
    conn.commit()
    cursor.close()
    conn.close()
    
    flash("Thank you for your review!", "success")
    return redirect(request.referrer or url_for('destinations'))

# ---------- NEW FEATURE: PDF TICKET ----------
@app.route('/download_ticket/<int:booking_id>')
@login_required
def download_ticket(booking_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    # Ensure this booking belongs to the current user (or admin)
    cursor.execute((
            "SELECT b.*, u.full_name, u.email, p.title as package_title "
            "FROM bookings b "
            "JOIN users u ON b.user_id = u.id "
            "JOIN packages p ON b.package_id = p.id "
            "WHERE b.id = %s AND (b.user_id = %s OR %s = 1) "
        ), (booking_id, session['user_id'], session.get('user_id')))
    booking = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if not booking or booking['status'] != 'Confirmed':
        flash("Ticket not available.", "danger")
        return redirect(url_for('my_bookings'))
        
    pdf_buffer = generate_ticket_pdf(booking)
    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f"ticket_{booking_id}.pdf",
        mimetype='application/pdf'
    )

# ---------- NEW FEATURE: CUSTOM TRIP WIZARD ----------
@app.route('/custom-trip', methods=['GET', 'POST'])
def custom_trip():
    if request.method == 'GET':
        return render_template('custom_trip.html', packages=None)
        
    # Handle POST
    budget = request.form.get('budget', type=float, default=999999)
    duration = request.form.get('duration', type=int, default=30)
    vibe = request.form.get('vibe', '').lower()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # We filter by budget and duration
    # Then we do a simple text match for the 'vibe' in description/category
    query = """
        SELECT p.*, d.name AS destination_name, d.category 
        FROM packages p
        JOIN destinations d ON p.destination_id = d.id
        WHERE p.price <= %s AND p.duration_days <= %s
    """
    cursor.execute(query, (budget, duration))
    available = cursor.fetchall()
    cursor.close()
    conn.close()
    
    # Score them based on vibe
    for pkg in available:
        pkg['score'] = 0
        if vibe in str(pkg['description']).lower() or vibe in str(pkg['category']).lower():
            pkg['score'] += 10
        # Closer to max budget is better
        pkg['score'] += (float(pkg['price']) / budget) * 5
        
    # Sort and take top 3
    available.sort(key=lambda x: x['score'], reverse=True)
    best_matches = available[:3]
    
    return render_template('custom_trip.html', packages=best_matches)

# ---------- ADMIN: MANAGE GUIDES ----------
@app.route('/admin/guides/update/<int:guide_id>/<status>')
@admin_required
def update_guide_status(guide_id, status):
    if status not in ['Approved', 'Rejected', 'Pending']:
        flash('Invalid status.', 'error')
        return redirect(url_for('admin_dashboard'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE guides SET status = %s WHERE id = %s', (status, guide_id))
    conn.commit()
    cursor.close()
    conn.close()

    flash(f'Guide status updated to {status}.', 'success')
    return redirect(url_for('admin_dashboard'))

# ---------- GUIDE PORTAL ----------
@app.route('/guide/register', methods=['GET', 'POST'])
def guide_register():
    if request.method == 'POST':
        full_name = request.form['full_name']
        email = request.form['email']
        password = request.form['password']
        phone = request.form['phone']
        experience = request.form.get('experience', 0)
        languages = request.form.get('languages', '')
        preferred_location = request.form.get('preferred_location', '')
        
        # Handle file upload for ID Card
        id_card = request.files.get('id_card')
        id_card_photo_path = None
        if id_card and id_card.filename != '':
            filename = secure_filename(id_card.filename)
            upload_folder = os.path.join(app.root_path, 'static', 'images', 'guides')
            if not os.path.exists(upload_folder):
                os.makedirs(upload_folder)
            filepath = os.path.join(upload_folder, filename)
            id_card.save(filepath)
            id_card_photo_path = f'images/guides/{filename}'
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM guides WHERE email = %s', (email,))
        if cursor.fetchone():
            flash('Email already exists. Please login.', 'error')
            cursor.close()
            conn.close()
            return redirect(url_for('guide_register'))
            
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        cursor.execute(
            'INSERT INTO guides (full_name, email, password_hash, phone, experience_years, languages, preferred_location, id_card_photo) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)',
            (full_name, email, hashed_password, phone, experience, languages, preferred_location, id_card_photo_path)
        )
        conn.commit()
        cursor.close()
        conn.close()
        
        flash('Guide registration successful! Your account is pending admin approval.', 'success')
        return redirect(url_for('guide_login'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    # Fetch distinct destination names that have packages
    cursor.execute('''
        SELECT DISTINCT d.name 
        FROM destinations d
        JOIN packages p ON d.id = p.destination_id
    ''')
    locations = [row['name'] for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    
    return render_template('guide_register.html', locations=locations)

@app.route('/guide/login', methods=['GET', 'POST'])
def guide_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM guides WHERE email = %s', (email,))
        guide = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if guide and check_password_hash(guide['password_hash'], password):
            if guide.get('status') == 'Pending':
                flash('Your account is currently under review by an administrator.', 'warning')
                return redirect(url_for('guide_login'))
            elif guide.get('status') == 'Rejected':
                flash('Your guide application was rejected. Please contact support.', 'error')
                return redirect(url_for('guide_login'))
                
            session['guide_id'] = guide['id']
            session['guide_name'] = guide['full_name']
            flash('Login successful!', 'success')
            return redirect(url_for('guide_dashboard'))
        else:
            flash('Invalid credentials. Please try again.', 'error')
            
    return render_template('guide_login.html')

@app.route('/guide/logout')
def guide_logout():
    session.pop('guide_id', None)
    session.pop('guide_name', None)
    flash('Logged out successfully.', 'success')
    return redirect(url_for('home'))

@app.route('/guide/dashboard')
@guide_required
def guide_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get assignments
    cursor.execute('''
        SELECT b.*, u.full_name as user_name, u.email as user_email, u.phone as user_phone, p.title as package_title
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        JOIN packages p ON b.package_id = p.id
        WHERE b.guide_id = %s
    ''', (session['guide_id'],))
    assignments = cursor.fetchall()
    
    # Get notifications
    cursor.execute('SELECT * FROM guide_notifications WHERE guide_id = %s ORDER BY created_at DESC', (session['guide_id'],))
    notifications = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('guide_dashboard.html', assignments=assignments, notifications=notifications)

@app.route('/guide/notifications/read/<int:notif_id>')
@guide_required
def read_notification(notif_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE guide_notifications SET is_read = TRUE WHERE id = %s AND guide_id = %s', (notif_id, session['guide_id']))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('guide_dashboard'))

@app.route('/api/available_guides')
def available_guides():
    package_id = request.args.get('package_id')
    travel_date = request.args.get('travel_date')
    
    if not package_id or not travel_date:
        return jsonify([])

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get package destination and duration
    cursor.execute('''
        SELECT d.name, d.location, p.duration_days 
        FROM packages p 
        JOIN destinations d ON p.destination_id = d.id 
        WHERE p.id = %s
    ''', (package_id,))
    dest = cursor.fetchone()
    
    if not dest:
        cursor.close()
        conn.close()
        return jsonify([])

    duration = dest['duration_days']
    
    # Query for available APPROVED guides not double-booked
    query = '''
        SELECT id, full_name, experience_years FROM guides g
        WHERE g.status = 'Approved' 
        AND (LOWER(g.preferred_location) LIKE LOWER(%s) OR LOWER(g.preferred_location) LIKE LOWER(%s))
        AND g.id NOT IN (
            SELECT b_exist.guide_id FROM bookings b_exist
            JOIN packages p_exist ON b_exist.package_id = p_exist.id
            WHERE b_exist.status IN ('Confirmed', 'Pending') AND b_exist.guide_id IS NOT NULL
            AND DATE(b_exist.travel_date) <= DATE_ADD(%s, INTERVAL %s DAY)
            AND DATE_ADD(DATE(b_exist.travel_date), INTERVAL p_exist.duration_days DAY) >= %s
        )
    '''
    cursor.execute(query, (
        f"%{dest['name']}%", f"%{dest['location']}%", 
        travel_date, duration, travel_date
    ))
    
    guides = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return jsonify(guides)

if __name__ == '__main__':
    app.run(debug=True, port=5001)
